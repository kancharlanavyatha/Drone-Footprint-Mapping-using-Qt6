import os
import sys
import json
import csv
import math
import pyproj
from PIL import Image
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QTransform, QImage, QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QListWidget, QListWidgetItem, QCheckBox, 
    QSplitter, QFrame, QGroupBox, QStatusBar
)

class MapCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        
        # State
        self.points = []          # List of (x, y, z) in UTM 15N
        self.drone_images = []    # List of metadata dicts
        self.selected_idx = -1
        
        # View parameters (centered around Brighton Beach)
        self.zoom = 5.0           # pixels per meter
        self.pan_x = 0.0          # offset in meters from origin
        self.pan_y = 0.0
        
        # Display settings
        self.show_point_cloud = True
        self.show_flight_path = True
        self.show_footprints = True
        self.show_image_overlay = True
        
        # Mouse interaction
        self.last_mouse_pos = None
        self.is_panning = False
        
        # Image cache
        self.image_cache = {}     # filename -> QImage
        
        # GeoTIFF metadata from PIL (instead of GDAL for compatibility in Python 3.10)
        self.dsm_data = None      # 2D numpy array of elevation
        self.dsm_w = 0
        self.dsm_h = 0
        
        # UTM 10N bounds from GeoTIFF tags
        self.dsm_gt_x = 2851243.844664077
        self.dsm_gt_y = 5674920.902038985
        self.dsm_pixel_scale = 0.07015431312445902
        
        # Coordinate bounds in UTM 15N
        self.x_min, self.x_max = 576660, 576770
        self.y_min, self.y_max = 5188110, 5188220
        self.z_min, self.z_max = 156.0, 169.0
        
        # Default view origin
        self.origin_x = (self.x_min + self.x_max) / 2.0
        self.origin_y = (self.y_min + self.y_max) / 2.0
        
        # Projection Transformers
        self.transformer_to_gps = pyproj.Transformer.from_crs("epsg:32615", "epsg:4326", always_xy=True)
        self.transformer_to_utm10 = pyproj.Transformer.from_crs("epsg:4326", "epsg:32610", always_xy=True)
        
    def set_data(self, points, drone_images, dsm_path):
        self.points = points
        self.drone_images = drone_images
        
        # Load DSM elevations using PIL + numpy
        if os.path.exists(dsm_path):
            try:
                import numpy as np
                pil_img = Image.open(dsm_path)
                self.dsm_data = np.array(pil_img)
                self.dsm_w = pil_img.width
                self.dsm_h = pil_img.height
                
                # Try reading GeoTIFF tags
                if hasattr(pil_img, 'tag'):
                    # Tag 33550 is ModelPixelScaleTag
                    if 33550 in pil_img.tag:
                        self.dsm_pixel_scale = pil_img.tag[33550][0]
                    # Tag 33922 is ModelTiepointTag
                    if 33922 in pil_img.tag:
                        tp = pil_img.tag[33922]
                        self.dsm_gt_x = tp[3]
                        self.dsm_gt_y = tp[4]
            except Exception as e:
                print(f"Error loading DSM with PIL: {e}")
            
        if self.points:
            xs = [p[0] for p in self.points]
            ys = [p[1] for p in self.points]
            zs = [p[2] for p in self.points]
            self.x_min, self.x_max = min(xs), max(xs)
            self.y_min, self.y_max = min(ys), max(ys)
            self.z_min, self.z_max = min(zs), max(zs)
            self.origin_x = (self.x_min + self.x_max) / 2.0
            self.origin_y = (self.y_min + self.y_max) / 2.0
            
        self.reset_view()
        self.update()
        
    def reset_view(self):
        self.zoom = 5.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()
        
    def to_screen(self, x, y):
        # Translate UTM (x, y) to screen pixels (u, v)
        u = self.width() / 2.0 + (x - self.origin_x + self.pan_x) * self.zoom
        v = self.height() / 2.0 - (y - self.origin_y + self.pan_y) * self.zoom
        return u, v
        
    def to_map(self, u, v):
        # Translate screen pixels (u, v) to UTM (x, y)
        x = (u - self.width() / 2.0) / self.zoom + self.origin_x - self.pan_x
        y = (self.height() / 2.0 - v) / self.zoom + self.origin_y - self.pan_y
        return x, y
        
    def get_elevation_at_utm(self, x_utm, y_utm):
        if self.dsm_data is None:
            return None
            
        # Convert UTM 15N -> WGS84 -> UTM 10N -> pixel coordinate
        lon, lat = self.transformer_to_gps.transform(x_utm, y_utm)
        x_10, y_10 = self.transformer_to_utm10.transform(lon, lat)
        
        # Convert to pixel coordinate on the DSM (which is projected in UTM 10N)
        # GT math: X = gt_x + col * pixel_scale, Y = gt_y - row * pixel_scale
        col = int((x_10 - self.dsm_gt_x) / self.dsm_pixel_scale + 0.5)
        row = int((self.dsm_gt_y - y_10) / self.dsm_pixel_scale + 0.5)
        
        if 0 <= col < self.dsm_w and 0 <= row < self.dsm_h:
            try:
                val = self.dsm_data[row, col]
                if val != -9999.0:
                    return float(val)
            except Exception:
                pass
        return None
        
    def get_color_for_z(self, z):
        # Color mapping (terrain color ramp: blue for low, green for beach, brown/white for heights)
        if self.z_max == self.z_min:
            t = 0.5
        else:
            t = (z - self.z_min) / (self.z_max - self.z_min)
        t = max(0.0, min(1.0, t))
        
        # Simple terrain color ramp
        if t < 0.15:
            # Water (Deep Blue to Light Blue)
            return QColor(10, 50, int(150 + t * 500))
        elif t < 0.3:
            # Sandy Beach (Pale Yellow/Green)
            w = (t - 0.15) / 0.15
            return QColor(int(220 + w*20), int(200 + w*30), int(150 - w*50))
        elif t < 0.6:
            # Vegetation (Green to Dark Green)
            w = (t - 0.3) / 0.3
            return QColor(int(100 - w*60), int(180 - w*60), int(100 - w*60))
        else:
            # Forest/Rock (Dark Green to Brown to White)
            w = (t - 0.6) / 0.4
            return QColor(int(60 + w*140), int(90 + w*100), int(50 + w*130))

    def load_cached_image(self, path):
        if path not in self.image_cache:
            if os.path.exists(path):
                img = QImage(path)
                if not img.isNull():
                    # Downsample image to save memory and render fast
                    self.image_cache[path] = img.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                else:
                    self.image_cache[path] = None
            else:
                self.image_cache[path] = None
        return self.image_cache[path]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Fill background (sleek dark grid background)
        painter.fillRect(self.rect(), QColor(25, 27, 33))
        self.draw_grid(painter)
        
        # 1. Draw Point Cloud
        if self.show_point_cloud and self.points:
            for x, y, z in self.points:
                u, v = self.to_screen(x, y)
                if 0 <= u < self.width() and 0 <= v < self.height():
                    painter.setPen(self.get_color_for_z(z))
                    painter.drawPoint(QPointF(u, v))
                    
        # 2. Draw Drone Flight Path
        if self.show_flight_path and self.drone_images:
            path_pen = QPen(QColor(0, 160, 255, 120), 2, Qt.DashLine)
            painter.setPen(path_pen)
            
            # Connect all drone points
            for i in range(len(self.drone_images) - 1):
                img1 = self.drone_images[i]
                img2 = self.drone_images[i+1]
                u1, v1 = self.to_screen(img1['utm_x'], img1['utm_y'])
                u2, v2 = self.to_screen(img2['utm_x'], img2['utm_y'])
                painter.drawLine(QPointF(u1, v1), QPointF(u2, v2))
                
        # 3. Draw Selected Image Warped Overlay
        if self.show_image_overlay and self.selected_idx != -1:
            img_data = self.drone_images[self.selected_idx]
            # Resolve image file path
            img_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'drone_dataset_brighton_beach-master', 'images', img_data['filename'])
            qimg = self.load_cached_image(img_path)
            
            if qimg:
                painter.save()
                
                # Image footprint math
                h = img_data['relative_altitude']
                # DJI Phantom 3 FOV constants
                tan_h = 0.857
                tan_v = 0.643
                W_ground = 2.0 * h * tan_h
                H_ground = 2.0 * h * tan_v
                
                X_c, Y_c = img_data['utm_x'], img_data['utm_y']
                yaw = img_data['gimbal_yaw'] # in degrees
                
                # Center screen position of the drone
                u_c, v_c = self.to_screen(X_c, Y_c)
                
                # QTransform matrix
                # 1. Map to screen center of drone
                t = QTransform()
                t.translate(u_c, v_c)
                # 2. Rotate by gimbal yaw (clockwise in Qt screen space)
                t.rotate(yaw)
                # 3. Scale from image dimensions to screen footprint dimensions (meters * zoom)
                t.scale(W_ground * self.zoom / qimg.width(), H_ground * self.zoom / qimg.height())
                # 4. Offset to center the image on (0, 0)
                t.translate(-qimg.width() / 2.0, -qimg.height() / 2.0)
                
                painter.setTransform(t)
                painter.setOpacity(0.7) # semi-transparent overlay
                painter.drawImage(0, 0, qimg)
                painter.restore()

        # 4. Draw Image Footprints (Rotated Rectangles)
        if self.show_footprints and self.drone_images:
            for idx, img_data in enumerate(self.drone_images):
                # Calculate corners of footprint
                h = img_data['relative_altitude']
                W_ground = 2.0 * h * 0.857
                H_ground = 2.0 * h * 0.643
                
                yaw_rad = math.radians(img_data['gimbal_yaw'])
                cos_y = math.cos(yaw_rad)
                sin_y = math.sin(yaw_rad)
                
                # Local rectangle corners
                corners = [
                    (-W_ground/2, H_ground/2),   # TL
                    (W_ground/2, H_ground/2),    # TR
                    (W_ground/2, -H_ground/2),   # BR
                    (-W_ground/2, -H_ground/2)   # BL
                ]
                
                # Rotate and translate to UTM map coords
                map_corners = []
                for lx, ly in corners:
                    mx = img_data['utm_x'] + lx * cos_y + ly * sin_y
                    my = img_data['utm_y'] - lx * sin_y + ly * cos_y
                    map_corners.append(self.to_screen(mx, my))
                
                # Draw boundary
                polygon = [QPointF(u, v) for u, v in map_corners]
                
                if idx == self.selected_idx:
                    pen = QPen(QColor(255, 170, 0), 2)
                    brush = QBrush(QColor(255, 170, 0, 30))
                else:
                    pen = QPen(QColor(0, 200, 100, 100), 1)
                    brush = QBrush(QColor(0, 200, 100, 10))
                    
                painter.setPen(pen)
                painter.setBrush(brush)
                painter.drawPolygon(polygon)
                
        # 5. Draw Drone Position Markers
        if self.drone_images:
            for idx, img_data in enumerate(self.drone_images):
                u, v = self.to_screen(img_data['utm_x'], img_data['utm_y'])
                
                if idx == self.selected_idx:
                    painter.setPen(QPen(QColor(255, 255, 255), 2))
                    painter.setBrush(QBrush(QColor(255, 170, 0)))
                    radius = 8
                else:
                    painter.setPen(QPen(QColor(0, 0, 0), 1))
                    painter.setBrush(QBrush(QColor(0, 150, 255)))
                    radius = 5
                    
                painter.drawEllipse(QPointF(u, v), radius, radius)
                
                # Draw index number
                painter.setPen(QColor(255, 255, 255))
                painter.setFont(QFont("Arial", 8, QFont.Bold))
                painter.drawText(QPointF(u + 8, v - 8), str(idx + 18))
                
    def draw_grid(self, painter):
        # Draw background coordinates grid
        grid_size = 20 # every 20 meters
        pen = QPen(QColor(40, 45, 55), 1)
        painter.setPen(pen)
        
        # Get bounds in map coords
        x_start = math.floor(self.to_map(0, 0)[0] / grid_size) * grid_size
        x_end = math.ceil(self.to_map(self.width(), 0)[0] / grid_size) * grid_size
        y_start = math.floor(self.to_map(0, self.height())[1] / grid_size) * grid_size
        y_end = math.ceil(self.to_map(0, 0)[1] / grid_size) * grid_size
        
        for gx in range(int(x_start), int(x_end) + grid_size, grid_size):
            u, _ = self.to_screen(gx, self.origin_y)
            painter.drawLine(u, 0, u, self.height())
            
        for gy in range(int(y_start), int(y_end) + grid_size, grid_size):
            _, v = self.to_screen(self.origin_x, gy)
            painter.drawLine(0, v, self.width(), v)
            
    # Mouse events for Pan & Zoom & Click Selection
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.last_mouse_pos = event.position()
            self.is_panning = True
            
            # Click selection check
            click_x, click_y = self.to_map(event.position().x(), event.position().y())
            threshold = 3.0 # meters radius to click marker
            clicked_idx = -1
            
            for idx, img in enumerate(self.drone_images):
                dist = math.hypot(img['utm_x'] - click_x, img['utm_y'] - click_y)
                if dist < threshold:
                    clicked_idx = idx
                    break
                    
            if clicked_idx != -1:
                self.selected_idx = clicked_idx
                self.parent().select_image(clicked_idx)
                self.update()
                
    def mouseMoveEvent(self, event):
        mx, my = self.to_map(event.position().x(), event.position().y())
        
        # Display coordinate status
        elev = self.get_elevation_at_utm(mx, my)
        elev_str = f"Elev: {elev:.2f} m" if elev is not None else "Elev: N/A"
        status_msg = f"UTM X: {mx:.2f} m, UTM Y: {my:.2f} m | {elev_str}"
        self.parent().statusBar().showMessage(status_msg)
        
        if self.is_panning and self.last_mouse_pos:
            delta = event.position() - self.last_mouse_pos
            self.pan_x += delta.x() / self.zoom
            self.pan_y -= delta.y() / self.zoom # Y screen is inverted
            self.last_mouse_pos = event.position()
            self.update()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_panning = False
            self.last_mouse_pos = None
            
    def wheelEvent(self, event):
        # Zoom centered around mouse position
        mouse_pos = event.position()
        mx, my = self.to_map(mouse_pos.x(), mouse_pos.y())
        
        # Zoom factor
        factor = 1.15 if event.angleDelta().y() > 0 else 0.85
        self.zoom = max(0.2, min(50.0, self.zoom * factor))
        
        # Re-align pan so mouse stays at same map coordinate
        new_u, new_v = self.to_screen(mx, my)
        self.pan_x += (mouse_pos.x() - new_u) / self.zoom
        self.pan_y -= (mouse_pos.y() - new_v) / self.zoom
        
        self.update()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drone Footprint Mapper & Point Cloud Visualizer")
        self.resize(1200, 850)
        
        # Apply dark stylesheet
        self.apply_dark_theme()
        
        # Main layout
        self.setup_ui()
        
        # Load datasets
        self.load_datasets()
        
    def setup_ui(self):
        # central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left Panel (Interactive Map Canvas)
        self.canvas = MapCanvas(self)
        splitter.addWidget(self.canvas)
        
        # Right Panel (Metadata, Previews, Controls)
        right_panel = QFrame()
        right_panel.setFrameShape(QFrame.StyledPanel)
        right_panel.setObjectName("RightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(15)
        
        # Title
        title_label = QLabel("DRONE FOOTPRINT MAP")
        title_label.setObjectName("PanelTitle")
        right_layout.addWidget(title_label)
        
        # Layer controls
        layers_group = QGroupBox("Layers")
        layers_layout = QVBoxLayout(layers_group)
        self.chk_pc = QCheckBox("Point Cloud (downsampled)")
        self.chk_pc.setChecked(True)
        self.chk_pc.stateChanged.connect(self.toggle_layers)
        self.chk_fp = QCheckBox("Image Footprints (rotated)")
        self.chk_fp.setChecked(True)
        self.chk_fp.stateChanged.connect(self.toggle_layers)
        self.chk_path = QCheckBox("Flight Path (dashed)")
        self.chk_path.setChecked(True)
        self.chk_path.stateChanged.connect(self.toggle_layers)
        self.chk_overlay = QCheckBox("Image Overlays (warped)")
        self.chk_overlay.setChecked(True)
        self.chk_overlay.stateChanged.connect(self.toggle_layers)
        
        layers_layout.addWidget(self.chk_pc)
        layers_layout.addWidget(self.chk_fp)
        layers_layout.addWidget(self.chk_path)
        layers_layout.addWidget(self.chk_overlay)
        right_layout.addWidget(layers_group)
        
        # Image list
        list_group = QGroupBox("Select Drone Image")
        list_layout = QVBoxLayout(list_group)
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self.list_selection_changed)
        list_layout.addWidget(self.list_widget)
        right_layout.addWidget(list_group)
        
        # Selected metadata
        self.meta_group = QGroupBox("Active Metadata")
        meta_layout = QVBoxLayout(self.meta_group)
        
        self.lbl_filename = QLabel("Image: Select an image...")
        self.lbl_gps = QLabel("GPS: (lat, lon)")
        self.lbl_utm = QLabel("UTM 15N: (E, N)")
        self.lbl_alt = QLabel("Altitude: (Rel/Abs)")
        self.lbl_gimbal = QLabel("Gimbal Yaw/Pitch: ")
        
        for lbl in [self.lbl_filename, self.lbl_gps, self.lbl_utm, self.lbl_alt, self.lbl_gimbal]:
            lbl.setWordWrap(True)
            meta_layout.addWidget(lbl)
            
        right_layout.addWidget(self.meta_group)
        
        # Selected thumbnail preview
        self.preview_group = QGroupBox("Thumbnail Preview")
        preview_layout = QVBoxLayout(self.preview_group)
        self.lbl_preview = QLabel("No Image Selected")
        self.lbl_preview.setMinimumSize(250, 180)
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setObjectName("PreviewArea")
        preview_layout.addWidget(self.lbl_preview)
        right_layout.addWidget(self.preview_group)
        
        # Navigation controls
        btn_reset = QPushButton("Reset View")
        btn_reset.clicked.connect(self.canvas.reset_view)
        right_layout.addWidget(btn_reset)
        
        right_panel.setFixedWidth(320)
        splitter.addWidget(right_panel)
        
        # Setup status bar
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready")
        
    def load_datasets(self):
        project_dir = os.path.dirname(os.path.dirname(__file__))
        dataset_dir = os.path.join(project_dir, 'drone_dataset_brighton_beach-master')
        
        # 1. Load Image metadata
        meta_path = os.path.join(dataset_dir, 'images_metadata.json')
        drone_images = []
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r') as f:
                    drone_images = json.load(f)
            except Exception as e:
                self.statusBar().showMessage(f"Error loading metadata JSON: {e}")
        else:
            self.statusBar().showMessage(f"Metadata file not found: {meta_path}")
            
        # Populate List widget
        self.list_widget.clear()
        for idx, img in enumerate(drone_images):
            label_text = f"Image {idx + 18} ({img['filename']})"
            item = QListWidgetItem(label_text)
            self.list_widget.addItem(item)
            
        # 2. Load downsampled point cloud
        points = []
        pc_path = os.path.join(dataset_dir, 'points_downsampled.csv')
        if os.path.exists(pc_path):
            try:
                with open(pc_path, 'r') as f:
                    reader = csv.reader(f)
                    next(reader) # skip header
                    for row in reader:
                        if row:
                            points.append((float(row[0]), float(row[1]), float(row[2])))
            except Exception as e:
                self.statusBar().showMessage(f"Error loading downsampled points: {e}")
        else:
            self.statusBar().showMessage(f"Point CSV not found: {pc_path}")
            
        # 3. Load DSM TIFF
        dsm_path = os.path.join(dataset_dir, 'dsm.tif')
        
        # Send data to Canvas
        self.canvas.set_data(points, drone_images, dsm_path)
        self.statusBar().showMessage(f"Loaded {len(points)} points, {len(drone_images)} images, and DSM raster.")
        
    def list_selection_changed(self, idx):
        if idx < 0 or idx >= len(self.canvas.drone_images):
            return
        self.canvas.selected_idx = idx
        self.canvas.update()
        
        # Update metadata display
        img = self.canvas.drone_images[idx]
        self.lbl_filename.setText(f"<b>Image File:</b> {img['filename']}")
        self.lbl_gps.setText(f"<b>GPS Coordinate:</b><br>Lat: {img['latitude']:.7f}°<br>Lon: {img['longitude']:.7f}°")
        self.lbl_utm.setText(f"<b>UTM 15N Coordinate:</b><br>E: {img['utm_x']:.2f} m<br>N: {img['utm_y']:.2f} m")
        self.lbl_alt.setText(f"<b>Altitude:</b><br>Relative: {img['relative_altitude']:.1f} m<br>Absolute: {img['absolute_altitude']:.1f} m")
        self.lbl_gimbal.setText(f"<b>Gimbal Angles:</b><br>Pitch: {img['gimbal_pitch']:.1f}° (Nadir)<br>Yaw: {img['gimbal_yaw']:.1f}°")
        
        # Load and set thumbnail preview
        project_dir = os.path.dirname(os.path.dirname(__file__))
        img_path = os.path.join(project_dir, 'drone_dataset_brighton_beach-master', 'images', img['filename'])
        if os.path.exists(img_path):
            pix = QPixmap(img_path)
            self.lbl_preview.setPixmap(pix.scaled(280, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.lbl_preview.setText("Image File Missing")
            
    def select_image(self, idx):
        self.list_widget.setCurrentRow(idx)
        
    def toggle_layers(self, state):
        self.canvas.show_point_cloud = self.chk_pc.isChecked()
        self.canvas.show_footprints = self.chk_fp.isChecked()
        self.canvas.show_flight_path = self.chk_path.isChecked()
        self.canvas.show_image_overlay = self.chk_overlay.isChecked()
        self.canvas.update()
        
    def apply_dark_theme(self):
        qss = """
        QMainWindow {
            background-color: #1e1e24;
        }
        QWidget {
            color: #e0e0e0;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px;
        }
        #RightPanel {
            background-color: #262932;
            border-left: 1px solid #3c404f;
        }
        #PanelTitle {
            font-size: 16px;
            font-weight: bold;
            color: #00a0ff;
            letter-spacing: 1px;
            padding-bottom: 5px;
            border-bottom: 2px solid #00a0ff;
        }
        QGroupBox {
            font-weight: bold;
            color: #cfcfcf;
            border: 1px solid #3c404f;
            border-radius: 6px;
            margin-top: 12px;
            padding: 10px 5px 5px 5px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0px 5px;
        }
        QCheckBox {
            spacing: 8px;
            padding: 3px 0;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #5a5f78;
            border-radius: 3px;
            background-color: #1e1e24;
        }
        QCheckBox::indicator:checked {
            background-color: #00a0ff;
            border-color: #00a0ff;
        }
        QListWidget {
            background-color: #1a1c23;
            border: 1px solid #3c404f;
            border-radius: 4px;
            padding: 5px;
        }
        QListWidget::item {
            padding: 6px 10px;
            border-radius: 3px;
            margin-bottom: 2px;
        }
        QListWidget::item:hover {
            background-color: #2b2f3d;
            color: #ffffff;
        }
        QListWidget::item:selected {
            background-color: #0080dd;
            color: #ffffff;
            font-weight: bold;
        }
        QLabel {
            color: #d0d2db;
        }
        QPushButton {
            background-color: #00a0ff;
            color: #ffffff;
            border: none;
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #33b3ff;
        }
        QPushButton:pressed {
            background-color: #0080dd;
        }
        #PreviewArea {
            background-color: #15161b;
            border: 1px solid #3c404f;
            border-radius: 4px;
        }
        QStatusBar {
            background-color: #1a1c23;
            color: #8f92a3;
            border-top: 1px solid #3c404f;
        }
        """
        self.setStyleSheet(qss)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
