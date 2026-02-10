import argparse
import branca.colormap as bcm
import datetime
import exifread
import folium
import logging
import matplotlib.colors as colors
import numpy as np
import os
import rasterio
import re
import requests
import rioxarray
import shutil
import sys
import time
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
from folium import Element
from folium import IFrame
from io import BytesIO
from matplotlib import colormaps
from pyproj import Transformer
from rasterio.transform import rowcol

# Load environment variables from .env file
load_dotenv()

# Get environment variables
ALLIANCECAN_URL = os.getenv("ALLIANCECAN_URL")
BASE_PATH_CONRAD = os.getenv("BASE_PATH_CONRAD")

# Verify environment variables are set
if not ALLIANCECAN_URL:
    raise ValueError("ALLIANCECAN_URL environment variable is not set")
if not BASE_PATH_CONRAD:
    raise ValueError("BASE_PATH_CONRAD environment variable is not set")

def search_latest_mapping(mission_id):
    """
    Search for the most recent mapping mission in BASE_PATH_CONRAD/YYYY/ by zoom mission.

    Args:
        mission_id (str): Zoom mission_id to filter mapping missions.

    Returns:
        str: The most recent mapping mission name matching the keyword.
    """
    logger = logging.getLogger('MapGenerator')
    
    # Search years from current year down to 2017
    current_year = datetime.datetime.now().year
    years = [str(y) for y in range(current_year, 2016, -1)]
    
    if '_' in mission_id:
        parts = mission_id.split('_')
        keyword = parts[1]
    else:
        logger.error(f"Invalid mission_id format: {mission_id}. Expected an underscore ('_') in the ID.")
    
    matching_dirs = []
    for year in years:
        folder_path = os.path.join(BASE_PATH_CONRAD, year)
        if not os.path.exists(folder_path):
            continue
        # Get all subdirectories in the folder that match the keyword
        matches = [
            d for d in os.listdir(folder_path)
            if os.path.isdir(os.path.join(folder_path, d)) and f"_{keyword}_" in d
        ]
        matching_dirs.extend(matches)

    # If no matching directories found, raise error
    if not matching_dirs:
        logger.error(f"No mapping mission found for zoom mission {mission_id}. Specify a mapping mission manually.")
        raise ValueError(f"No mapping mission found for zoom mission {mission_id}. Specify a mapping mission manually.")

    # Sort directories by date (most recent first)
    matching_dirs.sort(
        key=lambda x: x[:8] if re.match(r'^\d{8}', x) else '',  # Validate and extract YYYYMMDD from directory name
        reverse=True
    )

    # Return the most recent directory name
    return matching_dirs[0]

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
            # Get the bounding box in the raster's CRS
            bounds = src.bounds
            
            # Create transformer from raster CRS to WGS84
            transformer = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
            
            # transform() needs to be called with xx, yy
            # Transform south-west
            lon_min, lat_min = transformer.transform(bounds.left, bounds.bottom)
            # Transform north-east
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
        # Load the image into BytesIO
        image_data = BytesIO(response.content)
        tags = exifread.process_file(image_data)
        latitude = tags.get('GPS GPSLatitude')
        latitude_ref = tags.get('GPS GPSLatitudeRef')
        longitude = tags.get('GPS GPSLongitude')
        longitude_ref = tags.get('GPS GPSLongitudeRef')
        
        # Check if EXIF tags are present
        if latitude and latitude_ref and longitude and longitude_ref:
            # Convert to decimal degrees
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
        # Open the DSM and DTM files
        with rasterio.open(dsm_path) as dsm, rasterio.open(dtm_path) as dtm:
            # Get CRS from the DSM
            dsm_crs = dsm.crs
            
            # Create transformer from WGS84 (EPSG:4326) to the DSM's CRS
            transformer = Transformer.from_crs("EPSG:4326", dsm_crs, always_xy=True)
            
            # Transform coordinates
            x_proj, y_proj = transformer.transform(lon, lat)
            
            # Get pixel coordinates from the projected coordinates
            dsm_row, dsm_col = rowcol(dsm.transform, x_proj, y_proj)
            dtm_row, dtm_col = rowcol(dtm.transform, x_proj, y_proj)
            
            # Get elevation values
            dsm_value = dsm.read(1)[dsm_row, dsm_col]
            dtm_value = dtm.read(1)[dtm_row, dtm_col]
            
            # Calculate tree height (DSM - DTM)
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
            # Create transformer from WGS84 to raster CRS
            transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            
            # Transform coordinates
            x_proj, y_proj = transformer.transform(lon, lat)
            
            # Get pixel coordinates
            row, col = rowcol(src.transform, x_proj, y_proj)
            
            # Check if coordinates are within bounds
            if not (0 <= row < src.height and 0 <= col < src.width):
                return False
                
            # Read the value at the pixel location
            value = src.read(1)[row, col]
            
            # Check if the value is valid (not NoData and not NaN)
            if src.nodata is not None:
                is_valid = value != src.nodata and not np.isnan(value)
            else:
                is_valid = not np.isnan(value)
                
            return is_valid
            
    except Exception as e:
        logger.error(f"Error checking point in raster: {str(e)}")
        return False

def create_map(lat, lon, rgb_png_url, dtm_png_url, bbox, output_path, dsm_path=None, dtm_path=None):
    """
    Create an interactive map with a marker and optional DTM overlay.
    If DSM and DTM paths are provided, calculate tree height at marker location.

    Args:
        lat (float): Latitude of the center point.
        lon (float): Longitude of the center point.
        rgb_png_url (str): URL of the RGB PNG imagery overlay.
        dtm_png_url (str): URL of the DTM PNG overlay.
        output_path (str): Path to save the generated HTML file.
        dsm_path (str, optional): Path to the DSM GeoTIFF file.
        dtm_path (str, optional): Path to the DTM GeoTIFF file.
    """
    logger = logging.getLogger('MapGenerator')

    # Create a map centered at the coordinates with Esri Satellite tiles
    m = folium.Map(
        location=[lat, lon],
        zoom_start=18,
        max_zoom=20,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri"
    )

    # Calculate tree height if coordinates are within DTM bounds
    tree_height_info = ""
    use_dtm_overlay = False
    
    # Create base popup content
    popup_content = [
        f"<b>Lat:</b> {lat:.6f}°",
        f"<b>Lon:</b> {lon:.6f}°"
    ]
    
    if dtm_path and is_point_in_raster(lat, lon, dtm_path):
        use_dtm_overlay = True
        if dsm_path:
            tree_height, error = calculate_tree_height(lat, lon, dsm_path, dtm_path)
            if tree_height is not None:
                tree_height_info = f"{tree_height:.2f}"
                popup_content.append(f"<b>Tree height:</b> {tree_height_info} m")
            else:
                logger.error(f"Tree height calculation error: {error}")
                raise ValueError(error)
    else:
        logger.info(f"Coordinates ({lat:.8f}, {lon:.8f}) are outside DTM bounds or DTM path is not provided.")
    
    # Create popup HTML
    html = f"""
    <div style="width: 150px; height: 60px; overflow: hidden;">
        {'<br>'.join(popup_content)}
    </div>
    """
    
    # Add marker with popup
    iframe = IFrame(html, width=180, height=80)
    popup = folium.Popup(iframe)
    folium.Marker([lat, lon], popup=popup).add_to(m)

    # Validate bbox keys
    required_keys = ['south_min_lat_y_deg', 'west_min_lon_x_deg', 'north_max_lat_y_deg', 'east_max_lon_x_deg']
    if not bbox:
        logger.error("Bounding box is None. Cannot create map.")
        raise ValueError("Bounding box is None. Cannot create map.")
    if not all(key in bbox for key in required_keys):
        missing_keys = set(required_keys) - set(bbox.keys())
        logger.error(f"Missing required keys in bbox: {', '.join(missing_keys)}. Provided bbox: {bbox}")
        raise ValueError(f"Missing required keys in bbox: {', '.join(missing_keys)}. Provided bbox: {bbox}")

    # Convert bbox to the required bounds format for Folium
    bounds = [
        [bbox['south_min_lat_y_deg'], bbox['west_min_lon_x_deg']],  # Southwest (bottom-left)
        [bbox['north_max_lat_y_deg'], bbox['east_max_lon_x_deg']],  # Northeast (top-right)
    ]
    
    # Add PNG overlay only if DTM overlay is not used
    if not use_dtm_overlay:
        folium.raster_layers.ImageOverlay(
            image=rgb_png_url,
            bounds=bounds,
            opacity=1,
            interactive=False,
        ).add_to(m)

    # Add DTM overlay if coordinates are within DTM bounds
    if use_dtm_overlay:
        try:
            # Get DTM bounds
            dtm_bbox = get_bounding_box_from_raster(dtm_path)
            if not dtm_bbox:
                logger.error("Could not get DTM bounds")
                raise ValueError("Could not get DTM bounds")

            dtm_bounds = [
                [dtm_bbox['south_min_lat_y_deg'], dtm_bbox['west_min_lon_x_deg']],
                [dtm_bbox['north_max_lat_y_deg'], dtm_bbox['east_max_lon_x_deg']]
            ]

            # Add DTM overlay
            folium.raster_layers.ImageOverlay(
                image=dtm_png_url,
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

            # Compute min and max for color scale (based only on valid data)
            valid_data = masked.compressed()
            vmin = valid_data.min()
            vmax = valid_data.max()

            # Create a branca colormap from matplotlib colormap
            mpl_cmap = colormaps.get_cmap('turbo')
            norm = colors.Normalize(vmin=vmin, vmax=vmax)
            colormap = bcm.StepColormap(
                colors=[mpl_cmap(norm(v)) for v in np.linspace(vmin, vmax, 10)],
                vmin=vmin, vmax=vmax,
                caption='Digital terrain model - Modelo digital de terreno (m)',
                text_color='white'
            )

            # Add custom CSS styling for caption and tick labels
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
    
    # Save the map as an HTML file
    m.save(output_path)

def setup_logging(mission_id, output_dir):
    """Configure logging to separate files and streams by level."""
    log_dir = os.path.join(output_dir, mission_id, 'labelbox')
    os.makedirs(log_dir, exist_ok=True)

    info_log_file = os.path.join(log_dir, f'{mission_id}_maps_info.log')
    error_log_file = os.path.join(log_dir, f'{mission_id}_maps_error.log')

    logger = logging.getLogger('MapGenerator')
    logger.setLevel(logging.INFO)
    logger.handlers = []  # Remove any existing handlers

    # Formatter
    formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # INFO handler to stdout and info.log
    info_stream_handler = logging.StreamHandler(sys.stdout)
    info_stream_handler.setLevel(logging.INFO)
    info_stream_handler.addFilter(lambda record: record.levelno == logging.INFO)
    info_stream_handler.setFormatter(formatter)

    info_file_handler = logging.FileHandler(info_log_file)
    info_file_handler.setLevel(logging.INFO)
    info_file_handler.addFilter(lambda record: record.levelno == logging.INFO)
    info_file_handler.setFormatter(formatter)

    # WARNING/ERROR handler to stderr and error.log
    error_stream_handler = logging.StreamHandler(sys.stderr)
    error_stream_handler.setLevel(logging.WARNING)
    error_stream_handler.setFormatter(formatter)

    error_file_handler = logging.FileHandler(error_log_file)
    error_file_handler.setLevel(logging.WARNING)
    error_file_handler.setFormatter(formatter)

    # Add handlers
    logger.addHandler(info_stream_handler)
    logger.addHandler(info_file_handler)
    logger.addHandler(error_stream_handler)
    logger.addHandler(error_file_handler)

    return logger

def main(mission_id, output_dir, dtm_path=None, github_project=None, mapping_mission=None):
    """Main function to process a mission"""
    start_time = time.time()
    # Configure logging
    logger = setup_logging(mission_id, output_dir)
    logger.info(f"Processing mission: {mission_id}")
    
    # Use provided mapping_mission or search for the latest
    if mapping_mission:
        logger.info(f"Using provided mapping mission: {mapping_mission}")
    else:
        mapping_mission = search_latest_mapping(mission_id)
        logger.info(f"Found mapping mission: {mapping_mission}")
        if not mapping_mission:
            logger.error(f"No mapping mission found for zoom mission {mission_id}. Specify a mapping mission manually.")
            raise ValueError(f"No mapping mission found for zoom mission {mission_id}. Specify a mapping mission manually.")

    if not re.match(r'^\d{8}', mapping_mission):
        logger.error(f"Mapping mission {mapping_mission} does not start with 8 digits")
        raise ValueError(f"Mapping mission {mapping_mission} does not start with 8 digits")
    year = mapping_mission[:4]

    basename_path = f"{BASE_PATH_CONRAD}/{year}/{mapping_mission}/{mapping_mission}"

    # Define paths to DSM files
    dsm_cog_path = f"{basename_path}_dsm.cog.tif"
    dsm_path = f"{basename_path}_dsm.tif"

    # Define paths to RGB files
    rgb_cog_path = f"{basename_path}_rgb.cog.tif"
    rgb_path = f"{basename_path}_rgb.tif"

    # Check if COG version exists, otherwise use regular version
    if os.path.exists(dsm_cog_path):
        dsm_path = dsm_cog_path
    if os.path.exists(rgb_cog_path):
        rgb_path = rgb_cog_path

    # List all pictures on Alliance Canada for a given mission
    # Step 1: Specify the URL of the folder
    folder_url = f"{ALLIANCECAN_URL}/{mission_id}/"

    # Step 2: Fetch the XML data
    response = requests.get(folder_url)
    if response.status_code == 200:
        # Step 3: Parse the XML
        xml_data = response.text
        root = ET.fromstring(xml_data)

        # Step 4: Extract the namespace from the root tag
        namespace = {"ns": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}

        # Step 5: Extract file keys
        file_keys = []
        for content in root.findall("ns:Contents", namespace):
            key = content.find("ns:Key", namespace).text
            if key.lower().endswith(".jpg"):  # keep pictures only
                file_keys.append(key)

        logger.info(f"{len(file_keys)} pictures found for this mission : {mission_id}")
        
        # Step 6: Filter for close-up pictures
        zoom_files = [key for key in file_keys if "zoom" in key]

        logger.info(f"{len(zoom_files)} close-up pictures found for this mission : {mission_id}")
    else:
        logger.error(f"Failed to fetch XML. HTTP Status Code: {response.status_code}")
        return
    
    bbox = get_bounding_box_from_raster(rgb_path)
    if not bbox:
        logger.warning(f"No bounding box found for mapping mission: {mapping_mission}")
        return

    # Initialize counters for tracking progress
    maps_created = 0
    errors_occurred = 0
    
    # Define the URL for the RGB and DTM overview image
    rgb_png_url = f"{ALLIANCECAN_URL}/{mission_id}/labelbox/{mapping_mission}_rgb.overview.png"
    dtm_png_url = f"{ALLIANCECAN_URL}/{mission_id}/labelbox/{mapping_mission}_dtm.overview.png"
    
    # Process all zoom files
    for zoom_file in zoom_files:
        # Extract the identifier from the zoom filename
        zoom_basename = os.path.basename(zoom_file)
        identifier_match = zoom_basename.split("_")[-1].lower().replace("zoom.jpg", "")
        
        # Find the corresponding wide photo that has the same identifier
        wide_file = None
        for key in file_keys:
            wide_basename = os.path.basename(key)
            if re.search(rf'_{identifier_match}\.jpg$', wide_basename, re.IGNORECASE):
                wide_file = key
                break
        
        if not wide_file:
            logger.warning(f"Could not find matching wide photo for {zoom_file} with identifier {identifier_match}")
            break
        
        # Build the URL for wide pictures to extract coordinates
        wide_picture_url = f'{folder_url}{wide_file}'
        
        # Extract coordinates from the wide photo
        wide_coordinates = get_coordinates_from_image_url(wide_picture_url)
        
        # Run the function if coordinates exist
        if wide_coordinates:
            lat, lon = wide_coordinates
            
            try:
                # Build the output file name and directory path
                filename_with_extension = os.path.basename(zoom_file)
                filename = os.path.splitext(filename_with_extension)[0]
                
                # Create the directory path
                output_folder = f"{output_dir}/{mission_id}/labelbox/attachments"
                os.makedirs(output_folder, exist_ok=True)
    
                # Create the full output file path
                output_file = f"{output_folder}/{filename}.html"
                
                # Create the map with the given parameters
                create_map(lat, lon, rgb_png_url, dtm_png_url, bbox, output_file, dsm_path=dsm_path, dtm_path=dtm_path)
    
                logger.info(f"Created map: {output_file}")
                maps_created += 1
            except Exception as e:
                logger.error(f"Error creating map for {zoom_file}: {str(e)}")
                errors_occurred += 1
        else:
            logger.warning(f"No coordinates found for {zoom_file}")
            errors_occurred += 1
    
    logger.info(f"Mission {mission_id} - Total maps created: {maps_created} in {time.time() - start_time:.1f} seconds")
    logger.info(f"Mission {mission_id} - Total errors: {errors_occurred}")

    # Copy overview files
    try:
        # Create destination directory if it doesn't exist
        dest_dir = f"{output_dir}/{mission_id}/labelbox"
        os.makedirs(dest_dir, exist_ok=True)
        
        # Copy RGB overview file
        rgb_overview_src = f"{BASE_PATH_CONRAD}/{year}/{mapping_mission}/{mapping_mission}_rgb.overview.png"
        rgb_overview_dest = f"{dest_dir}/{mapping_mission}_rgb.overview.png"
        
        if os.path.exists(rgb_overview_src):
            shutil.copy2(rgb_overview_src, rgb_overview_dest)
            logger.info(f"Copied RGB overview file to {rgb_overview_dest}")
        else:
            logger.warning(f"RGB overview file not found: {rgb_overview_src}")
        
        # Copy DTM overview file if github_project is provided
        if github_project:
            dtm_overview_src = f"/app/lefolab-utils/Labelbox/{github_project}/{github_project}_dtm.overview.png"
            dtm_overview_dest = f"{dest_dir}/{mapping_mission}_dtm.overview.png"
            
            if os.path.exists(dtm_overview_src):
                shutil.copy2(dtm_overview_src, dtm_overview_dest)
                logger.info(f"Copied DTM overview file to {dtm_overview_dest}")
            else:
                logger.warning(f"DTM overview file not found: {dtm_overview_src}")
    
    except Exception as e:
        logger.error(f"Error copying overview files: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process drone close-up pictures mission data and create maps.')
    parser.add_argument('--mission_id', required=True, help='ID of the mission to process')
    parser.add_argument('--output_dir', required=True, help='Base directory where output folder and maps will be saved')
    parser.add_argument('--dtm_path', help='Path to DTM file (optional)') 
    parser.add_argument('--github_project', help='Github project name for copying DTM overview file from GitHub repo (optional)')
    parser.add_argument('--mapping_mission', help='Explicit mapping mission ID to use for overview (optional)')
    args = parser.parse_args()

    try:
        main(args.mission_id, args.output_dir, args.dtm_path, args.github_project, args.mapping_mission)
    except Exception as e:
        logging.getLogger('MapGenerator').error(f"Fatal error: {str(e)}")
        sys.exit(1)  # Exit with error code for bash script to catch
