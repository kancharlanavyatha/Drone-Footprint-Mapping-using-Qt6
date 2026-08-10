#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>
#include <QListWidget>
#include <QLabel>
#include <QCheckBox>
#include <QPushButton>
#include <QVector>
#include <QString>
#include <QGroupBox>
#include <QScrollArea>
#include <QTableWidget>
#include <QJsonArray>
#include <QJsonObject>

// Struct to store parsed GPS and attitude metadata for a single drone photo
struct DroneImage {
    QString filename;          // Name of the JPEG file
    double latitude;           // GPS Latitude (WGS 84)
    double longitude;          // GPS Longitude (WGS 84)
    double utm_x;              // Projected X coordinate in meters (UTM 15N)
    double utm_y;              // Projected Y coordinate in meters (UTM 15N)
    double relative_altitude;  // Flight height relative to takeoff point (meters)
    double absolute_altitude;  // Flight height above mean sea level (meters)
    double gimbal_pitch;       // Camera tilt angle (-90 is straight down)
    double gimbal_yaw;         // Camera orientation angle relative to North (0-360)
    double gimbal_roll;        // Camera roll angle
    QVector<QPointF> corners_utm; // 4 ground UTM corner coordinates
};

// Struct to store a single point in the 3D point cloud
struct Point3D {
    double x, y, z;            // UTM X, UTM Y, and Elevation Z (all in meters)
};

// Forward declaration of MapCanvas class (notifies compiler it exists)
class MapCanvas;

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

    // Sets the active selected image from outside (e.g. when canvas is clicked)
    void selectImage(int idx);

private slots:
    // Slot triggered when the user selects a different image in the sidebar list
    void listSelectionChanged(int idx);
    
    // Slot triggered when checking/unchecking layer checkboxes (updates map layers)
    void toggleLayers();
    
    // Slot triggered when clicking "Export GIS GeoJSON" (saves footprint coordinates)
    void exportGeoJSON();

private:
    void setupUi();            // Creates and positions the window widgets
    void applyDarkTheme();     // Applies custom styling (QSS) for a modern look
    void loadDatasets();       // Reads JSON and CSV data files from the disk

    // UI elements
    MapCanvas *canvas;         // The interactive map viewport
    QListWidget *listWidget;   // Sidebar list of images
    
    // Layer checkboxes
    QCheckBox *chkPc;          // Point cloud toggle
    QCheckBox *chkFp;          // Footprints toggle
    QCheckBox *chkPath;        // Flight path toggle
    QCheckBox *chkOverlay;     // Image warp overlay toggle
    
    // Summary labels (for quick reading)
    QLabel *lblFilename;
    QLabel *lblGps;
    QLabel *lblUtm;
    QLabel *lblAlt;
    
    // Table containing ALL metadata tags dynamically loaded from the pipeline JSON
    QTableWidget *tblMetadata;
    
    QLabel *lblPreview;        // Label displaying the photo thumbnail
    
    // Camera calibration UI
    QLabel *lblCameraSpecs;    // Displays camera sensor sizes & focal length
    QLabel *lblCalculatedFov;  // Displays calculated Horizontal/Vertical FOVs
    QPushButton *btnExportGeoJSON; // Button to save footprints to GeoJSON

    // Data lists
    QVector<DroneImage> droneImages; // Loaded list of all drone photos
    QVector<Point3D> points;         // Loaded list of point cloud points
    
    // Stores the raw parsed JSON array containing all telemetry and calculated attributes
    QJsonArray metadataArray;
};

#endif // MAINWINDOW_H
