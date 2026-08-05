#include <QApplication>
#include "mainwindow.h"
#include <gdal_priv.h>

int main(int argc, char *argv[]) {
    // Register GDAL drivers
    GDALAllRegister();

    QApplication app(argc, argv);
    MainWindow window;
    window.show();
    return app.exec();
}
