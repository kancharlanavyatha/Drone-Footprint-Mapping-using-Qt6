import os
import numpy as np
from PIL import Image
from pyproj import Transformer

class DemRayTracer:
    """
    Loads a GeoTIFF Digital Elevation Model (DSM/DEM) and performs
    3D ray-surface intersection using bisection ray-marching.
    """
    def __init__(self, dem_path):
        self.dem_path = dem_path
        self.loaded = False
        
        if not os.path.exists(dem_path):
            print(f"[DemRayTracer] DEM file not found at: {dem_path}")
            return
            
        try:
            im = Image.open(dem_path)
            self.elevation_data = np.array(im, dtype=np.float32)
            self.height, self.width = self.elevation_data.shape
            
            tags = im.tag_v2
            # Tag 33550: ModelPixelScale (scale_x, scale_y, scale_z)
            scale = tags.get(33550, (0.070154, 0.070154, 0.0))
            self.pixel_scale_x = float(scale[0])
            self.pixel_scale_y = float(scale[1])
            
            # Tag 33922: ModelTiepoint (I, J, K, X, Y, Z)
            tiepoint = tags.get(33922, (0, 0, 0, 2851243.84, 5674920.90, 0))
            self.origin_x = float(tiepoint[3])
            self.origin_y = float(tiepoint[4])
            
            # Transformer from UTM 15N (project dataset coordinates) to UTM 10N (dsm.tif raster coordinates)
            self.transformer_to_utm10 = Transformer.from_crs("epsg:32615", "epsg:32610", always_xy=True)
            
            # Elevation statistics (filtering out nodata values < -9000)
            valid_mask = self.elevation_data > -9000
            self.min_elevation = float(np.min(self.elevation_data[valid_mask]))
            self.max_elevation = float(np.max(self.elevation_data[valid_mask]))
            self.mean_elevation = float(np.mean(self.elevation_data[valid_mask]))
            
            self.loaded = True
            print(f"[DemRayTracer] Successfully loaded DEM: {self.width}x{self.height}, "
                  f"elevation range: [{self.min_elevation:.2f}m, {self.max_elevation:.2f}m]")
        except Exception as e:
            print(f"[DemRayTracer] Error initializing DEM ray tracer: {e}")
            self.loaded = False

    def get_elevation_at_utm15(self, utm15_x, utm15_y):
        """
        Samples the DEM elevation in meters for a given UTM Zone 15N coordinate.
        Returns None if out of bounds or nodata.
        """
        if not self.loaded:
            return None
            
        try:
            x_10, y_10 = self.transformer_to_utm10.transform(utm15_x, utm15_y)
            col = int(round((x_10 - self.origin_x) / self.pixel_scale_x))
            row = int(round((self.origin_y - y_10) / self.pixel_scale_y))
            
            if 0 <= col < self.width and 0 <= row < self.height:
                val = float(self.elevation_data[row, col])
                if val > -9000:
                    return val
        except Exception:
            pass
        return None

    def intersect_ray(self, origin, ray_dir, max_iterations=25, tolerance=0.05):
        """
        Finds the 3D intersection point of a world-space ray with the DEM surface.
        
        Parameters:
            origin: np.ndarray [X, Y, Z] (Camera center in UTM 15N)
            ray_dir: np.ndarray [dx, dy, dz] (Unit direction vector in world space)
            max_iterations: Maximum bisection steps
            tolerance: Convergence distance threshold in meters
            
        Returns:
            np.ndarray [X, Y, Z] (Intersection point in UTM 15N coordinates)
        """
        # If ray is not pointing downwards, cannot intersect ground
        if ray_dir[2] >= -1e-5:
            return None
            
        # Initial bounding bracket for lambda:
        # lambda_min: ray reaches the highest possible terrain point
        # lambda_max: ray reaches the lowest possible terrain point
        lambda_min = (self.max_elevation - origin[2]) / ray_dir[2]
        lambda_max = (self.min_elevation - origin[2]) / ray_dir[2]
        
        if lambda_min < 0:
            lambda_min = 0.1
            
        # Bisection ray marching
        t_low = lambda_min
        t_high = lambda_max
        
        for _ in range(max_iterations):
            t_mid = 0.5 * (t_low + t_high)
            p_mid = origin + t_mid * ray_dir
            
            dem_z = self.get_elevation_at_utm15(p_mid[0], p_mid[1])
            if dem_z is None:
                dem_z = self.mean_elevation
                
            # Error = Ray Z height - Actual Terrain Z height
            diff = p_mid[2] - dem_z
            
            if abs(diff) < tolerance or (t_high - t_low) < tolerance:
                return np.array([p_mid[0], p_mid[1], dem_z], dtype=np.float64)
                
            if diff > 0:
                # Ray is still above ground -> move forward
                t_low = t_mid
            else:
                # Ray has penetrated ground -> pull back
                t_high = t_mid
                
        # Return best converged point
        p_final = origin + 0.5 * (t_low + t_high) * ray_dir
        dem_z = self.get_elevation_at_utm15(p_final[0], p_final[1])
        if dem_z is not None:
            p_final[2] = dem_z
        return p_final
