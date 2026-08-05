cmake_minimum_required(VERSION 3.16)
project(DroneMapper LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Enable automatic compilation of Qt files
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

# Find Qt6 components
find_package(Qt6 REQUIRED COMPONENTS Widgets)

# Find GDAL
list(APPEND CMAKE_PREFIX_PATH "C:/msys64/mingw64")
find_package(GDAL REQUIRED)

# Include directories
include_directories(${GDAL_INCLUDE_DIRS})

add_executable(DroneMapper
    main.cpp
    mainwindow.h
    mainwindow.cpp
    mapcanvas.h
    mapcanvas.cpp
)

target_link_libraries(DroneMapper PRIVATE
    Qt6::Widgets
    ${GDAL_LIBRARIES}
)
