import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.ops import transform
from shapely.geometry import Point, Polygon
from pykrige.ok import OrdinaryKriging

# ----------------------------
# UTM Transform (Delhi = 32643 - UTM Zone 43N)
# ----------------------------
# Transformer for converting (lon, lat) to (x, y) in meters
to_utm = Transformer.from_crs("epsg:4326", "epsg:32643", always_xy=True).transform
# Transformer for converting (x, y) in meters back to (lon, lat)
to_latlon = Transformer.from_crs("epsg:32643", "epsg:4326", always_xy=True).transform


# ----------------------------
# Generate UTM Grid
# ----------------------------
def generate_utm_grid(lat_min, lat_max, lon_min, lon_max, resolution=200):
    """Generates a regular grid of UTM coordinates spanning the bounding box."""
    x_min, y_min = to_utm(lon_min, lat_min)
    x_max, y_max = to_utm(lon_max, lat_max)

    x = np.linspace(x_min, x_max, resolution)
    y = np.linspace(y_min, y_max, resolution)

    x_grid, y_grid = np.meshgrid(x, y)
    return x_grid, y_grid


# ----------------------------
# Main Kriging Function
# ----------------------------
def perform_kriging_correct(df, bbox, polygon=None, resolution=200):
    """
    Performs Ordinary Kriging interpolation on AQI data.

    Args:
        df (pd.DataFrame): DataFrame with 'lat', 'lon', and 'aqi' columns.
        bbox (tuple): (lat_min, lat_max, lon_min, lon_max) bounding box.
        polygon (Polygon, optional): Delhi boundary in UTM (EPSG:32643) for masking.
        resolution (int): Grid resolution.

    Returns:
        tuple: (lon_grid, lat_grid, interpolated_aqi_grid)
    """

    lat_min, lat_max, lon_min, lon_max = bbox

    # 1. Convert station coordinates to UTM (meters)
    xs, ys = to_utm(df["lon"].values, df["lat"].values)
    values = df["aqi"].values

    # 2. Build UTM grid for interpolation
    x_grid, y_grid = generate_utm_grid(lat_min, lat_max, lon_min, lon_max, resolution)

    # Kriging requires at least two unique data points
    if len(values) < 2 or len(np.unique(values)) < 2:
        # Return NaN grid if Kriging cannot run
        z_nan = np.full(x_grid.shape, np.nan)
        lon_grid, lat_grid = to_latlon(x_grid, y_grid)
        return lon_grid, lat_grid, z_nan
    
    # 3. Perform Ordinary Kriging in meters
    try:
        OK = OrdinaryKriging(
            xs, ys, values,
            variogram_model="spherical",
            verbose=False,
            enable_plotting=False,
        )

        z, ss = OK.execute("grid", x_grid[0], y_grid[:, 0])
        z = z.data # Extract data from masked array
        
    except Exception as e:
        # Handle exceptions during Kriging (e.g., singular matrix)
        print(f"Kriging execution failed: {e}")
        z = np.full(x_grid.shape, np.nan)


    # 4. Mask grid using Delhi polygon in UTM
    if polygon is not None:
        mask = np.zeros_like(z, dtype=bool)

        # Iterate over the grid points
        for i in range(z.shape[0]):
            for j in range(z.shape[1]):
                px = x_grid[i, j]
                py = y_grid[i, j]

                # Check if the grid point (in UTM) is inside the polygon (in UTM)
                if polygon.contains(Point(px, py)):
                    mask[i, j] = True

        # Apply mask: if outside the polygon, set AQI to NaN
        z = np.where(mask, z, np.nan)

    # 5. Convert grid from UTM → Lat/Lon
    lon_grid, lat_grid = to_latlon(x_grid, y_grid)

    return lon_grid, lat_grid, z
