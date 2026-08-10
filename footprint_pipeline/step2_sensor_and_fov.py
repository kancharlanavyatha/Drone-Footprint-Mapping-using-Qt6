import math

def calculate_sensor_and_fov(raw_metadata):
    """
    Workflow Step 5 & 6: Determine Sensor Size and Calculate FOV
    - DJI Phantom 3 sensor: 6.17 mm x 4.55 mm
    - Calculates Horizontal and Vertical FOVs using focal length
    """
    print("[Step 2] Determining Sensor Size and calculating FOV...")
    sensor_w = 6.17  # mm
    
    processed_metadata = []
    for item in raw_metadata:
        f = float(item.get("FocalLength", 3.61)) # Step 4 Focal Length
        
        # Adjust sensor height dynamically based on image crop aspect ratio
        img_w = float(item.get("ImageWidth", 4000.0))
        img_h = float(item.get("ImageHeight", 2250.0))
        sensor_h = sensor_w * (img_h / img_w) # 16:9 crop results in ~3.47 mm instead of native 4.55 mm
        
        # Step 6: FOV = 2 * arctan(sensor_size / (2 * focal_length))
        fov_h = 2 * math.atan(sensor_w / (2.0 * f))
        fov_v = 2 * math.atan(sensor_h / (2.0 * f))
        
        processed_item = item.copy()
        processed_item["sensor_width_mm"] = sensor_w
        processed_item["sensor_height_mm"] = sensor_h
        processed_item["fov_h_rad"] = fov_h
        processed_item["fov_v_rad"] = fov_v
        processed_item["fov_h_deg"] = math.degrees(fov_h)
        processed_item["fov_v_deg"] = math.degrees(fov_v)
        processed_metadata.append(processed_item)
        
    print(f" -> Calculated FOVs (Horizontal: {math.degrees(fov_h):.2f} deg, Vertical: {math.degrees(fov_v):.2f} deg)")
    return processed_metadata
