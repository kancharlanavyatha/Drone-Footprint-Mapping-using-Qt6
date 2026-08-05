#ifndef MAPCANVAS_H
#define MAPCANVAS_H

#include <QWidget>
#include <QPointF>
#include <QVector>
#include <QImage>
#include <QCache>
#include "mainwindow.h"
#include <gdal_priv.h>
#include <ogr_spatialref.h>

class MapCanvas : public QWidget {
    Q_OBJECT

public:
    explicit MapCanvas(QWidget *parent = nullptr);
    ~MapCanvas();

    // Sets up the points list, drone metadata list, and the path to the dsm.tif elevation model
    void setData(const QVector<Point3D>& points, const QVector<DroneImage>& droneImages, const QString& dsmPath);
    
    // Resets the zoom level and map panning position back to center
    void resetView();
    
    // Computes image corner footprint coordinates, converts them back to WGS84 GPS (Lat/Lon) using GDAL OGR, and writes them to a GeoJSON file
    bool exportFootprintsToGeoJSON(const QString& outputPath);

    // Layer visibility flags (controlled by GUI checkboxes)
    bool showPointCloud;
    bool showFlightPath;
    bool showFootprints;
    bool showImageOverlay;

    int selectedIdx;                 // Index of the selected drone image (-1 if none)
    QVector<Point3D> points;         // The 3D point cloud dataset
    QVector<DroneImage> droneImages; // Metadata list for all drone photos

signals:
    // Emitted when the user clicks near a drone marker (selects the image)
    void imageSelected(int idx);
    
    // Emitted when the mouse moves over the canvas to update coordinates/elevation in status bar
    void statusMessage(const QString& message);

protected:
    // Custom painting method (called by Qt when rendering the widget)
    void paintEvent(QPaintEvent *event) override;
    
    // Interactive mouse event handlers
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;
    void wheelEvent(QWheelEvent *event) override;

private:
    // Helper to convert physical map coordinates (meters) to screen pixel coordinates
    QPointF toScreen(double x, double y) const;
    
    // Helper to convert screen pixel coordinates back to physical map coordinates (meters)
    QPointF toMap(double u, double v) const;
    
    // Draws coordinate grid lines in the background
    void drawGrid(QPainter &painter);
    
    // Maps a point's elevation (Z value) to a QColor using a terrain color ramp
    QColor getColorForZ(double z) const;
    
    // Uses GDAL and OGR to query the elevation at a specific UTM 15N coordinate from the GeoTIFF raster
    double getElevationAtUtm(double x_utm, double y_utm);
    
    // Loads, downsamples, and caches a drone photo in memory to prevent lag
    QImage* loadCachedImage(const QString& filename);

    // View settings
    double zoom;                     // Screen pixels per physical meter
    double panX;                     // Panning offset in the horizontal direction (meters)
    double panY;                     // Panning offset in the vertical direction (meters)
    double originX;                  // Map center X coordinate
    double originY;                  // Map center Y coordinate

    // Dataset spatial bounds (meters)
    double xMin, xMax;
    double yMin, yMax;
    double zMin, zMax;

    // Mouse tracking variables for panning
    QPointF lastMousePos;
    bool isPanning;

    // Image Caching (automatically deletes least recently used images)
    QCache<QString, QImage> imageCache;

    // GDAL Dataset members
    GDALDataset *dsmDataset;         // Pointer to opened dsm.tif GeoTIFF file
    double dsmGeoTransform[6];       // Matrix mapping pixel grid coordinates to map coordinates
    int dsmWidth;                    // Image width of the raster grid
    int dsmHeight;                   // Image height of the raster grid
    GDALRasterBand *dsmBand;         // Raster band pointer to read elevation floats

    // Coordinate Transformations (using GDAL OGR library)
    OGRSpatialReference oSourceSRS; // Source CRS: UTM 15N (EPSG:32615) - actual local beach project
    OGRSpatialReference oGpsSRS;    // Target CRS: WGS 84 (EPSG:4326) - Lat/Lon GPS standard
    OGRSpatialReference oUtm10SRS;  // Target CRS: UTM 10N (EPSG:32610) - coordinate system used by dsm.tif
    OGRCoordinateTransformation *poCT_to_GPS;   // Transformer from UTM 15N to GPS Lat/Lon
    OGRCoordinateTransformation *poCT_to_UTM10; // Transformer from UTM 15N to UTM 10N
};

#endif // MAPCANVAS_H
