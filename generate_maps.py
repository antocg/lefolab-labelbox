import argparse
import exifread
import folium
import os
import rasterio
import re
import requests
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
from folium import IFrame
from io import BytesIO
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

def search_latest_mapping(year, mission_id):
    """
    Search for the most recent mapping mission in BASE_PATH_CONRAD/YYYY/ by zoom mission.

    Args:
        year (str): The year of the mapping mission.
        mission_id (str): Zoom mission_id to filter mapping missions.

    Returns:
        str: The most recent mapping mission name matching the keyword.
    """
    folder_path = os.path.join(BASE_PATH_CONRAD, year)

    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"Folder path does not exist: {folder_path}")
    
    if '_' in mission_id:
        parts = mission_id.split('_')
        keyword = parts[1]
    else:
        raise ValueError(f"Invalid mission_id format: {mission_id}. Expected an underscore ('_') in the ID.")
    
    # Get all subdirectories in the folder that match the keyword
    matching_dirs = [
        d for d in os.listdir(folder_path)
        if os.path.isdir(os.path.join(folder_path, d)) and f"_{keyword}_" in d
    ]

    # If no matching directories found, raise error
    if not matching_dirs:
        raise ValueError(f"No matching collection found for mission_id: {mission_id}")

    # Sort directories by date (most recent first)
    matching_dirs.sort(
        key=lambda x: x[:8],  # Extract YYYYMMDD from directory name
        reverse=True
    )

    # Return the most recent directory name
    return matching_dirs[0]

# def get_bounding_box(STAC_API_URL, mission_id):
#     """
#     Fetch the bounding box of a mission from a STAC API.

#     Args:
#         STAC_API_URL (str): URL of the STAC API.
#         mission_id (str): ID of the mission to query.

#     Returns:
#         list or None: The bounding box [west, south, east, north] if found, otherwise None.
#     """
#     # Build the URL for the specific collection
#     url = f"{STAC_API_URL}/collections/{mission_id}"

#     # Send the GET request
#     response = requests.get(url)

#     # Check if the request was successful
#     if response.status_code == 200:
#         # Parse the response JSON
#         data = response.json()
#         bbox = data.get("bbox", None)

#         if bbox:
#             return bbox
#         else:
#             print("Bounding Box not found in the response.")
#             return None
#     else:
#         print(f"Failed to fetch data. HTTP Status Code: {response.status_code}")
#         return None

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
    try:
        with rasterio.open(raster_path) as src:
            # Get the bounding box in the raster's CRS
            bounds = src.bounds
            
            # Create transformer from raster CRS to WGS84
            transformer = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
            
            # Transform southwest corner
            lon_min, lat_min = transformer.transform(bounds.left, bounds.bottom)
            # Transform northeast corner
            lon_max, lat_max = transformer.transform(bounds.right, bounds.top)
            
            return {
                'south_min_lat_y_deg': lat_min,
                'west_min_lon_x_deg': lon_min,
                'north_max_lat_y_deg': lat_max,
                'east_max_lon_x_deg': lon_max
            }
    except Exception as e:
        print(f"Failed to read bounding box from raster: {str(e)}")
        return None

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
    if ref.values[0] in ['S', 'W']:
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
            print("Missing GPS EXIF tags in the image metadata.")
            return None
    else:
        print(f"Failed to fetch image. HTTP Status Code: {response.status_code}")
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
    try:
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
            
            # Check if coordinates are within bounds
            if (0 <= dsm_row < dsm.height and 0 <= dsm_col < dsm.width and
                0 <= dtm_row < dtm.height and 0 <= dtm_col < dtm.width):
                # Get elevation values
                dsm_value = dsm.read(1)[dsm_row, dsm_col]
                dtm_value = dtm.read(1)[dtm_row, dtm_col]
                
                # Calculate tree height (DSM - DTM)
                tree_height = dsm_value - dtm_value
                return tree_height, None
            else:
                return None, f"Coordinates ({lon}, {lat}) are outside raster bounds"
    except Exception as e:
        return None, f"Failed to calculate tree height: {str(e)}"

def create_map(lat, lon, png_imagery_url, bbox, output_path, dsm_path=None, dtm_path=None):
    """
    Create an interactive map with a marker and an image overlay.
    If DSM and DTM paths are provided, calculate tree height at marker location.

    Args:
        lat (float): Latitude of the center point.
        lon (float): Longitude of the center point.
        png_imagery_url (str): URL of the PNG imagery to overlay on the map.
        output_path (str): Path to save the generated HTML file.
        dsm_path (str, optional): Path to the DSM GeoTIFF file.
        dtm_path (str, optional): Path to the DTM GeoTIFF file.
    """
    # Create a map centered at the coordinates with Esri Satellite tiles
    m = folium.Map(
        location=[lat, lon],
        zoom_start=18,
        max_zoom=20,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri"
    )
    
    # Calculate tree height if DSM and DTM are provided
    tree_height_info = ""
    if dsm_path and dtm_path:
        tree_height, error = calculate_tree_height(lat, lon, dsm_path, dtm_path)
        if tree_height is not None:
            tree_height_info = f"{tree_height:.2f}"
        else:
            print(error)
    
    # Create a custom HTML popup
    html = f"""
    <div style="width: 150px; height: 60px; overflow: hidden;">
        <b>Lat:</b> {lat:.6f}°<br>
        <b>Lon:</b> {lon:.6f}°<br>
        <b>Tree height:</b> {tree_height_info} m
    </div>
    """
    iframe = IFrame(html, width=180, height=80)
    popup = folium.Popup(iframe)

    # Add a marker to the map with the custom popup
    folium.Marker([lat, lon], popup=popup).add_to(m)
    
    # Validate bbox keys
    required_keys = ['south_min_lat_y_deg', 'west_min_lon_x_deg', 'north_max_lat_y_deg', 'east_max_lon_x_deg']
    if not bbox:
        raise ValueError("Bounding box is None. Cannot create map.")
    if not all(key in bbox for key in required_keys):
        missing_keys = set(required_keys) - set(bbox.keys())
        raise ValueError(f"Missing required keys in bbox: {', '.join(missing_keys)}. Provided bbox: {bbox}")

    # Convert bbox to the required bounds format for Folium
    bounds = [
        [bbox['south_min_lat_y_deg'], bbox['west_min_lon_x_deg']],  # Southwest (bottom-left)
        [bbox['north_max_lat_y_deg'], bbox['east_max_lon_x_deg']],  # Northeast (top-right)
    ]
    
    # Add the PNG layer to the map
    folium.raster_layers.ImageOverlay(
        image=png_imagery_url,
        bounds=bounds,
        opacity=1,
        interactive=False,
    ).add_to(m)
    
    # Save the map as an HTML file
    m.save(output_path)

def main(mission_id, year, dtm_path, output_dir):
    """Main function to process a mission"""
    print(f"Processing mission: {mission_id}")

    # Search for the latest mapping mission
    mapping_mission = search_latest_mapping(year, mission_id)
    if not mapping_mission:
        print(f"No mapping_mission found for zoom mission: {mission_id}")
        return

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

        # Print the result
        print(f"{len(file_keys)} pictures found for this mission : {mission_id}")
        
        # Step 6: Filter for close-up pictures
        zoom_files = [key for key in file_keys if "zoom" in key]

        # Print the result
        print(f"{len(zoom_files)} close-up pictures found for this mission : {mission_id}")
    else:
        print(f"Failed to fetch XML. HTTP Status Code: {response.status_code}")
        return
    
    bbox = get_bounding_box_from_raster(rgb_cog_path)
    if not bbox:
        print(f"No bounding box found for mapping mission: {mapping_mission}")
        return

    # Initialize counters for tracking progress
    maps_created = 0
    errors_occurred = 0
    
    # Define the URL for the RGB overview image
    png_url = f"{ALLIANCECAN_URL}/{mission_id}/labelbox/{mapping_mission}_rgb.overview.png"
    
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
            print(f"Could not find matching wide photo for {zoom_file} with identifier {identifier_match}")
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
                create_map(lat, lon, png_url, bbox, output_file, dsm_path=dsm_path, dtm_path=dtm_path)
    
                # Print confirmation
                print(f"Created map: {output_file}")
                maps_created += 1
            except Exception as e:
                print(f"Error creating map for {zoom_file}: {str(e)}")
                errors_occurred += 1
        else:
            print(f"No coordinates found for {zoom_file}")
            errors_occurred += 1
    
    # Print summary after loop completion
    print(f"Mission {mission_id} - Total maps created: {maps_created}")
    print(f"Mission {mission_id} - Total errors: {errors_occurred}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process drone close-up pictures mission data and create maps.')
    parser.add_argument('--mission_id', required=True, help='ID of the mission to process')
    parser.add_argument('--year', help='Year of the mission (default to first 4 digits of mission_id)')
    parser.add_argument('--dtm_path', help='Path to DTM file') 
    parser.add_argument('--output_dir', required=True, help='Base directory where output folder and maps will be saved')
    args = parser.parse_args()
    
    # Use provided year or extract from mission_id
    year = args.year
    if not year:
        if not re.match(r'^\d{8}', args.mission_id):
            raise ValueError(f"Mission ID {args.mission_id} does not start with 8 digits")
        year = args.mission_id[:4]

    main(args.mission_id, year, args.dtm_path, args.output_dir)