import argparse
import copy
import labelbox as lb
import os
import requests
import xml.etree.ElementTree as ET

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")
ALLIANCECAN_URL = os.getenv("ALLIANCECAN_URL")

client = lb.Client(api_key=LABELBOX_API_KEY)

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Import data rows into Labelbox.")
parser.add_argument("--mission_id", required=True, help="Mission ID for the Labelbox dataset.")
parser.add_argument("--project", required=True, help="Project name for the Labelbox dataset.")
args = parser.parse_args()

mission_id = args.mission_id
project = args.project

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

# Create new dataset in Labelbox based on the project name and mission ID
# Check if the dataset already exists
existing_datasets = client.get_datasets()
dataset_name = f"{project}_{mission_id}"
existing_dataset = next((ds for ds in existing_datasets if ds.name == dataset_name), None)

if existing_dataset:
    print(f"Dataset {dataset_name} already exists")
    dataset = existing_dataset
else:
    print(f"Creating new dataset {dataset_name}")
    dataset = client.create_dataset(name=f"{project}_{mission_id}")

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

for i, zoom_file in enumerate(zoom_files):
    # Make a copy of the template for each asset
    asset = copy.deepcopy(assets_template)
    
    # Replace row_data with the current zoom_file (URL)
    asset["row_data"] = f"{folder_url}{zoom_file}"
    
    # Use file name as unique global_key
    file = zoom_file.split('/', 1)[-1]
    asset["global_key"] = file
    
    # Metadata fields : mission_id
    asset["metadata_fields"][0]["value"] = f"{mission_id}" 
    
    # Extract the polygon id from the zoom file name
    polygon_id = zoom_file.split('_')[-1].replace('zoom.JPG', '')
    
    # Metadata fields : polygon_id
    asset["metadata_fields"][1]["value"] = f"{polygon_id}" 
    
    # Attach the map
    zoom_basename = os.path.basename(zoom_file)
    map_url = f"{ALLIANCECAN_URL}/{mission_id}/labelbox/attachments/{zoom_basename.replace('.JPG', '.html')}"
    
    asset["attachments"][1]["value"] = map_url
    
    # Find the corresponding wide file from file_keys
    wide_file = None
    wide_file_end = polygon_id + '.JPG'
    for key in file_keys:
        if wide_file_end in key and "zoom" not in key:
            wide_file = key
            break  # Exit the loop once the first match is found
    
    # If a wide file is found, set the attachment value
    if wide_file:
        asset["attachments"][0]["value"] = f"{folder_url}{wide_file}"
    else:
        print(f"Warning: No wide file found for {zoom_file}")
    
    # Add the updated asset to the list
    assets.append(asset)

# Import data in Labelbox
if not assets:
    print("No valid assets to upload. Exiting.")
else:
    task = dataset.create_data_rows(assets)
    task.wait_till_done()
    print(task.errors)
    task.wait_till_done()
    print(task.errors)