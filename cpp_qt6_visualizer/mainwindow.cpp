#include "mainwindow.h"
#include "mapcanvas.h"
#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QSplitter>
#include <QGroupBox>
#include <QFile>
#include <QTextStream>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QPixmap>
#include <QStatusBar>
#include <QCoreApplication>
#include <QDir>
#include <QDebug>
#include <QHeaderView>
#include <QFileInfo>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent) {
    setWindowTitle("Drone Footprint Mapper & Point Cloud Visualizer (C++ GDAL)");
    resize(1250, 800); // More balanced visualizer window size

    applyDarkTheme();
    setupUi();
    loadDatasets();
}

MainWindow::~MainWindow() {
}

void MainWindow::setupUi() {
    QWidget *centralWidget = new QWidget(this);
    setCentralWidget(centralWidget);

    QHBoxLayout *mainLayout = new QHBoxLayout(centralWidget);
    mainLayout->setContentsMargins(10, 10, 10, 10);

    QSplitter *splitter = new QSplitter(Qt::Horizontal, this);
    mainLayout->addWidget(splitter);

    // Left Panel (Map Canvas)
    canvas = new MapCanvas(this);
    connect(canvas, &MapCanvas::imageSelected, this, &MainWindow::selectImage);
    connect(canvas, &MapCanvas::statusMessage, this, [this](const QString& msg) {
        statusBar()->showMessage(msg);
    });
    splitter->addWidget(canvas);

    // Right Scroll Area (to prevent window truncation on small screens)
    QScrollArea *scrollArea = new QScrollArea(this);
    scrollArea->setWidgetResizable(true);
    scrollArea->setFixedWidth(350); // Set fixed width for sidebar
    scrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scrollArea->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);

    QFrame *rightPanel = new QFrame(scrollArea);
    rightPanel->setObjectName("RightPanel");
    QVBoxLayout *rightLayout = new QVBoxLayout(rightPanel);
    rightLayout->setContentsMargins(12, 12, 12, 12);
    rightLayout->setSpacing(12);

    QLabel *titleLabel = new QLabel("DRONE FOOTPRINT MAP", rightPanel);
    titleLabel->setObjectName("PanelTitle");
    rightLayout->addWidget(titleLabel);

    // Layers visibility group
    QGroupBox *layerGroup = new QGroupBox("Layers", rightPanel);
    QVBoxLayout *layerLayout = new QVBoxLayout(layerGroup);
    chkPc = new QCheckBox("Point Cloud (downsampled)", layerGroup);
    chkFp = new QCheckBox("Image Footprints (rotated)", layerGroup);
    chkPath = new QCheckBox("Flight Path (dashed)", layerGroup);
    chkOverlay = new QCheckBox("Image Overlays (warped)", layerGroup);

    chkPc->setChecked(true);
    chkFp->setChecked(true);
    chkPath->setChecked(true);
    chkOverlay->setChecked(true);

    layerLayout->addWidget(chkPc);
    layerLayout->addWidget(chkFp);
    layerLayout->addWidget(chkPath);
    layerLayout->addWidget(chkOverlay);
    rightLayout->addWidget(layerGroup);

    connect(chkPc, &QCheckBox::checkStateChanged, this, &MainWindow::toggleLayers);
    connect(chkFp, &QCheckBox::checkStateChanged, this, &MainWindow::toggleLayers);
    connect(chkPath, &QCheckBox::checkStateChanged, this, &MainWindow::toggleLayers);
    connect(chkOverlay, &QCheckBox::checkStateChanged, this, &MainWindow::toggleLayers);

    // Selection dropdown list
    QGroupBox *selectionGroup = new QGroupBox("Select Drone Image", rightPanel);
    QVBoxLayout *selectionLayout = new QVBoxLayout(selectionGroup);
    listWidget = new QListWidget(selectionGroup);
    listWidget->setObjectName("ImageList");
    listWidget->setMinimumHeight(130);
    listWidget->setMaximumHeight(200);
    selectionLayout->addWidget(listWidget);
    rightLayout->addWidget(selectionGroup);

    connect(listWidget, &QListWidget::currentRowChanged, this, &MainWindow::listSelectionChanged);

    // Active Metadata Group
    QGroupBox *metaGroup = new QGroupBox("Active Metadata", rightPanel);
    QVBoxLayout *metaLayout = new QVBoxLayout(metaGroup);
    
    lblFilename = new QLabel("Image: Select an image...", metaGroup);
    lblGps = new QLabel("GPS: (lat, lon)", metaGroup);
    lblUtm = new QLabel("UTM 15N: (E, N)", metaGroup);
    lblAlt = new QLabel("Altitude: (Rel/Abs)", metaGroup);

    lblFilename->setWordWrap(true);
    lblGps->setWordWrap(true);
    lblUtm->setWordWrap(true);
    lblAlt->setWordWrap(true);

    metaLayout->addWidget(lblFilename);
    metaLayout->addWidget(lblGps);
    metaLayout->addWidget(lblUtm);
    metaLayout->addWidget(lblAlt);

    // Table for All Metadata tags (makes copyable and reads everything from ExifTool output)
    QLabel *lblTableTitle = new QLabel("<b>All Exif & Calculation Tags:</b>", metaGroup);
    metaLayout->addWidget(lblTableTitle);

    tblMetadata = new QTableWidget(metaGroup);
    tblMetadata->setColumnCount(2);
    tblMetadata->setMinimumHeight(220);
    tblMetadata->setHorizontalHeaderLabels(QStringList() << "Metadata Tag" << "Value");
    tblMetadata->horizontalHeader()->setStretchLastSection(true);
    tblMetadata->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    tblMetadata->verticalHeader()->setVisible(false); // Hide row indices
    tblMetadata->setEditTriggers(QAbstractItemView::NoEditTriggers); // Make read-only
    tblMetadata->setSelectionBehavior(QAbstractItemView::SelectRows);
    
    metaLayout->addWidget(tblMetadata);
    rightLayout->addWidget(metaGroup);

    // Camera & Calibration Group
    QGroupBox *cameraGroup = new QGroupBox("Camera & Calibration", rightPanel);
    QVBoxLayout *cameraLayout = new QVBoxLayout(cameraGroup);
    lblCameraSpecs = new QLabel("<b>Camera model:</b> DJI FC300S<br><b>Sensor:</b> 1/2.3\" CMOS (6.17 x 4.55 mm)<br><b>Focal Length:</b> 3.61 mm (20mm eq.)<br><b>Photo size:</b> 4000 x 3000 px", cameraGroup);
    lblCalculatedFov = new QLabel("<b>Calculated FOV:</b><br>Horizontal FOV: ~81.0°<br>Vertical FOV: ~64.4°", cameraGroup);
    btnExportGeoJSON = new QPushButton("Export GIS GeoJSON", cameraGroup);
    
    btnExportGeoJSON->setStyleSheet("background-color: #00aa55; color: white; font-weight: bold; padding: 8px; border-radius: 4px;");
    connect(btnExportGeoJSON, &QPushButton::clicked, this, &MainWindow::exportGeoJSON);
    
    cameraLayout->addWidget(lblCameraSpecs);
    cameraLayout->addWidget(lblCalculatedFov);
    cameraLayout->addWidget(btnExportGeoJSON);
    rightLayout->addWidget(cameraGroup);

    // Thumbnail preview
    QGroupBox *previewGroup = new QGroupBox("Thumbnail Preview", rightPanel);
    QVBoxLayout *previewLayout = new QVBoxLayout(previewGroup);
    lblPreview = new QLabel("No Image Selected", previewGroup);
    lblPreview->setMinimumSize(250, 180);
    lblPreview->setAlignment(Qt::AlignCenter);
    lblPreview->setObjectName("PreviewArea");
    previewLayout->addWidget(lblPreview);
    rightLayout->addWidget(previewGroup);

    // Reset view
    QPushButton *btnReset = new QPushButton("Reset View", rightPanel);
    connect(btnReset, &QPushButton::clicked, canvas, &MapCanvas::resetView);
    rightLayout->addWidget(btnReset);

    // Setup scroll widget content
    scrollArea->setWidget(rightPanel);
    splitter->addWidget(scrollArea);

    // Set splitter sizes (Left Map Canvas gets most space)
    splitter->setSizes(QList<int>() << 900 << 350);

    // Status bar
    setStatusBar(new QStatusBar(this));
    statusBar()->showMessage("Ready");
}

void MainWindow::loadDatasets() {
    // Resolve project dataset folder
    QString projectDir = QCoreApplication::applicationDirPath();
    QDir dir(projectDir);
    while (dir.cdUp()) {
        if (dir.exists("drone_dataset_brighton_beach-master")) {
            break;
        }
    }
    QString dsmPath = dir.absoluteFilePath("drone_dataset_brighton_beach-master/dsm.tif");
    QString csvPath = dir.absoluteFilePath("drone_dataset_brighton_beach-master/points_downsampled.csv");
    
    // Path to the pipeline output metadata JSON (contains ALL EXIF tags)
    QString metaPath = dir.absoluteFilePath("footprint_pipeline/output/calculated_footprints.json");

    // Fallbacks to absolute paths if directory resolution fails
    if (!QFile::exists(csvPath)) {
        dsmPath = "d:/DRDO/drone points/drone_dataset_brighton_beach-master/dsm.tif";
        csvPath = "d:/DRDO/drone points/drone_dataset_brighton_beach-master/points_downsampled.csv";
        metaPath = "d:/DRDO/drone points/footprint_pipeline/output/calculated_footprints.json";
    }
    
    // Secondary fallback to original metadata if pipeline JSON is not found
    if (!QFile::exists(metaPath)) {
        metaPath = "d:/DRDO/drone points/drone_dataset_brighton_beach-master/images_metadata.json";
    }

    // 1. Read CSV Points
    QFile csvFile(csvPath);
    if (csvFile.open(QIODevice::ReadOnly | QIODevice::Text)) {
        QTextStream stream(&csvFile);
        // Skip header line (X,Y,Z)
        if (!stream.atEnd()) {
            stream.readLine();
        }
        while (!stream.atEnd()) {
            QString line = stream.readLine();
            QStringList parts = line.split(',');
            if (parts.size() >= 3) {
                bool okX = false, okY = false, okZ = false;
                double x = parts[0].toDouble(&okX);
                double y = parts[1].toDouble(&okY);
                double z = parts[2].toDouble(&okZ);
                if (okX && okY && okZ) {
                    Point3D pt;
                    pt.x = x;
                    pt.y = y;
                    pt.z = z;
                    points.append(pt);
                }
            }
        }
        csvFile.close();
        qDebug() << "Successfully loaded" << points.size() << "terrain points.";
    } else {
        qDebug() << "Failed to open point cloud CSV file at:" << csvPath;
    }

    // 2. Read JSON Metadata (Full pipeline metadata or fallback)
    QFile file(metaPath);
    if (file.open(QIODevice::ReadOnly)) {
        QByteArray data = file.readAll();
        QJsonDocument doc = QJsonDocument::fromJson(data);
        metadataArray = doc.array();

        for (int i = 0; i < metadataArray.size(); ++i) {
            QJsonObject obj = metadataArray[i].toObject();
            DroneImage di;
            
            // Handle both pipeline structure and fallback structure
            if (obj.contains("SourceFile")) {
                di.filename = QFileInfo(obj["SourceFile"].toString()).fileName();
                di.latitude = obj["GPSLatitude"].toDouble();
                di.longitude = obj["GPSLongitude"].toDouble();
                di.utm_x = obj["utm_x"].toDouble();
                di.utm_y = obj["utm_y"].toDouble();
                di.relative_altitude = obj["RelativeAltitude"].toVariant().toDouble();
                di.absolute_altitude = obj["GPSAltitude"].toDouble();
                di.gimbal_pitch = obj["GimbalPitchDegree"].toDouble();
                di.gimbal_yaw = obj["GimbalYawDegree"].toVariant().toDouble();
                di.gimbal_roll = obj["GimbalRollDegree"].toVariant().toDouble();
                
                if (obj.contains("corners_utm")) {
                    QJsonArray corners = obj["corners_utm"].toArray();
                    for (int c = 0; c < corners.size(); ++c) {
                        QJsonArray pt = corners[c].toArray();
                        if (pt.size() >= 2) {
                            di.corners_utm.append(QPointF(pt[0].toDouble(), pt[1].toDouble()));
                        }
                    }
                }
            } else {
                di.filename = obj["filename"].toString();
                di.latitude = obj["latitude"].toDouble();
                di.longitude = obj["longitude"].toDouble();
                di.utm_x = obj["utm_x"].toDouble();
                di.utm_y = obj["utm_y"].toDouble();
                di.relative_altitude = obj["relative_altitude"].toDouble();
                di.absolute_altitude = obj["absolute_altitude"].toDouble();
                di.gimbal_pitch = obj["gimbal_pitch"].toDouble();
                di.gimbal_yaw = obj["gimbal_yaw"].toDouble();
                di.gimbal_roll = obj["gimbal_roll"].toDouble();
            }

            // Fallback corners calculation if corners_utm was not loaded
            if (di.corners_utm.size() < 4) {
                double W_ground = 2.0 * di.relative_altitude * 0.857;
                double H_ground = 2.0 * di.relative_altitude * 0.481;
                double yaw_rad = di.gimbal_yaw * M_PI / 180.0;
                double cos_y = std::cos(yaw_rad);
                double sin_y = std::sin(yaw_rad);
                QPointF local_corners[4] = {
                    QPointF(-W_ground/2.0, H_ground/2.0),
                    QPointF(W_ground/2.0, H_ground/2.0),
                    QPointF(W_ground/2.0, -H_ground/2.0),
                    QPointF(-W_ground/2.0, -H_ground/2.0)
                };
                for (int c = 0; c < 4; ++c) {
                    double mx = di.utm_x + local_corners[c].x() * cos_y + local_corners[c].y() * sin_y;
                    double my = di.utm_y - local_corners[c].x() * sin_y + local_corners[c].y() * cos_y;
                    di.corners_utm.append(QPointF(mx, my));
                }
            }

            droneImages.append(di);

            QString labelText = QString("Image %1 (%2)").arg(i + 18).arg(di.filename);
            listWidget->addItem(labelText);
        }
        file.close();
        qDebug() << "Successfully loaded" << droneImages.size() << "drone image positions.";
    } else {
        qDebug() << "Failed to open metadata JSON file at:" << metaPath;
    }

    // Set data into map canvas
    canvas->setData(points, droneImages, dsmPath);
}

void MainWindow::listSelectionChanged(int idx) {
    if (idx < 0 || idx >= droneImages.size()) return;

    canvas->selectedIdx = idx;
    canvas->update();

    const auto& di = droneImages[idx];

    // Update quick-read summary labels
    lblFilename->setText(QString("<b>Image:</b> %1").arg(di.filename));
    lblGps->setText(QString("<b>GPS:</b> Lat: %1, Lon: %2")
                    .arg(di.latitude, 0, 'f', 6)
                    .arg(di.longitude, 0, 'f', 6));
    lblUtm->setText(QString("<b>UTM 15N:</b> E: %1 m, N: %2 m")
                    .arg(di.utm_x, 0, 'f', 2)
                    .arg(di.utm_y, 0, 'f', 2));
    lblAlt->setText(QString("<b>Altitude:</b> Rel: %1 m, Abs: %2 m")
                    .arg(di.relative_altitude, 0, 'f', 1)
                    .arg(di.absolute_altitude, 0, 'f', 1));

    // Populate the QTableWidget with ALL keys/values from the JSON object
    tblMetadata->setRowCount(0);
    if (idx < metadataArray.size()) {
        QJsonObject obj = metadataArray[idx].toObject();
        int row = 0;
        for (auto it = obj.constBegin(); it != obj.constEnd(); ++it) {
            QString key = it.key();
            QJsonValue val = it.value();
            
            // Format values nicely based on type
            QString valStr;
            if (val.isArray()) {
                // Format coordinates corners arrays
                QJsonArray subArr = val.toArray();
                QStringList coordStrings;
                for (int c = 0; c < subArr.size(); ++c) {
                    if (subArr[c].isArray()) {
                        QJsonArray pt = subArr[c].toArray();
                        if (pt.size() >= 2) {
                            coordStrings.append(QString("[%1, %2]").arg(pt[0].toVariant().toDouble(), 0, 'f', 2).arg(pt[1].toVariant().toDouble(), 0, 'f', 2));
                        }
                    }
                }
                valStr = QString("[%1]").arg(coordStrings.join(", "));
            } else if (val.isObject()) {
                QJsonDocument tempDoc(val.toObject());
                valStr = tempDoc.toJson(QJsonDocument::Compact);
            } else if (val.isDouble()) {
                valStr = QString::number(val.toDouble(), 'f', 4);
            } else {
                valStr = val.toVariant().toString();
            }

            tblMetadata->insertRow(row);
            
            // Key Cell
            QTableWidgetItem *keyItem = new QTableWidgetItem(key);
            keyItem->setFlags(keyItem->flags() ^ Qt::ItemIsEditable); // Make copyable but read-only
            tblMetadata->setItem(row, 0, keyItem);
            
            // Value Cell
            QTableWidgetItem *valItem = new QTableWidgetItem(valStr);
            valItem->setFlags(valItem->flags() ^ Qt::ItemIsEditable); // Make copyable but read-only
            tblMetadata->setItem(row, 1, valItem);
            
            row++;
        }
    }

    // Load Preview Image
    QString projectDir = QCoreApplication::applicationDirPath();
    QDir dir(projectDir);
    while (dir.cdUp()) {
        if (dir.exists("drone_dataset_brighton_beach-master")) {
            break;
        }
    }
    QString imgPath = dir.absoluteFilePath(QString("drone_dataset_brighton_beach-master/images/%1").arg(di.filename));
    if (!QFile::exists(imgPath)) {
        imgPath = QString("d:/DRDO/drone points/drone_dataset_brighton_beach-master/images/%1").arg(di.filename);
    }

    QPixmap pix(imgPath);
    if (!pix.isNull()) {
        lblPreview->setPixmap(pix.scaled(280, 200, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    } else {
        lblPreview->setText("Preview Load Error");
    }
}

void MainWindow::selectImage(int idx) {
    if (idx >= 0 && idx < droneImages.size()) {
        listWidget->setCurrentRow(idx);
    }
}

void MainWindow::toggleLayers() {
    canvas->showPointCloud = chkPc->isChecked();
    canvas->showFootprints = chkFp->isChecked();
    canvas->showFlightPath = chkPath->isChecked();
    canvas->showImageOverlay = chkOverlay->isChecked();
    canvas->update();
}

void MainWindow::exportGeoJSON() {
    QString projectDir = QCoreApplication::applicationDirPath();
    QDir dir(projectDir);
    while (dir.cdUp()) {
        if (dir.exists("drone_dataset_brighton_beach-master")) {
            break;
        }
    }
    QString outputPath = dir.absoluteFilePath("drone_dataset_brighton_beach-master/footprints.geojson");
    
    // Fallback if directory search fails
    if (!QDir(dir.absoluteFilePath("drone_dataset_brighton_beach-master")).exists()) {
        outputPath = "d:/DRDO/drone points/drone_dataset_brighton_beach-master/footprints.geojson";
    }

    if (canvas->exportFootprintsToGeoJSON(outputPath)) {
        statusBar()->showMessage(QString("Saved footprint GeoJSON to: %1").arg(outputPath), 5000);
    } else {
        statusBar()->showMessage("Error exporting GeoJSON!", 5000);
    }
}

void MainWindow::applyDarkTheme() {
    QString qss = R"(
        QMainWindow {
            background-color: #1a1c23;
        }
        QScrollArea {
            border: none;
            background-color: #212431;
        }
        QScrollBar:vertical {
            border: none;
            background-color: #1a1c23;
            width: 10px;
            margin: 0px 0px 0px 0px;
        }
        QScrollBar::handle:vertical {
            background-color: #3c404f;
            min-height: 20px;
            border-radius: 5px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: #33b3ff;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
            background: none;
        }
        QFrame#RightPanel {
            background-color: #212431;
            border-left: 1px solid #3c404f;
        }
        QLabel {
            color: #d1d4e0;
            font-size: 12px;
        }
        QLabel#PanelTitle {
            color: #33b3ff;
            font-size: 16px;
            font-weight: bold;
            border-bottom: 2px solid #33b3ff;
            padding-bottom: 5px;
        }
        QGroupBox {
            color: #33b3ff;
            font-weight: bold;
            border: 1px solid #3c404f;
            border-radius: 6px;
            margin-top: 10px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 5px;
        }
        QCheckBox {
            color: #d1d4e0;
            spacing: 8px;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
        }
        QListWidget {
            background-color: #15161b;
            border: 1px solid #3c404f;
            border-radius: 4px;
            color: #d1d4e0;
        }
        QListWidget::item {
            padding: 6px 10px;
            border-bottom: 1px solid #1a1c23;
        }
        QListWidget::item:selected {
            background-color: #33b3ff;
            color: #111215;
            font-weight: bold;
        }
        QTableWidget {
            background-color: #15161b;
            color: #d1d4e0;
            gridline-color: #3c404f;
            border: 1px solid #3c404f;
            border-radius: 4px;
        }
        QTableWidget::item {
            padding: 4px;
        }
        QTableWidget::item:selected {
            background-color: #33b3ff;
            color: #111215;
            font-weight: bold;
        }
        QHeaderView::section {
            background-color: #1a1c23;
            color: #33b3ff;
            padding: 4px;
            border: 1px solid #3c404f;
            font-weight: bold;
        }
        QPushButton {
            background-color: #007acc;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 8px 15px;
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
    )";
    setStyleSheet(qss);
}
