import subprocess
import json
import os

def extract_metadata_using_exiftool(image_dir, output_raw_json):
    """
    Workflow Step 2, 3, & 4: Uses ExifTool to extract:
    - GPS Position (Lat/Lon/Alt)
    - Camera Orientation (Gimbal Yaw/Pitch/Roll)
    - Camera Calibration (Focal Length, Image dimensions)
    """
    print("[Step 1] Extracting raw metadata using ExifTool...")
    cmd = [
        "exiftool",
        "-json",
        "-n",
        "-GPSLatitude",
        "-GPSLongitude",
        "-GPSAltitude",
        "-RelativeAltitude",
        "-GimbalYawDegree",
        "-GimbalPitchDegree",
        "-GimbalRollDegree",
        "-FocalLength",
        "-ImageWidth",
        "-ImageHeight",
        image_dir
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
    if result.returncode != 0:
        raise RuntimeError(f"ExifTool failed: {result.stderr}")
        
    raw_data = json.loads(result.stdout)
    os.makedirs(os.path.dirname(output_raw_json), exist_ok=True)
    with open(output_raw_json, "w") as f:
        json.dump(raw_data, f, indent=4)
    print(f" -> Raw metadata saved to: {output_raw_json}")
    return raw_data
