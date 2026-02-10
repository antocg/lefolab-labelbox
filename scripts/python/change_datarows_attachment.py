import labelbox as lb
import os
import requests
import xml.etree.ElementTree as ET

from dotenv import load_dotenv

mission_id = "20250402_zf2amzface_wptsouth_m3e"
project = "2025_amzface"

# Load environment variables from .env file
load_dotenv()

# Get environment variables
ALLIANCECAN_URL = os.getenv("ALLIANCECAN_URL")
LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")

# Verify environment variables are set
if not ALLIANCECAN_URL:
    raise ValueError("ALLIANCECAN_URL environment variable is not set")
if not LABELBOX_API_KEY:
    raise ValueError("LABELBOX_API_KEY environment variable is not set")

client = lb.Client(api_key=LABELBOX_API_KEY)

# Check if the dataset already exists
existing_datasets = client.get_datasets()
dataset_name = f"{project}_{mission_id}"
existing_dataset = next((ds for ds in existing_datasets if ds.name == dataset_name), None)

if existing_dataset:
    print(f"Dataset {dataset_name} already exists. Possible to update attachments.")

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


# Delete all existing attachments for each data row in the dataset
for i, zoom_file in enumerate(zoom_files):
    # Find data by global_key
    file = zoom_file.split('/', 1)[-1]
    data_row = client.get_data_row_by_global_key(file)

    dataset = data_row.dataset()
    dataset.upsert_data_rows([{ 'key': lb.UniqueId(data_row.uid), 'attachments': [] }])


# Create new attachments for each data row in the dataset
for i, zoom_file in enumerate(zoom_files):
    # Find data by global_key
    file = zoom_file.split('/', 1)[-1]
    data_row = client.get_data_row_by_global_key(file)

    # Attach the map
    zoom_basename = os.path.basename(zoom_file)
    map_url = f"{ALLIANCECAN_URL}/{mission_id}/labelbox/attachments/{zoom_basename.replace('.JPG', '.html')}"
    
    # Extract the polygon id from the zoom file name
    polygon_id = zoom_file.split('_')[-1].replace('zoom.JPG', '')
    
    # Find the corresponding wide file from file_keys
    wide_file = None
    wide_file_end = f"_{polygon_id}.JPG"
    for key in file_keys:
        if wide_file_end in key and "zoom" not in key:
            wide_file = key
            break  # Exit the loop once the first match is found

    data_row.create_attachment(attachment_type="IMAGE", attachment_value=f"{folder_url}{wide_file}", attachment_name="wide")
    data_row.create_attachment(attachment_type="HTML", attachment_value=map_url, attachment_name="map")


# OR
# Update attachments instead of delete-create
for i, zoom_file in enumerate(zoom_files):
    # Find data by global_key
    file = zoom_file.split('/', 1)[-1]
    data_row = client.get_data_row_by_global_key(file)

    # Extract the polygon id from the zoom file name
    polygon_id = zoom_file.split('_')[-1].replace('zoom.JPG', '')
    
    # Find the corresponding wide file from file_keys
    wide_file = None
    wide_file_end = f"_{polygon_id}.JPG"
    for key in file_keys:
        if wide_file_end in key and "zoom" not in key:
            wide_file = key
            break  # Exit the loop once the first match is found

    # Select the attachment to update
    attachments_to_update = [attachment for attachment 
                            in data_row.attachments()
                            if attachment.attachment_type == "IMAGE"]

    # Update the attachment
    for attachment in attachments_to_update:
        attachment.update(value=f"{folder_url}{wide_file}")