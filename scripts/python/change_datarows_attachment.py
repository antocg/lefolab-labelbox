import argparse
import labelbox as lb
import os
import requests
import xml.etree.ElementTree as ET

from dotenv import load_dotenv


def get_mission_files(mission_id, alliancecan_url):
    """
    Fetch all files for a given mission from Alliance Canada.
    
    Args:
        mission_id (str): Mission ID to fetch files for
        alliancecan_url (str): Base URL for Alliance Canada
        
    Returns:
        tuple: (file_keys, closeup_files, folder_url)
    """
    folder_url = f"{alliancecan_url}/{mission_id}/"
    
    response = requests.get(folder_url)
    if response.status_code != 200:
        print(f"Failed to fetch XML. HTTP Status Code: {response.status_code}")
        return None, None, None
    
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
    
    print(f"{len(file_keys)} pictures found for this mission : {mission_id}")
    
    # Filter for close-up pictures (detect naming convention)
    closeup_files = [key for key in file_keys if "tele" in key]
    
    if closeup_files:
        print(f"{len(closeup_files)} close-up pictures (tele) found for this mission : {mission_id}")
    else:
        closeup_files = [key for key in file_keys if "zoom" in key]
        if closeup_files:
            print("Using legacy naming convention (zoom).")
            print(f"{len(closeup_files)} close-up pictures (zoom) found for this mission : {mission_id}")
        else:
            print(f"No close-up pictures found for this mission : {mission_id}")
    
    return file_keys, closeup_files, folder_url


def delete_attachments(client, closeup_files):
    """
    Delete all existing attachments for each data row in the dataset.
    
    Args:
        client: Labelbox client instance
        closeup_files (list): List of close-up file keys
    """
    print("Deleting existing attachments...")
    for i, closeup_file in enumerate(closeup_files):
        # Find data by global_key
        file = closeup_file.split('/', 1)[-1]
        data_row = client.get_data_row_by_global_key(file)
        
        dataset = data_row.dataset()
        dataset.upsert_data_rows([{'key': lb.UniqueId(data_row.uid), 'attachments': []}])
        
        if (i + 1) % 10 == 0:
            print(f"Deleted attachments for {i + 1}/{len(closeup_files)} data rows")
    
    print(f"Deleted attachments for all {len(closeup_files)} data rows")


def create_attachments(client, closeup_files, file_keys, folder_url, mission_id, alliancecan_url):
    """
    Create new attachments for each data row in the dataset.
    
    Args:
        client: Labelbox client instance
        closeup_files (list): List of close-up file keys (zoom or tele)
        file_keys (list): List of all file keys
        folder_url (str): URL of the folder
        mission_id (str): Mission ID
        alliancecan_url (str): Base URL for Alliance Canada
    """
    print("Creating new attachments...")
    for i, closeup_file in enumerate(closeup_files):
        # Find data by global_key
        file = closeup_file.split('/', 1)[-1]
        data_row = client.get_data_row_by_global_key(file)
        
        # Attach the map
        closeup_basename = os.path.basename(closeup_file)
        map_url = f"{alliancecan_url}/{mission_id}/labelbox/attachments/{closeup_basename.replace('.JPG', '.html')}"
        
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
        
        # Find the corresponding wide file from file_keys
        matching_wide_files = [key for key in file_keys if wide_file_end in key and exclusion_keyword not in key]
        
        if len(matching_wide_files) > 1:
            print(f"Warning: Multiple wide pictures found for {closeup_file}: {matching_wide_files}. Using the first match.")
        
        wide_file = matching_wide_files[0] if matching_wide_files else None
        
        if wide_file:
            data_row.create_attachment(attachment_type="IMAGE", attachment_value=f"{folder_url}{wide_file}", attachment_name="wide")
        else:
            print(f"Warning: No wide file found for {closeup_file} (polygon_id: {polygon_id})")
        
        data_row.create_attachment(attachment_type="HTML", attachment_value=map_url, attachment_name="map")
        
        if (i + 1) % 10 == 0:
            print(f"Created attachments for {i + 1}/{len(closeup_files)} data rows")
    
    print(f"Created attachments for all {len(closeup_files)} data rows")

# OR
# Update attachments instead of delete-create
# for i, zoom_file in enumerate(zoom_files):
#     # Find data by global_key
#     file = zoom_file.split('/', 1)[-1]
#     data_row = client.get_data_row_by_global_key(file)

#     # Extract the polygon id from the zoom file name
#     polygon_id = zoom_file.split('_')[-1].replace('zoom.JPG', '')
    
#     # Find the corresponding wide file from file_keys
#     wide_file = None
#     wide_file_end = f"_{polygon_id}.JPG"
#     for key in file_keys:
#         if wide_file_end in key and "zoom" not in key:
#             wide_file = key
#             break  # Exit the loop once the first match is found

#     # Select the attachment to update
#     attachments_to_update = [attachment for attachment 
#                             in data_row.attachments()
#                             if attachment.attachment_type == "IMAGE"]

#     # Update the attachment
#     for attachment in attachments_to_update:
#         attachment.update(value=f"{folder_url}{wide_file}")

def main():
    """Main function to manage data row attachments in Labelbox."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Manage data row attachments in Labelbox.")
    parser.add_argument("--mission_id", required=True, help="Mission ID to process.")
    parser.add_argument("--project", required=True, help="Project name.")
    parser.add_argument("-d", "--delete", action="store_true", help="Delete existing attachments.")
    parser.add_argument("-c", "--create", action="store_true", help="Create new attachments.")
    args = parser.parse_args()
    
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
    
    # Initialize Labelbox client
    client = lb.Client(api_key=LABELBOX_API_KEY)
    
    # Check if the dataset already exists
    existing_datasets = client.get_datasets()
    dataset_name = f"{args.project}_{args.mission_id}"
    existing_dataset = next((ds for ds in existing_datasets if ds.name == dataset_name), None)
    
    if existing_dataset:
        print(f"Dataset {dataset_name} found.")
    else:
        print(f"Dataset {dataset_name} not found.")
        return
    
    # Get mission files
    file_keys, closeup_files, folder_url = get_mission_files(args.mission_id, ALLIANCECAN_URL)
    
    if not closeup_files:
        print("No close-up files found. Exiting.")
        return
    
    # Execute requested operations
    if args.delete:
        delete_attachments(client, closeup_files)
    
    if args.create:
        create_attachments(client, closeup_files, file_keys, folder_url, args.mission_id, ALLIANCECAN_URL)
    
    if not args.delete and not args.create:
        print("No operation specified. Use -d to delete attachments or -c to create attachments.")


if __name__ == "__main__":
    main()