import json
import math
from pyproj import Transformer

def compute_ground_coverage_and_corners(fov_metadata, output_json):
    """
    Workflow Step 7 & 8: Compute Ground Coverage and Bounding Corners
    - Ground coverage based on altitude and FOVs
    - Corner projections with gimbal yaw rotation
    - UTM coordinate conversion (GPS -> UTM 15N)
    """
    print("[Step 3] Computing ground coverage and 4 corner coordinates...")
    
    # Transformer for coordinate systems (GPS degree -> UTM 15N meters)
    transformer = Transformer.from_crs("epsg:4326", "epsg:32615", always_xy=True)
    
    footprint_data = []
    for item in fov_metadata:
        lat = float(item.get("GPSLatitude", 0.0))
        lon = float(item.get("GPSLongitude", 0.0))
        h = float(item.get("RelativeAltitude", 0.0))
        yaw = float(item.get("GimbalYawDegree", 0.0))
        yaw_rad = math.radians(yaw)
        
        # Project camera center to UTM Zone 15N (meters)
        utm_x, utm_y = transformer.transform(lon, lat)
        
        # Step 7: Ground Coverage width & height
        w_ground = 2.0 * h * math.tan(item["fov_h_rad"] / 2.0)
        h_ground = 2.0 * h * math.tan(item["fov_v_rad"] / 2.0)
        
        # Local corners relative to camera center (0,0)
        local_corners = [
            (-w_ground / 2.0, h_ground / 2.0),
            (w_ground / 2.0, h_ground / 2.0),
            (w_ground / 2.0, -h_ground / 2.0),
            (-w_ground / 2.0, -h_ground / 2.0)
        ]
        
        # Step 8: Compute 4 Ground Corners (using yaw rotation)
        cos_y = math.cos(yaw_rad)
        sin_y = math.sin(yaw_rad)
        
        corners_utm = []
        for cx, cy in local_corners:
            mx = utm_x + cx * cos_y + cy * sin_y
            my = utm_y - cx * sin_y + cy * cos_y
            corners_utm.append((mx, my))
            
        footprint_item = item.copy()
        footprint_item["utm_x"] = utm_x
        footprint_item["utm_y"] = utm_y
        footprint_item["ground_width_m"] = w_ground
        footprint_item["ground_height_m"] = h_ground
        footprint_item["corners_utm"] = corners_utm
        footprint_data.append(footprint_item)
        
    with open(output_json, "w") as f:
        json.dump(footprint_data, f, indent=4)
        
    print(f" -> Computed footprint corners saved to: {output_json}")
    return footprint_data
