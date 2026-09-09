import os
import sys

# Ensure import works when running script directly from terminal
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from step1_extract_metadata import extract_metadata_using_exiftool
from step2_sensor_and_fov import calculate_sensor_and_fov
from step3_ground_coverage import compute_ground_coverage_and_corners
from step4_polygon_export import build_polygon_and_export

def main():
    print("==================================================")
    print("GIS DRONE FOOTPRINT EXTRACTION PIPELINE")
    print("==================================================")
    
    base_dir = os.path.dirname(current_dir)
    image_dir = os.path.join(base_dir, "drone_dataset_brighton_beach-master", "images")
    output_dir = os.path.join(current_dir, "output")
    
    raw_json = os.path.join(output_dir, "raw_metadata.json")
    footprints_json = os.path.join(output_dir, "calculated_footprints.json")
    output_geojson = os.path.join(base_dir, "drone_dataset_brighton_beach-master", "footprints_pipeline.geojson")
    dem_path = os.path.join(base_dir, "drone_dataset_brighton_beach-master", "dsm.tif")
    
    # Step 1: Collect images is done (target image_dir)
    # Step 2-4: Extract metadata via ExifTool
    raw_data = extract_metadata_using_exiftool(image_dir, raw_json)
    
    # Step 5-6: Determine Sensor size & Calculate FOV
    fov_data = calculate_sensor_and_fov(raw_data)
    
    # Step 7-8: Compute 3D Pinhole Ray Casting ground coverage & 4 corners with DEM
    footprint_data = compute_ground_coverage_and_corners(fov_data, footprints_json, dem_path=dem_path)
    
    # Step 9-10: Build polygon & Export GeoJSON
    build_polygon_and_export(footprint_data, output_geojson)
    
    print("==================================================")
    print("PIPELINE RUN COMPLETED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    main()
