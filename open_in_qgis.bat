@echo off
echo =================================================================
echo Launching Brighton Beach Drone Footprints and Aerial Photos in QGIS
echo =================================================================
set "QGIS_BIN=C:\Program Files\QGIS 3.44.12\bin\qgis-ltr.bat"
set "PROJECT=d:\DRDO\drone points\Brighton_Beach_Project.qgz"

if exist "%PROJECT%" (
    echo Opening pre-configured QGIS Project (Photos + Footprints + DEM)...
    start "" "%QGIS_BIN%" "%PROJECT%"
) else (
    echo Opening layers directly into QGIS...
    start "" "%QGIS_BIN%" "d:\DRDO\drone points\brighton_beach_mosaic.vrt" "d:\DRDO\drone points\footprints_pipeline.geojson" "d:\DRDO\drone points\dsm.tif"
)
