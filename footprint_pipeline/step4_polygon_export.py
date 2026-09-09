import json
import os
from pyproj import Transformer

def build_polygon_and_export(footprint_data, output_geojson):
    """
    Workflow Step 9 & 10: Build Polygon and Export to GIS Format (GeoJSON)
    - Projects UTM corners back to standard GPS (WGS84)
    - Formats polygons into a standardized GeoJSON FeatureCollection
    """
    print("[Step 4] Building polygons and exporting GeoJSON...")
    
    # Transformer: UTM Zone 15N (meters) -> GPS (Lat/Lon degrees)
    transformer = Transformer.from_crs("epsg:32615", "epsg:4326", always_xy=True)
    
    features = []
    for item in footprint_data:
        filename = os.path.basename(item.get("SourceFile", ""))
        
        # Project corners back to standard GPS degrees (with elevation Z for 3D GIS)
        gps_coords = []
        has_3d = "corners_utm_3d" in item and len(item["corners_utm_3d"]) == 4
        
        for i in range(4):
            mx = item["corners_utm"][i][0]
            my = item["corners_utm"][i][1]
            lon, lat = transformer.transform(mx, my)
            if has_3d:
                elev = round(float(item["corners_utm_3d"][i][2]), 2)
                gps_coords.append([round(lon, 7), round(lat, 7), elev])
            else:
                gps_coords.append([round(lon, 7), round(lat, 7)])
            
        # Close the loop
        gps_coords.append(gps_coords[0])
        
        # Step 9 & 10: Build GeoJSON structure
        feature = {
            "type": "Feature",
            "properties": {
                "filename": filename,
                "latitude": float(item.get("GPSLatitude", 0.0)),
                "longitude": float(item.get("GPSLongitude", 0.0)),
                "altitude_m": float(item.get("RelativeAltitude", 0.0)),
                "yaw_deg": float(item.get("GimbalYawDegree", 0.0))
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [gps_coords]
            }
        }
        features.append(feature)
        
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    
    with open(output_geojson, "w") as f:
        json.dump(geojson, f, indent=4)
        
    print(f" -> Successfully exported GeoJSON file: {output_geojson}")
    return geojson
