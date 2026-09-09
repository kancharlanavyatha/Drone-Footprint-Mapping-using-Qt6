import os
import json
import subprocess
import time

def georeference_drone_images(footprints_json_path, output_dir=None, mosaic_vrt_path=None):
    """
    Workflow Step 11: Georeferencing drone camera images into GIS Rasters (GeoTIFFs)
    and building a unified mosaic VRT for QGIS.
    - Assigns 4 ray-cast UTM corners as Ground Control Points (GCPs)
    - Warps each image with GDAL into EPSG:32615 with alpha transparency
    - Builds a unified VRT mosaic catalog
    """
    print("[Step 5] Batch Georeferencing Drone Photos into GIS Rasters...")
    
    if not os.path.exists(footprints_json_path):
        print(f"Error: Footprint JSON not found: {footprints_json_path}")
        return []
        
    with open(footprints_json_path, "r") as f:
        footprints = json.load(f)
        
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if output_dir is None:
        output_dir = os.path.join(base_dir, "georeferenced_images")
    os.makedirs(output_dir, exist_ok=True)
    
    if mosaic_vrt_path is None:
        mosaic_vrt_path = os.path.join(base_dir, "brighton_beach_mosaic.vrt")
        
    tif_files = []
    t0 = time.time()
    
    for i, fp in enumerate(footprints):
        src_file = fp.get("SourceFile", "")
        if not os.path.exists(src_file):
            print(f"Warning: Image file missing: {src_file}")
            continue
            
        base_name = os.path.splitext(os.path.basename(src_file))[0]
        out_tif = os.path.join(output_dir, f"{base_name}_geo.tif")
        temp_vrt = os.path.join(output_dir, f"{base_name}_temp.vrt")
        
        w = fp.get("ImageWidth", 4000)
        h = fp.get("ImageHeight", 2250)
        c = fp["corners_utm"]
        
        # 4 GCPs: 0:Top-Left, 1:Top-Right, 2:Bottom-Right, 3:Bottom-Left
        cmd_trans = [
            "gdal_translate", "-of", "VRT",
            "-gcp", "0", "0", str(c[0][0]), str(c[0][1]),
            "-gcp", str(w), "0", str(c[1][0]), str(c[1][1]),
            "-gcp", str(w), str(h), str(c[2][0]), str(c[2][1]),
            "-gcp", "0", str(h), str(c[3][0]), str(c[3][1]),
            src_file, temp_vrt
        ]
        subprocess.run(cmd_trans, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        cmd_warp = [
            "gdalwarp", "-overwrite",
            "-t_srs", "EPSG:32615",
            "-dstalpha",
            "-co", "COMPRESS=DEFLATE",
            "-co", "TILED=YES",
            temp_vrt, out_tif
        ]
        subprocess.run(cmd_warp, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        if os.path.exists(temp_vrt):
            os.remove(temp_vrt)
            
        tif_files.append(out_tif)
        print(f" -> [{i+1}/{len(footprints)}] Georeferenced: {base_name} -> {os.path.basename(out_tif)}")
        
    print(f" -> Completed {len(tif_files)} GeoTIFFs in {time.time() - t0:.1f}s.")
    
    # Build unified VRT mosaic
    if tif_files:
        cmd_vrt = ["gdalbuildvrt", "-overwrite", mosaic_vrt_path] + tif_files
        subprocess.run(cmd_vrt, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        print(f" -> Created seamless mosaic catalog: {mosaic_vrt_path}")
        
    return tif_files

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    fp_json = os.path.join(current_dir, "output", "calculated_footprints.json")
    georeference_drone_images(fp_json)
