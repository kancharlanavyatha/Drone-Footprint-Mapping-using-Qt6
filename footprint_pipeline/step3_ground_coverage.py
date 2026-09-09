import json
import math
import os
import numpy as np
from pyproj import Transformer
from step3b_dem_raytracer import DemRayTracer

def compute_camera_matrix(w_px, h_px, f_mm, sw_mm, sh_mm):
    """
    Constructs the 3x3 pinhole camera intrinsic matrix K and its inverse K_inv.
    """
    fx = f_mm * w_px / sw_mm
    fy = f_mm * h_px / sh_mm
    cx = w_px / 2.0
    cy = h_px / 2.0
    
    K = np.array([
        [fx, 0.0, cx],
        [0.0, fy, cy],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64)
    
    K_inv = np.array([
        [1.0 / fx, 0.0, -cx / fx],
        [0.0, 1.0 / fy, -cy / fy],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64)
    
    return K, K_inv

def compute_corner_rays_camera(w_px, h_px, K_inv):
    """
    Unprojects the 4 image corners into 3D unit ray vectors in camera coordinates:
    Order: Top-Left (0,0), Top-Right (W,0), Bottom-Right (W,H), Bottom-Left (0,H)
    """
    corners_px = np.array([
        [0.0, 0.0, 1.0],
        [w_px, 0.0, 1.0],
        [w_px, h_px, 1.0],
        [0.0, h_px, 1.0]
    ], dtype=np.float64)
    
    rays_c = []
    for p in corners_px:
        v = K_inv @ p
        norm = np.linalg.norm(v)
        rays_c.append(v / norm)
    return np.array(rays_c, dtype=np.float64)

def compute_camera_to_world_rotation(yaw_deg, pitch_deg, roll_deg):
    """
    Constructs the 3D rotation matrix R_WC transforming rays from
    camera coordinates into UTM East-North-Up (ENU) world coordinates.
    """
    yaw_rad = math.radians(yaw_deg)
    roll_rad = math.radians(roll_deg)
    # Pitch tilt relative to nadir (-90 degrees)
    delta_pitch = math.radians(pitch_deg + 90.0)
    
    # Base Nadir camera alignment (yaw=0, pitch=-90, roll=0)
    # +X_c (Right) -> +X_w (East)
    # +Y_c (Down)  -> -Y_w (South, so image top faces North)
    # +Z_c (Look)  -> -Z_w (Down)
    R0 = np.array([
        [1.0,  0.0,  0.0],
        [0.0, -1.0,  0.0],
        [0.0,  0.0, -1.0]
    ], dtype=np.float64)
    
    # Pitch rotation around camera horizontal X axis
    cp = math.cos(delta_pitch)
    sp = math.sin(delta_pitch)
    R_pitch = np.array([
        [1.0, 0.0,  0.0],
        [0.0,  cp, -sp],
        [0.0,  sp,  cp]
    ], dtype=np.float64)
    
    # Roll rotation around camera optical Z axis
    cr = math.cos(roll_rad)
    sr = math.sin(roll_rad)
    R_roll = np.array([
        [cr, -sr, 0.0],
        [sr,  cr, 0.0],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64)
    
    # Yaw rotation around World vertical Z axis (clockwise from North)
    cy = math.cos(yaw_rad)
    sy = math.sin(yaw_rad)
    R_yaw = np.array([
        [cy,  sy, 0.0],
        [-sy, cy, 0.0],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64)
    
    return R_yaw @ R0 @ R_pitch @ R_roll

def compute_ground_coverage_and_corners(fov_metadata, output_json, dem_path=None):
    """
    Workflow Step 7 & 8: 3D Pinhole Ray Casting & Ground Coverage
    - Casts 3D rays from image corners using camera intrinsic matrix K
    - Rotates rays to UTM world space using full Yaw, Pitch, Roll orientation
    - Intersects rays with Digital Elevation Model (DEM) or ground datum
    """
    print("[Step 3] Computing 3D Pinhole Ray-Casting & Footprint Corners...")
    
    # Initialize DEM Ray Tracer if available
    dem_tracer = None
    if dem_path and os.path.exists(dem_path):
        dem_tracer = DemRayTracer(dem_path)
        if not dem_tracer.loaded:
            dem_tracer = None
            
    # Transformer from GPS (WGS 84) to UTM Zone 15N
    transformer = Transformer.from_crs("epsg:4326", "epsg:32615", always_xy=True)
    
    footprint_data = []
    for item in fov_metadata:
        lat = float(item.get("GPSLatitude", 0.0))
        lon = float(item.get("GPSLongitude", 0.0))
        rel_alt = float(item.get("RelativeAltitude", 0.0))
        abs_alt = float(item.get("GPSAltitude", 0.0))
        yaw = float(item.get("GimbalYawDegree", 0.0))
        pitch = float(item.get("GimbalPitchDegree", -90.0))
        roll = float(item.get("GimbalRollDegree", 0.0))
        
        # Project camera center to UTM Zone 15N
        utm_x, utm_y = transformer.transform(lon, lat)
        
        # Determine camera height above ground datum
        cam_z = abs_alt if abs_alt != 0.0 else rel_alt
        ground_datum_z = abs_alt - rel_alt if abs_alt != 0.0 else 0.0
        
        # Camera 3D center in UTM 15N
        C_w = np.array([utm_x, utm_y, cam_z], dtype=np.float64)
        
        # 1. Build Camera Intrinsics
        w_px = float(item.get("ImageWidth", 4000.0))
        h_px = float(item.get("ImageHeight", 2250.0))
        f_mm = float(item.get("FocalLength", 3.6))
        sw_mm = float(item.get("sensor_width_mm", 6.17))
        sh_mm = float(item.get("sensor_height_mm", 3.470625))
        
        K, K_inv = compute_camera_matrix(w_px, h_px, f_mm, sw_mm, sh_mm)
        rays_c = compute_corner_rays_camera(w_px, h_px, K_inv)
        
        # 2. Camera to World 3D Rotation
        R_wc = compute_camera_to_world_rotation(yaw, pitch, roll)
        
        # 3. Intersect 4 Corner Rays with Ground / DEM
        corners_utm_2d = []
        corners_utm_3d = []
        
        for r_c in rays_c:
            r_w = R_wc @ r_c
            pt_ground = None
            
            # Try DEM intersection first
            if dem_tracer:
                pt_ground = dem_tracer.intersect_ray(C_w, r_w)
                
            # Fallback to horizontal ground plane intersection
            if pt_ground is None:
                if r_w[2] < -1e-5:
                    lam = (ground_datum_z - C_w[2]) / r_w[2]
                    pt_ground = C_w + lam * r_w
                else:
                    # Ray pointing horizontally or up
                    pt_ground = C_w + 100.0 * r_w
                    
            corners_utm_2d.append([float(pt_ground[0]), float(pt_ground[1])])
            corners_utm_3d.append([float(pt_ground[0]), float(pt_ground[1]), float(pt_ground[2])])
            
        # Calculate approximate dimensions for compatibility
        top_w = float(np.linalg.norm(np.array(corners_utm_2d[1]) - np.array(corners_utm_2d[0])))
        bot_w = float(np.linalg.norm(np.array(corners_utm_2d[2]) - np.array(corners_utm_2d[3])))
        avg_w = 0.5 * (top_w + bot_w)
        
        left_h = float(np.linalg.norm(np.array(corners_utm_2d[3]) - np.array(corners_utm_2d[0])))
        right_h = float(np.linalg.norm(np.array(corners_utm_2d[2]) - np.array(corners_utm_2d[1])))
        avg_h = 0.5 * (left_h + right_h)
        
        footprint_item = item.copy()
        footprint_item["utm_x"] = utm_x
        footprint_item["utm_y"] = utm_y
        footprint_item["camera_z"] = cam_z
        footprint_item["ground_width_m"] = avg_w
        footprint_item["ground_height_m"] = avg_h
        footprint_item["corners_utm"] = corners_utm_2d
        footprint_item["corners_utm_3d"] = corners_utm_3d
        footprint_item["method"] = "3D_Pinhole_RayCasting_DEM" if dem_tracer else "3D_Pinhole_RayCasting_Plane"
        footprint_data.append(footprint_item)
        
    with open(output_json, "w") as f:
        json.dump(footprint_data, f, indent=4)
        
    print(f" -> Computed 3D ray-cast footprint corners saved to: {output_json}")
    return footprint_data
