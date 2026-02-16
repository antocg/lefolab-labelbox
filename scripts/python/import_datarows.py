import argparse
import copy
import labelbox as lb
import logging
import os
import requests
import sys
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
from pathlib import Path

# Setup logging with timestamp
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Handler for INFO to stdout
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.INFO)
stdout_handler.addFilter(lambda record: record.levelno == logging.INFO)
stdout_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))

# Handler for WARNING and ERROR to stderr
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.WARNING)
stderr_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))

# Remove default handlers and add custom ones
logger.handlers = []
logger.addHandler(stdout_handler)
logger.addHandler(stderr_handler)

# Load environment variables from .env file
project_root = Path(__file__).parent.parent.parent
load_dotenv(dotenv_path=project_root / '.env')

# Get environment variables
ALLIANCECAN_URL = os.getenv("ALLIANCECAN_URL")
LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")
BUCKET_WPT = os.getenv("BUCKET_WPT")

# Verify environment variables are set
if not ALLIANCECAN_URL:
    logger.error("ALLIANCECAN_URL environment variable is not set")
    raise ValueError("ALLIANCECAN_URL environment variable is not set")
if not LABELBOX_API_KEY:
    logger.error("LABELBOX_API_KEY environment variable is not set")
    raise ValueError("LABELBOX_API_KEY environment variable is not set")
if not BUCKET_WPT:
    logger.error("BUCKET_WPT environment variable is not set")
    raise ValueError("BUCKET_WPT environment variable is not set")

client = lb.Client(api_key=LABELBOX_API_KEY)

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Import data rows into Labelbox.")
parser.add_argument("--mission_id", required=True, help="Mission ID to generate the dataset.")
parser.add_argument("--prefix", help="Prefix for the dataset name.")
args = parser.parse_args()

mission_id = args.mission_id

if args.prefix:
    prefix = args.prefix
else:
    parts = mission_id.split('_')
    if len(parts) >= 4:
        site = parts[1]
        if site.startswith('tbs'):
            prefix = '2025_tiputini'
        elif site.startswith('bci'):
            prefix = '2024_bci'
        else:
            logger.error("Site in mission ID is not recognized, unable to extract prefix for Labelbox dataset.")
            raise ValueError("Site in mission ID is not recognized, unable to extract prefix for Labelbox dataset. Please provide a prefix.")
    else:
        logger.error("Mission ID does not follow expected format, unable to extract prefix for Labelbox dataset.")
        raise ValueError("Mission ID does not follow expected format, unable to extract prefix for Labelbox dataset. Please provide a prefix.")

# List all pictures on Alliance Canada for a given mission
# Specify the URL of the folder
folder_url = f"{ALLIANCECAN_URL}/{BUCKET_WPT}/{mission_id}/"

# Fetch the XML data
response = requests.get(folder_url)
if response.status_code == 200:
    # Parse the XML
    xml_data = response.text
    root = ET.fromstring(xml_data)

    # Extract the namespace from the root tag
    namespace = {"ns": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}

    # Extract file keys
    file_keys = []
    for content in root.findall("ns:Contents", namespace):
        key = content.find("ns:Key", namespace).text
        if key.lower().endswith(".jpg"):
            file_keys.append(key)

    # Print the result
    logger.info(f"{len(file_keys)} pictures found for this mission : {mission_id}")
    
    # Filter for close-up pictures (detect naming convention)
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

else:
    logger.error(f"Failed to fetch XML. HTTP Status Code: {response.status_code}")

# Create new dataset in Labelbox based on the prefix and mission ID
# Check if the dataset already exists
existing_datasets = client.get_datasets()
dataset_name = f"{prefix}_{mission_id}"
existing_dataset = next((ds for ds in existing_datasets if ds.name == dataset_name), None)

if existing_dataset:
    logger.info(f"Dataset {dataset_name} already exists")
    dataset = existing_dataset
else:
    logger.info(f"Creating new dataset {dataset_name}")
    dataset = client.create_dataset(name=dataset_name)

# Base asset template
assets_template = {
    "row_data": "",
    "global_key": "",
    "media_type": "IMAGE",
    "metadata_fields": [{"name": "mission", "value": ""},
                        {"name": "polygon", "value": ""}],
    "attachments": [{"type": "IMAGE", "value": "", "name": "wide"},
                    {"type": "HTML", "value": "", "name": "map"}]
}

# Create a list of assets
assets = []

for i, closeup_file in enumerate(closeup_files):
    # Make a copy of the template for each asset
    asset = copy.deepcopy(assets_template)
    
    # Replace row_data with the current closeup_file (URL)
    asset["row_data"] = f"{folder_url}{closeup_file}"
    
    # Use file name as unique global_key
    file = closeup_file.split('/', 1)[-1]
    asset["global_key"] = file
    
    # Metadata fields : mission_id
    asset["metadata_fields"][0]["value"] = f"{mission_id}" 
    
    # Detect naming convention and extract the polygon id
    if "tele" in closeup_file:
        polygon_id = closeup_file.split('_')[-1].lower().replace('tele.jpg', '')
        wide_file_end = f"_{polygon_id}wide.JPG"
        exclusion_keyword = "tele"
    else:
        # Legacy naming convention (zoom)
        polygon_id = closeup_file.split('_')[-1].lower().replace('zoom.jpg', '')
        wide_file_end = f"_{polygon_id}.JPG"
        exclusion_keyword = "zoom"
    
    # Metadata fields : polygon_id
    asset["metadata_fields"][1]["value"] = f"{polygon_id}" 
    
    # Attach the map
    closeup_basename = os.path.basename(closeup_file)
    map_url = f"{ALLIANCECAN_URL}/{mission_id}/labelbox/attachments/{closeup_basename.replace('.JPG', '.html')}"
    
    asset["attachments"][1]["value"] = map_url
    
    # Find the corresponding wide file from file_keys
    wide_file = None
    matching_wide_files = [key for key in file_keys if wide_file_end in key and exclusion_keyword not in key]
    
    if len(matching_wide_files) > 1:
        logger.warning(f"Warning: Multiple wide pictures found for {closeup_file}: {matching_wide_files}. Using the first match.")
    
    wide_file = matching_wide_files[0] if matching_wide_files else None
    
    # If a wide file is found, set the attachment value
    if wide_file:
        asset["attachments"][0]["value"] = f"{folder_url}{wide_file}"
    else:
        logger.warning(f"No wide file found for {closeup_file}")
    
    # Add the updated asset to the list
    assets.append(asset)

# Import data in Labelbox
if not assets:
    logger.error("No valid assets to upload. Exiting.")
    sys.exit(1)
else:
    task = dataset.create_data_rows(assets)
    task.wait_till_done()
    errors = task.errors

    if errors is None:
        logger.info("No errors while importing data to Labelbox.")
    else:
        # Count duplicate global key errors
        duplicate_count = sum(1 for e in errors if e.get('message', '').startswith("Duplicate global key"))
        other_errors = [e for e in errors if not e.get('message', '').startswith("Duplicate global key")]

        if duplicate_count:
            logger.warning(f"{duplicate_count} duplicate global key errors.")

        if other_errors:
            logger.error(f"Other errors: {other_errors}")
        else:
            logger.info("No errors while importing data to Labelbox.")
