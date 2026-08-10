#include "mapcanvas.h"
#include <QPainter>
#include <QMouseEvent>
#include <QWheelEvent>
#include <QFile>
#include <QDir>
#include <QCoreApplication>
#include <QStatusBar>
#include <cmath>
#include <algorithm>
#include <QDebug>

MapCanvas::MapCanvas(QWidget *parent)
    : QWidget(parent),
      showPointCloud(true),
      showFlightPath(true),
      showFootprints(true),
      showImageOverlay(true),
      selectedIdx(-1),
      zoom(1.5),
      panX(0.0),
      panY(0.0),
      originX(0.0),
      originY(0.0),
      xMin(0.0), xMax(0.0),
      yMin(0.0), yMax(0.0),
      zMin(0.0), zMax(0.0),
      isPanning(false),
      imageCache(10), // Limit cache to 10 scaled images
      dsmDataset(nullptr),
      dsmBand(nullptr),
      poCT_to_GPS(nullptr),
      poCT_to_UTM10(nullptr) {

    // 1. Setup GDAL Coordinate Transformations
    // Points are in UTM Zone 15N (EPSG:32615)
    oSourceSRS.importFromEPSG(32615);
    
    // GPS standard coordinates are WGS 84 (EPSG:4326)
    oGpsSRS.importFromEPSG(4326);
    oGpsSRS.SetAxisMappingStrategy(OAMS_TRADITIONAL_GIS_ORDER); // Lon, Lat order
    
    // The dsm.tif uses UTM Zone 10N (EPSG:32610)
    oUtm10SRS.importFromEPSG(32610);

    poCT_to_GPS = OGRCreateCoordinateTransformation(&oSourceSRS, &oGpsSRS);
    poCT_to_UTM10 = OGRCreateCoordinateTransformation(&oSourceSRS, &oUtm10SRS);

    if (!poCT_to_GPS) {
        qDebug() << "GDAL Warning: Failed to create coordinate transformation to GPS!";
    }
    if (!poCT_to_UTM10) {
        qDebug() << "GDAL Warning: Failed to create coordinate transformation to UTM 10N!";
    }
}

MapCanvas::~MapCanvas() {
    if (dsmDataset) {
        GDALClose(dsmDataset);
    }
    if (poCT_to_GPS) {
        OCTDestroyCoordinateTransformation(poCT_to_GPS);
    }
    if (poCT_to_UTM10) {
        OCTDestroyCoordinateTransformation(poCT_to_UTM10);
    }
}

void MapCanvas::setData(const QVector<Point3D>& pts, const QVector<DroneImage>& images, const QString& dsmPath) {
    points = pts;
    droneImages = images;

    // 1. Open GDAL DSM Digital Elevation GeoTIFF
    dsmDataset = (GDALDataset*)GDALOpen(dsmPath.toUtf8().constData(), GA_ReadOnly);
    if (dsmDataset) {
        dsmDataset->GetGeoTransform(dsmGeoTransform);
        dsmWidth = dsmDataset->GetRasterXSize();
        dsmHeight = dsmDataset->GetRasterYSize();
        dsmBand = dsmDataset->GetRasterBand(1); // Band 1 stores elevations
        qDebug() << "GDAL: Successfully loaded DSM elevation model.";
    } else {
        qDebug() << "GDAL Error: Failed to open elevation raster at:" << dsmPath;
    }

    // 2. Compute point cloud bounds to frame the view
    if (!points.isEmpty()) {
        xMin = xMax = points[0].x;
        yMin = yMax = points[0].y;
        zMin = zMax = points[0].z;

        for (const auto& pt : points) {
            xMin = std::min(xMin, pt.x);
            xMax = std::max(xMax, pt.x);
            yMin = std::min(yMin, pt.y);
            yMax = std::max(yMax, pt.y);
            zMin = std::min(zMin, pt.z);
            zMax = std::max(zMax, pt.z);
        }

        // Set map origin to center
        originX = (xMin + xMax) / 2.0;
        originY = (yMin + yMax) / 2.0;
    } else if (!droneImages.isEmpty()) {
        xMin = xMax = droneImages[0].utm_x;
        yMin = yMax = droneImages[0].utm_y;
        zMin = 0.0;
        zMax = 200.0;

        for (const auto& img : droneImages) {
            xMin = std::min(xMin, img.utm_x);
            xMax = std::max(xMax, img.utm_x);
            yMin = std::min(yMin, img.utm_y);
            yMax = std::max(yMax, img.utm_y);
        }

        // Set map origin to center
        originX = (xMin + xMax) / 2.0;
        originY = (yMin + yMax) / 2.0;
    }

    resetView();
}

void MapCanvas::resetView() {
    zoom = 1.8;
    panX = 0.0;
    panY = 0.0;
    update();
}

QPointF MapCanvas::toScreen(double x, double y) const {
    // Converts physical coordinates in meters (UTM) to screen pixel coordinates
    double u = width() / 2.0 + (x - originX + panX) * zoom;
    double v = height() / 2.0 - (y - originY + panY) * zoom; // Y screen is inverted
    return QPointF(u, v);
}

QPointF MapCanvas::toMap(double u, double v) const {
    // Converts screen pixel coordinates back to map coordinate meters
    double x = (u - width() / 2.0) / zoom + originX - panX;
    double y = (height() / 2.0 - v) / zoom + originY - panY;
    return QPointF(x, y);
}

double MapCanvas::getElevationAtUtm(double x_utm, double y_utm) {
    // If the elevation model isn't loaded or coordinates transformers aren't ready, return N/A
    if (!dsmBand || !poCT_to_UTM10) return -9999.0;

    double x_10 = x_utm;
    double y_10 = y_utm;
    double z_dummy = 0.0;

    // Convert input UTM 15N coordinate to UTM 10N coordinate using OGR
    if (poCT_to_UTM10->Transform(1, &x_10, &y_10, &z_dummy)) {
        // Map standard geospatial coordinate (X, Y) to image pixel grid (col, row):
        // col = (X - originX) / pixelWidth
        // row = (originY - Y) / pixelHeight
        int col = std::round((x_10 - dsmGeoTransform[0]) / dsmGeoTransform[1]);
        int row = std::round((dsmGeoTransform[3] - y_10) / (-dsmGeoTransform[5]));

        // Check if the calculated pixel lies within the raster dimensions
        if (col >= 0 && col < dsmWidth && row >= 0 && row < dsmHeight) {
            float elev = -9999.0f;
            // Read 1x1 pixel block directly from the float32 DSM TIFF band using GDAL RasterIO
            if (dsmBand->RasterIO(GF_Read, col, row, 1, 1, &elev, 1, 1, GDT_Float32, 0, 0) == CE_None) {
                if (elev != -9999.0f) {
                    return elev; // Return valid elevation in meters
                }
            }
        }
    }
    return -9999.0;
}

QImage* MapCanvas::loadCachedImage(const QString& filename) {
    QImage *cached = imageCache.object(filename);
    if (!cached) {
        QString projectDir = QCoreApplication::applicationDirPath();
        QDir dir(projectDir);
        while (dir.cdUp()) {
            if (dir.exists("drone_dataset_brighton_beach-master")) {
                break;
            }
        }
        QString imgPath = dir.absoluteFilePath(QString("drone_dataset_brighton_beach-master/images/%1").arg(filename));
        
        // Fallback check
        if (!QFile::exists(imgPath)) {
            imgPath = QString("d:/DRDO/drone points/drone_dataset_brighton_beach-master/images/%1").arg(filename);
        }

        if (QFile::exists(imgPath)) {
            QImage img(imgPath);
            if (!img.isNull()) {
                // Downsample image to save memory and make drawing fast
                QImage scaledImg = img.scaled(800, 600, Qt::KeepAspectRatio, Qt::SmoothTransformation);
                cached = new QImage(scaledImg);
                imageCache.insert(filename, cached);
            }
        }
    }
    return cached;
}

void MapCanvas::paintEvent(QPaintEvent *event) {
    Q_UNUSED(event);
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    // Draw background
    painter.fillRect(rect(), QColor(25, 27, 33));
    drawGrid(painter);

    // 1. Draw Point Cloud
    if (showPointCloud && !points.isEmpty()) {
        for (const auto& pt : points) {
            QPointF sc = toScreen(pt.x, pt.y);
            if (sc.x() >= 0 && sc.x() < width() && sc.y() >= 0 && sc.y() < height()) {
                painter.setPen(getColorForZ(pt.z));
                painter.drawPoint(sc);
            }
        }
    }

    // 2. Draw Flight Path
    if (showFlightPath && !droneImages.isEmpty()) {
        QPen pathPen(QColor(0, 160, 255, 120), 2, Qt::DashLine);
        painter.setPen(pathPen);

        for (int i = 0; i < droneImages.size() - 1; ++i) {
            QPointF p1 = toScreen(droneImages[i].utm_x, droneImages[i].utm_y);
            QPointF p2 = toScreen(droneImages[i+1].utm_x, droneImages[i+1].utm_y);
            painter.drawLine(p1, p2);
        }
    }

    // 3. Draw Selected Warped Image Overlay
    if (showImageOverlay && selectedIdx != -1) {
        const DroneImage& imgData = droneImages[selectedIdx];
        QImage *qimg = loadCachedImage(imgData.filename);
        if (qimg) {
            painter.save();

            double W_ground = 2.0 * h * 0.857;
            double H_ground = 2.0 * h * 0.481;
            QPointF sc = toScreen(imgData.utm_x, imgData.utm_y);

            QTransform t;
            // Translate to drone center
            t.translate(sc.x(), sc.y());
            // Rotate by yaw
            t.rotate(imgData.gimbal_yaw);
            // Scale from image pixels to screen footprint dimensions (meters * zoom)
            t.scale(W_ground * zoom / qimg->width(), H_ground * zoom / qimg->height());
            // Center the image
            t.translate(-qimg->width() / 2.0, -qimg->height() / 2.0);

            painter.setTransform(t);
            painter.setOpacity(0.7);
            painter.drawImage(0, 0, *qimg);
            painter.restore();
        }
    }

    // 4. Draw Image Footprints
    if (showFootprints && !droneImages.isEmpty()) {
        for (int idx = 0; idx < droneImages.size(); ++idx) {
            const auto& imgData = droneImages[idx];
            double h = imgData.relative_altitude;
            double W_ground = 2.0 * h * 0.857;
            double H_ground = 2.0 * h * 0.481;

            double yaw_rad = imgData.gimbal_yaw * M_PI / 180.0;
            double cos_y = std::cos(yaw_rad);
            double sin_y = std::sin(yaw_rad);

            // Local corners relative to camera center
            QPointF corners[4] = {
                QPointF(-W_ground/2.0, H_ground/2.0),
                QPointF(W_ground/2.0, H_ground/2.0),
                QPointF(W_ground/2.0, -H_ground/2.0),
                QPointF(-W_ground/2.0, -H_ground/2.0)
            };

            // Project to map and then screen
            QPointF screenCorners[4];
            for (int i = 0; i < 4; ++i) {
                double mx = imgData.utm_x + corners[i].x() * cos_y + corners[i].y() * sin_y;
                double my = imgData.utm_y - corners[i].x() * sin_y + corners[i].y() * cos_y;
                screenCorners[i] = toScreen(mx, my);
            }

            if (idx == selectedIdx) {
                painter.setPen(QPen(QColor(255, 170, 0), 2));
                painter.setBrush(QBrush(QColor(255, 170, 0, 30)));
            } else {
                painter.setPen(QPen(QColor(0, 200, 100, 100), 1));
                painter.setBrush(QBrush(QColor(0, 200, 100, 10)));
            }
            painter.drawPolygon(screenCorners, 4);
        }
    }

    // 5. Draw Flight Nodes (Circles)
    if (!droneImages.isEmpty()) {
        for (int i = 0; i < droneImages.size(); ++i) {
            QPointF sc = toScreen(droneImages[i].utm_x, droneImages[i].utm_y);
            
            // Highlight selected node
            if (i == selectedIdx) {
                painter.setPen(QPen(QColor(255, 170, 0), 2));
                painter.setBrush(QBrush(QColor(255, 200, 0)));
                painter.drawEllipse(sc, 8, 8);
            } else {
                painter.setPen(QPen(QColor(255, 255, 255), 1));
                painter.setBrush(QBrush(QColor(0, 150, 255)));
                painter.drawEllipse(sc, 5, 5);
            }
            
            // Draw label
            painter.setPen(QPen(Qt::white));
            painter.setFont(QFont("Arial", 8, QFont::Bold));
            painter.drawText(sc + QPointF(8, 4), QString::number(i + 18));
        }
    }
}

void MapCanvas::drawGrid(QPainter &painter) {
    QPen gridPen(QColor(60, 64, 79, 100), 1, Qt::SolidLine);
    painter.setPen(gridPen);

    double spacing = 50.0; // Grid every 50 meters
    double startX = std::floor(toMap(0, 0).x() / spacing) * spacing;
    double endX = std::floor(toMap(width(), 0).x() / spacing) * spacing;
    double startY = std::floor(toMap(0, height()).y() / spacing) * spacing;
    double endY = std::floor(toMap(0, 0).y() / spacing) * spacing;

    for (double gx = startX; gx <= endX; gx += spacing) {
        QPointF sc = toScreen(gx, originY);
        painter.drawLine(sc.x(), 0, sc.x(), height());
    }
    for (double gy = startY; gy <= endY; gy += spacing) {
        QPointF sc = toScreen(originX, gy);
        painter.drawLine(0, sc.y(), width(), sc.y());
    }
}

QColor MapCanvas::getColorForZ(double z) const {
    // Custom heightmap color ramp
    double t = (z - zMin) / (zMax - zMin + 0.001);
    t = std::max(0.0, std::min(1.0, t));

    if (t < 0.2) {
        // Deep blue to light blue (shoreline)
        return QColor::fromRgbF(0.1, 0.3, 0.6 + t * 2.0);
    } else if (t < 0.5) {
        // Yellow sand
        return QColor::fromRgbF(0.9, 0.8, 0.5);
    } else {
        // Green trees to dark brown/yellow hills
        double factor = (t - 0.5) / 0.5;
        int r = int(40 + factor * 100);
        int g = int(140 - factor * 40);
        int b = int(40 + factor * 10);
        return QColor(r, g, b);
    }
}

void MapCanvas::mousePressEvent(QMouseEvent *event) {
    if (event->button() == Qt::LeftButton) {
        lastMousePos = event->position();
        isPanning = true;

        // Selection hit-test
        QPointF clickMap = toMap(event->position().x(), event->position().y());
        double threshold = 3.0; // 3 meters selection radius
        int clickedIdx = -1;

        for (int i = 0; i < droneImages.size(); ++i) {
            double dist = std::hypot(droneImages[i].utm_x - clickMap.x(), droneImages[i].utm_y - clickMap.y());
            if (dist < threshold) {
                clickedIdx = i;
                break;
            }
        }

        if (clickedIdx != -1) {
            selectedIdx = clickedIdx;
            emit imageSelected(clickedIdx);
            update();
        }
    }
}

void MapCanvas::mouseMoveEvent(QMouseEvent *event) {
    QPointF mapPos = toMap(event->position().x(), event->position().y());

    // Elevation reading from GDAL DSM
    double elev = getElevationAtUtm(mapPos.x(), mapPos.y());
    QString elevStr = (elev != -9999.0) ? QString("Elev: %1 m").arg(elev, 0, 'f', 2) : "Elev: N/A";
    
    QString statusMsg = QString("UTM X: %1 m, UTM Y: %2 m | %3")
                        .arg(mapPos.x(), 0, 'f', 2)
                        .arg(mapPos.y(), 0, 'f', 2)
                        .arg(elevStr);

    emit statusMessage(statusMsg);

    if (isPanning && !lastMousePos.isNull()) {
        QPointF delta = event->position() - lastMousePos;
        panX += delta.x() / zoom;
        panY -= delta.y() / zoom; // Y screen is inverted
        lastMousePos = event->position();
        update();
    }
}

void MapCanvas::mouseReleaseEvent(QMouseEvent *event) {
    if (event->button() == Qt::LeftButton) {
        isPanning = false;
        lastMousePos = QPointF();
    }
}

void MapCanvas::wheelEvent(QWheelEvent *event) {
    QPointF mousePos = event->position();
    QPointF mapPos = toMap(mousePos.x(), mousePos.y());

    double factor = (event->angleDelta().y() > 0) ? 1.15 : 0.85;
    zoom = std::max(0.2, std::min(50.0, zoom * factor));

    QPointF newSc = toScreen(mapPos.x(), mapPos.y());
    panX += (mousePos.x() - newSc.x()) / zoom;
    panY -= (mousePos.y() - newSc.y()) / zoom;

    update();
}

bool MapCanvas::exportFootprintsToGeoJSON(const QString& outputPath) {
    if (droneImages.isEmpty() || !poCT_to_GPS) {
        return false;
    }

    QFile file(outputPath);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Text)) {
        return false;
    }

    QTextStream out(&file);

    // GeoJSON header
    out << "{\n";
    out << "  \"type\": \"FeatureCollection\",\n";
    out << "  \"features\": [\n";

    for (int idx = 0; idx < droneImages.size(); ++idx) {
        const auto& imgData = droneImages[idx];
        double h = imgData.relative_altitude;
        double W_ground = 2.0 * h * 0.857;
        double H_ground = 2.0 * h * 0.481;

        double yaw_rad = imgData.gimbal_yaw * M_PI / 180.0;
        double cos_y = std::cos(yaw_rad);
        double sin_y = std::sin(yaw_rad);

        // Local corners
        QPointF corners[4] = {
            QPointF(-W_ground/2.0, H_ground/2.0),
            QPointF(W_ground/2.0, H_ground/2.0),
            QPointF(W_ground/2.0, -H_ground/2.0),
            QPointF(-W_ground/2.0, -H_ground/2.0)
        };

        // Project local to UTM 15N and then to GPS Lat/Lon
        double gps_lon[5];
        double gps_lat[5];
        double gps_z[5] = {0, 0, 0, 0, 0};

        for (int i = 0; i < 4; ++i) {
            double mx = imgData.utm_x + corners[i].x() * cos_y + corners[i].y() * sin_y;
            double my = imgData.utm_y - corners[i].x() * sin_y + corners[i].y() * cos_y;

            double lon_val = mx;
            double lat_val = my;
            double z_val = 0.0;

            if (poCT_to_GPS->Transform(1, &lon_val, &lat_val, &z_val)) {
                gps_lon[i] = lon_val;
                gps_lat[i] = lat_val;
            } else {
                gps_lon[i] = mx;
                gps_lat[i] = my;
            }
        }
        gps_lon[4] = gps_lon[0];
        gps_lat[4] = gps_lat[0];

        // Format Feature
        out << "    {\n";
        out << "      \"type\": \"Feature\",\n";
        out << "      \"properties\": {\n";
        out << "        \"filename\": \"" << imgData.filename << "\",\n";
        out << "        \"latitude\": " << QString::number(imgData.latitude, 'f', 7) << ",\n";
        out << "        \"longitude\": " << QString::number(imgData.longitude, 'f', 7) << ",\n";
        out << "        \"altitude_m\": " << QString::number(imgData.relative_altitude, 'f', 1) << ",\n";
        out << "        \"yaw_deg\": " << QString::number(imgData.gimbal_yaw, 'f', 1) << "\n";
        out << "      },\n";
        out << "      \"geometry\": {\n";
        out << "        \"type\": \"Polygon\",\n";
        out << "        \"coordinates\": [[\n";
        for (int i = 0; i < 5; ++i) {
            out << "          [" << QString::number(gps_lon[i], 'f', 7) << ", " 
                << QString::number(gps_lat[i], 'f', 7) << "]";
            if (i < 4) out << ",\n";
        }
        out << "\n        ]]\n";
        out << "      }\n";
        out << "    }";

        if (idx < droneImages.size() - 1) {
            out << ",\n";
        } else {
            out << "\n";
        }
    }

    out << "  ]\n";
    out << "}\n";

    file.close();
    return true;
}
