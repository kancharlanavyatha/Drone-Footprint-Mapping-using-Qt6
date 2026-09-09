import os
import sys
from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsCoordinateReferenceSystem,
    QgsSingleSymbolRenderer,
    QgsFillSymbol,
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling,
    QgsTextFormat,
    QgsTextBufferSettings
)
from PyQt5.QtGui import QColor

# Initialize QGIS Application in headless mode
QgsApplication.setPrefixPath(r"C:\Program Files\QGIS 3.44.12\apps\qgis-ltr", True)
qgs = QgsApplication([], False)
qgs.initQgis()

project = QgsProject.instance()
project.clear()
project.setTitle("Brighton Beach UAV Footprint & Orthomosaic Mapping")
project.setCrs(QgsCoordinateReferenceSystem("EPSG:32615"))

base_dir = r"d:\DRDO\drone points"
dsm_path = os.path.join(base_dir, "dsm.tif")
mosaic_path = os.path.join(base_dir, "brighton_beach_mosaic.vrt")
geojson_path = os.path.join(base_dir, "footprints_pipeline.geojson")

# 1. Add DSM Elevation Layer
dsm_layer = QgsRasterLayer(dsm_path, "Terrain Elevation (DSM)", "gdal")
if dsm_layer.isValid():
    project.addMapLayer(dsm_layer, False)
    print("Added DSM layer.")
else:
    print("Failed to load DSM layer.")

# 2. Add Orthomosaic Aerial Photo Layer
mosaic_layer = QgsRasterLayer(mosaic_path, "Drone Aerial Photo Mosaic (18 Photos)", "gdal")
if mosaic_layer.isValid():
    project.addMapLayer(mosaic_layer, False)
    print("Added Mosaic layer.")
else:
    print("Failed to load Mosaic layer.")

# 3. Add Vector Footprints Layer
footprint_layer = QgsVectorLayer(geojson_path, "Drone Footprint Polygons", "ogr")
if footprint_layer.isValid():
    # Setup styling: Cyan outline, semi-transparent fill
    symbol = QgsFillSymbol.createSimple({
        "color": "0,229,255,40",
        "outline_color": "0,229,255,255",
        "outline_width": "0.7"
    })
    footprint_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    
    # Setup labels: filename with dark halo
    label_settings = QgsPalLayerSettings()
    label_settings.fieldName = "filename"
    text_format = QgsTextFormat()
    from PyQt5.QtGui import QFont
    font = QFont("Arial", 9)
    font.setBold(True)
    text_format.setFont(font)
    text_format.setSize(9)
    text_format.setColor(QColor(255, 255, 255))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(1.2)
    buffer.setColor(QColor(0, 0, 0, 200))
    text_format.setBuffer(buffer)
    label_settings.setFormat(text_format)
    footprint_layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))
    footprint_layer.setLabelsEnabled(True)
    
    # Setup HTML Map Tip for interactive photo previews
    tip_html = """
    <div style="font-family: Arial; font-size: 12px; background: #222; color: #eee; padding: 10px; border-radius: 6px; border: 1px solid #00e5ff;">
      <h3 style="margin: 0 0 5px 0; color: #00e5ff;">[% "filename" %]</h3>
      <table style="width: 100%; font-size: 11px; margin-bottom: 8px;">
        <tr><td><b>Altitude:</b></td><td>[% "altitude_m" %] m</td></tr>
        <tr><td><b>Yaw:</b></td><td>[% "yaw_deg" %]°</td></tr>
        <tr><td><b>Lat, Lon:</b></td><td>[% round("latitude", 5) %], [% round("longitude", 5) %]</td></tr>
      </table>
      <img src="file:///d:/DRDO/drone points/drone_dataset_brighton_beach-master/images/[% "filename" %]" width="360" style="border-radius: 4px; border: 1px solid #444;" />
    </div>
    """
    footprint_layer.setMapTipTemplate(tip_html)
    
    project.addMapLayer(footprint_layer, False)
    print("Added Footprint layer with interactive Map Tip.")
else:
    print("Failed to load Footprint layer.")

# Layer tree ordering (Top to Bottom): Footprints -> Aerial Photos -> DSM Elevation
root = project.layerTreeRoot()
if footprint_layer.isValid():
    root.addLayer(footprint_layer)
if mosaic_layer.isValid():
    root.addLayer(mosaic_layer)
if dsm_layer.isValid():
    root.addLayer(dsm_layer)

project_file = os.path.join(base_dir, "Brighton_Beach_Project.qgz")
success = project.write(project_file)
print(f"Project written to: {project_file} (Success: {success})")

qgs.exitQgis()
