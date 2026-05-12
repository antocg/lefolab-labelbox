import argparse
import boto3
import branca.colormap as bcm
import exifread
import folium
import logging
import matplotlib.colors as colors
import numpy as np
import os
import rasterio
import requests
import rioxarray
import sys
import time

from botocore import UNSIGNED
from botocore.client import Config
from dotenv import load_dotenv
from folium import Element
from folium import IFrame
from io import BytesIO
from matplotlib import colormaps
from pathlib import Path
from pyproj import Transformer
from rasterio.transform import rowcol

def get_bounding_box_from_raster(raster_path):
    """
    Fetch the bounding box of a raster file and convert to decimal degrees.

    Args:
        raster_path (str): Path to the raster file.

    Returns:
        dict: The bounding box in decimal degrees with keys:
              south_min_lat_y_deg, west_min_lon_x_deg,
              north_max_lat_y_deg, east_max_lon_x_deg
    """
    logger = logging.getLogger('MapGenerator')

    try:
        with rasterio.open(raster_path) as src:
            bounds = src.bounds
            transformer = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
            lon_min, lat_min = transformer.transform(bounds.left, bounds.bottom)
            lon_max, lat_max = transformer.transform(bounds.right, bounds.top)

            return {
                'south_min_lat_y_deg': lat_min,
                'west_min_lon_x_deg': lon_min,
                'north_max_lat_y_deg': lat_max,
                'east_max_lon_x_deg': lon_max
            }
    except Exception as e:
        logger.error(f"Failed to read bounding box from raster '{raster_path}': {str(e)}")
        raise

def convert_to_decimal_degrees(value, ref):
    """
    Convert GPS coordinates to decimal degrees.

    Args:
        value: GPS coordinate value.
        ref: GPS coordinate reference (N, S, E, W).

    Returns:
        float: Coordinate in decimal degrees.
    """
    if len(value.values) != 3:
        raise ValueError("Malformed or incomplete EXIF data: GPS coordinate value does not contain exactly three elements")
    d, m, s = [float(x.num) / float(x.den) for x in value.values]
    decimal_degrees = d + (m / 60) + (s / 3600)
    if ref.values and ref.values[0] in ['S', 'W']:
        decimal_degrees = -decimal_degrees
    return decimal_degrees

def get_coordinates_from_image_url(picture_url):
    """
    Get latitude and longitude from the image metadata.

    Args:
        picture_url (str): URL of the image to process.

    Returns:
        tuple or None: (latitude, longitude) in decimal degrees if found, otherwise None.
    """
    logger = logging.getLogger('MapGenerator')

    response = requests.get(picture_url)

    if response.status_code == 200:
        image_data = BytesIO(response.content)
        tags = exifread.process_file(image_data)
        latitude = tags.get('GPS GPSLatitude')
        latitude_ref = tags.get('GPS GPSLatitudeRef')
        longitude = tags.get('GPS GPSLongitude')
        longitude_ref = tags.get('GPS GPSLongitudeRef')

        if latitude and latitude_ref and longitude and longitude_ref:
            latitude = convert_to_decimal_degrees(latitude, latitude_ref)
            longitude = convert_to_decimal_degrees(longitude, longitude_ref)
            return latitude, longitude
        else:
            logger.warning("Missing GPS EXIF tags in the image metadata.")
            return None
    else:
        logger.error(f"Failed to fetch image. HTTP Status Code: {response.status_code}")
        return None

def calculate_tree_height(lat, lon, dsm_path, dtm_path):
    """
    Calculate tree height at a specific geographic location using DSM and DTM.

    Args:
        lat (float): Latitude of the point.
        lon (float): Longitude of the point.
        dsm_path (str): Path to the Digital Surface Model (DSM) GeoTIFF.
        dtm_path (str): Path to the Digital Terrain Model (DTM) GeoTIFF.

    Returns:
        tuple: (tree_height, error_message) where tree_height is a float (None if calculation failed)
               and error_message is a string (None if calculation succeeded).
    """
    logger = logging.getLogger('MapGenerator')

    try:
        logger.info(f"Calculating tree height at lat={lat:.8f}, lon={lon:.8f}")
        with rasterio.open(dsm_path) as dsm, rasterio.open(dtm_path) as dtm:
            dsm_crs = dsm.crs
            transformer = Transformer.from_crs("EPSG:4326", dsm_crs, always_xy=True)
            x_proj, y_proj = transformer.transform(lon, lat)
            dsm_row, dsm_col = rowcol(dsm.transform, x_proj, y_proj)
            dtm_row, dtm_col = rowcol(dtm.transform, x_proj, y_proj)
            dsm_value = dsm.read(1)[dsm_row, dsm_col]
            dtm_value = dtm.read(1)[dtm_row, dtm_col]
            tree_height = dsm_value - dtm_value
            logger.info(f"Calculated tree height: {tree_height:.2f}m")
            return tree_height, None
    except Exception as e:
        logger.error(f"Failed to calculate tree height: {str(e)}")
        return None, f"Failed to calculate tree height: {str(e)}"

def is_point_in_raster(lat, lon, raster_path):
    """
    Check if coordinates fall within raster bounds and have valid data.

    Args:
        lat (float): Latitude in decimal degrees
        lon (float): Longitude in decimal degrees
        raster_path (str): Path to the raster file

    Returns:
        bool: True if coordinates are within bounds and have valid data
    """
    logger = logging.getLogger('MapGenerator')

    try:
        with rasterio.open(raster_path) as src:
            transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            x_proj, y_proj = transformer.transform(lon, lat)
            row, col = rowcol(src.transform, x_proj, y_proj)

            if not (0 <= row < src.height and 0 <= col < src.width):
                return False

            value = src.read(1)[row, col]

            if src.nodata is not None:
                is_valid = value != src.nodata and not np.isnan(value)
            else:
                is_valid = not np.isnan(value)

            return is_valid

    except Exception as e:
        logger.error(f"Error checking point in raster: {str(e)}")
        return False

def create_map(lat, lon, dsm_png_path, dtm_png_path, output_path, dsm_path=None, dtm_path=None):
    """
    Create an interactive map with a marker and optional DTM or DSM overlay.
    If the point falls within DTM bounds, the DTM overlay is used and tree height is calculated.
    Otherwise the DSM overview PNG is used as the overlay.

    Args:
        lat (float): Latitude of the center point.
        lon (float): Longitude of the center point.
        dsm_png_path (str): Path to the DSM overview PNG (used when DTM unavailable).
        dtm_png_path (str): Path to the DTM overview PNG.
        output_path (str): Path to save the generated HTML file.
        dsm_path (str, optional): Path to the DSM GeoTIFF (for height calculation and DSM overlay bounds).
        dtm_path (str, optional): Path to the DTM GeoTIFF.
    """
    logger = logging.getLogger('MapGenerator')

    m = folium.Map(
        location=[lat, lon],
        zoom_start=18,
        max_zoom=20,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri"
    )

    use_dtm_overlay = False
    popup_content = [
        f"<b>Lat:</b> {lat:.6f}°",
        f"<b>Lon:</b> {lon:.6f}°"
    ]

    if dtm_path and is_point_in_raster(lat, lon, dtm_path):
        use_dtm_overlay = True
        if dsm_path:
            tree_height, error = calculate_tree_height(lat, lon, dsm_path, dtm_path)
            if tree_height is not None:
                popup_content.append(f"<b>Tree height:</b> {tree_height:.2f} m")
            else:
                logger.error(f"Tree height calculation error: {error}")
                raise ValueError(error)
    else:
        logger.info(f"Coordinates ({lat:.8f}, {lon:.8f}) are outside DTM bounds or DTM path is not provided.")

    html = f"""
    <div style="width: 150px; height: 60px; overflow: hidden;">
        {'<br>'.join(popup_content)}
    </div>
    """

    iframe = IFrame(html, width=180, height=80)
    popup = folium.Popup(iframe)
    folium.Marker([lat, lon], popup=popup).add_to(m)

    if not use_dtm_overlay:
        if dsm_path and dsm_png_path and os.path.exists(str(dsm_png_path)):
            dsm_bbox = get_bounding_box_from_raster(dsm_path)
            dsm_bounds = [
                [dsm_bbox['south_min_lat_y_deg'], dsm_bbox['west_min_lon_x_deg']],
                [dsm_bbox['north_max_lat_y_deg'], dsm_bbox['east_max_lon_x_deg']],
            ]
            folium.raster_layers.ImageOverlay(
                image=str(dsm_png_path),
                bounds=dsm_bounds,
                opacity=1,
                interactive=False,
            ).add_to(m)
        else:
            logger.info("No DSM overlay available for this point.")

    if use_dtm_overlay:
        try:
            dtm_bbox = get_bounding_box_from_raster(dtm_path)
            if not dtm_bbox:
                logger.error("Could not get DTM bounds")
                raise ValueError("Could not get DTM bounds")

            dtm_bounds = [
                [dtm_bbox['south_min_lat_y_deg'], dtm_bbox['west_min_lon_x_deg']],
                [dtm_bbox['north_max_lat_y_deg'], dtm_bbox['east_max_lon_x_deg']]
            ]

            folium.raster_layers.ImageOverlay(
                image=str(dtm_png_path),
                bounds=dtm_bounds,
                opacity=0.7,
                name='DTM'
            ).add_to(m)

            dem = rioxarray.open_rasterio(dtm_path)
            if 'x' in dem.dims and 'y' in dem.dims:
                dem = dem.rename({'x': 'longitude', 'y': 'latitude'})
            else:
                logger.error(f"Unexpected dimension names in DTM file: {dem.dims}")
                raise ValueError(f"Unexpected dimension names in DTM file: {dem.dims}")
            arr_dem = dem.values

            if dem.rio.nodata is not None:
                masked = np.ma.masked_equal(arr_dem[0], dem.rio.nodata)
            else:
                logger.error("NoData value is not defined in the raster file.")
                raise ValueError("NoData value is not defined in the raster file.")

            valid_data = masked.compressed()
            vmin = valid_data.min()
            vmax = valid_data.max()

            mpl_cmap = colormaps.get_cmap('turbo')
            norm = colors.Normalize(vmin=vmin, vmax=vmax)
            colormap = bcm.StepColormap(
                colors=[mpl_cmap(norm(v)) for v in np.linspace(vmin, vmax, 10)],
                vmin=vmin, vmax=vmax,
                caption='Digital terrain model - Modelo digital de terreno (m)',
                text_color='white'
            )

            custom_css = """
            <style>
            .legend.leaflet-control text.caption {
                font-size: 16px;
                font-weight: bold;
                fill: white !important;
            }
            .legend.leaflet-control .tick text {
                font-size: 14px;
                fill: white;
                font-weight: bold;
            }
            </style>
            """

            m.add_child(colormap)
            m.get_root().html.add_child(Element(custom_css))

        except Exception as e:
            logger.error(f"Failed to add DTM overlay: {str(e)}")

    m.save(output_path)

def setup_logging(mission_id, output_dir):
    """Configure logging to separate files and streams by level."""
    log_dir = os.path.join(output_dir, mission_id, 'labelbox')
    os.makedirs(log_dir, exist_ok=True)

    info_log_file = os.path.join(log_dir, f'{mission_id}_maps.log')
    error_log_file = os.path.join(log_dir, f'{mission_id}_maps_error.log')

    logger = logging.getLogger('MapGenerator')
    logger.setLevel(logging.INFO)
    logger.handlers = []

    formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    info_stream_handler = logging.StreamHandler(sys.stdout)
    info_stream_handler.setLevel(logging.INFO)
    info_stream_handler.addFilter(lambda record: record.levelno == logging.INFO)
    info_stream_handler.setFormatter(formatter)

    info_file_handler = logging.FileHandler(info_log_file)
    info_file_handler.setLevel(logging.INFO)
    info_file_handler.addFilter(lambda record: record.levelno == logging.INFO)
    info_file_handler.setFormatter(formatter)

    error_stream_handler = logging.StreamHandler(sys.stderr)
    error_stream_handler.setLevel(logging.WARNING)
    error_stream_handler.setFormatter(formatter)

    error_file_handler = logging.FileHandler(error_log_file)
    error_file_handler.setLevel(logging.WARNING)
    error_file_handler.setFormatter(formatter)

    logger.addHandler(info_stream_handler)
    logger.addHandler(info_file_handler)
    logger.addHandler(error_stream_handler)
    logger.addHandler(error_file_handler)

    return logger

def main(mission_id, project_name):
    """Main function to process a mission"""
    start_time = time.time()

    project_root = Path(__file__).parent.parent.parent
    project_dir = project_root / 'projects' / project_name
    output_dir = str(project_dir / 'output_maps')

    logger = setup_logging(mission_id, output_dir)
    logger.info(f"Processing mission: {mission_id}")

    load_dotenv(dotenv_path=project_root / '.env')

    ALLIANCECAN_URL = os.getenv("ALLIANCECAN_URL")
    BUCKET_WPT = os.getenv("BUCKET_WPT")
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

    if not ALLIANCECAN_URL:
        logger.error("ALLIANCECAN_URL environment variable is not set")
        raise ValueError("ALLIANCECAN_URL environment variable is not set")
    if not BUCKET_WPT:
        logger.error("BUCKET_WPT environment variable is not set")
        raise ValueError("BUCKET_WPT environment variable is not set")
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        logger.warning("AWS_ACCESS_KEY_ID and/or AWS_SECRET_ACCESS_KEY environment variables are not set. Assuming public bucket access.")

    # DTM - project-level
    dtm_tif = project_dir / f'{project_name}_dtm.tif'
    dtm_path = str(dtm_tif) if dtm_tif.exists() else None
    dtm_png_path = project_dir / f'{project_name}_dtm.overview.png'

    # DSM - site-specific (second segment of mission_id) or project-level fallback
    parts = mission_id.split('_')
    site_name = parts[1] if len(parts) > 1 else None
    dsm_path = None
    dsm_png_path = None

    if site_name:
        site_dsm_tif = project_dir / f'{site_name}_dsm.tif'
        if site_dsm_tif.exists():
            dsm_path = str(site_dsm_tif)
            dsm_png_path = project_dir / f'{site_name}_dsm.overview.png'

    if dsm_path is None:
        general_dsm_tif = project_dir / f'{project_name}_dsm.tif'
        if general_dsm_tif.exists():
            dsm_path = str(general_dsm_tif)
            dsm_png_path = project_dir / f'{project_name}_dsm.overview.png'

    if dtm_path:
        logger.info(f"Using DTM: {dtm_path}")
    else:
        logger.info("No DTM found for this project.")
    if dsm_path:
        logger.info(f"Using DSM: {dsm_path}")
    else:
        logger.warning("No DSM found for this project.")

    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        s3_client = boto3.client(
            's3',
            endpoint_url=ALLIANCECAN_URL,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4')
        )
    else:
        s3_client = boto3.client(
            's3',
            endpoint_url=ALLIANCECAN_URL,
            config=Config(signature_version=UNSIGNED)
        )

    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=BUCKET_WPT, Prefix=mission_id)

        file_keys = []
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    if key.lower().endswith('.jpg'):
                        file_keys.append(key)
    except Exception as e:
        logger.error(f"Failed to retrieve files from S3 bucket: {e}")
        sys.exit(1)

    folder_url = f"{ALLIANCECAN_URL}/{BUCKET_WPT}"

    logger.info(f"{len(file_keys)} pictures found for this mission : {mission_id}")

    closeup_files = [key for key in file_keys if "tele" in key]
    if closeup_files:
        logger.info(f"{len(closeup_files)} close-up pictures (tele) found for this mission : {mission_id}")
    else:
        closeup_files = [key for key in file_keys if "zoom" in key]
        if closeup_files:
            logger.info("Using legacy naming convention (zoom).")
            logger.info(f"{len(closeup_files)} close-up pictures (zoom) found for this mission : {mission_id}")
        else:
            logger.warning(f"No close-up pictures found for this mission : {mission_id}")

    maps_created = 0
    errors_occurred = 0

    for closeup_file in closeup_files:
        if "tele" in closeup_file:
            polygon_id = closeup_file.split('_')[-1].lower().replace('tele.jpg', '')
            wide_file_end = f"_{polygon_id}wide.JPG"
            exclusion_keyword = "tele"
        else:
            polygon_id = closeup_file.split('_')[-1].lower().replace('zoom.jpg', '')
            wide_file_end = f"_{polygon_id}.JPG"
            exclusion_keyword = "zoom"

        wide_file = None
        matching_wide_files = [key for key in file_keys if wide_file_end in key and exclusion_keyword not in key]

        if len(matching_wide_files) > 1:
            logger.warning(f"Warning: Multiple wide pictures found for {closeup_file}: {matching_wide_files}. Using the first match.")

        wide_file = matching_wide_files[0] if matching_wide_files else None

        if not wide_file:
            logger.warning(f"No wide file found for {closeup_file}")
            break

        wide_picture_url = f'{folder_url}/{wide_file}'
        wide_coordinates = get_coordinates_from_image_url(wide_picture_url)

        if wide_coordinates:
            lat, lon = wide_coordinates

            max_attempts = 3
            success = False
            last_error = None

            for attempt in range(max_attempts):
                try:
                    filename_with_extension = os.path.basename(closeup_file)
                    filename = os.path.splitext(filename_with_extension)[0]

                    output_folder = f"{output_dir}/{mission_id}/labelbox/attachments"
                    os.makedirs(output_folder, exist_ok=True)

                    output_file = f"{output_folder}/{filename}.html"

                    create_map(lat, lon, dsm_png_path, dtm_png_path, output_file, dsm_path=dsm_path, dtm_path=dtm_path)

                    logger.info(f"Created map: {output_file}")
                    maps_created += 1
                    success = True
                    break
                except Exception as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        logger.warning(f"Attempt {attempt + 1} failed for {closeup_file}, retrying... ({str(e)})")
                        time.sleep(10)

            if not success:
                logger.error(f"Error creating map for {closeup_file} after {max_attempts} attempts: {str(last_error)}")
                errors_occurred += 1
        else:
            logger.warning(f"No coordinates found for {closeup_file}")
            errors_occurred += 1

    logger.info(f"Mission {mission_id} - Total maps created: {maps_created} in {time.time() - start_time:.1f} seconds")
    logger.info(f"Mission {mission_id} - Total errors: {errors_occurred}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process drone close-up pictures mission data and create maps.')
    parser.add_argument('--mission_id', required=True, help='ID of the mission to process')
    parser.add_argument('--project_name', required=True, help='Project name (folder under projects/)')
    args = parser.parse_args()

    try:
        main(args.mission_id, args.project_name)
    except Exception as e:
        logging.getLogger('MapGenerator').error(f"Fatal error: {str(e)}")
        sys.exit(1)
