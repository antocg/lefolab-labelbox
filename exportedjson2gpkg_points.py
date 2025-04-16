import json
import os
from pathlib import Path

from dotenv import load_dotenv
import labelbox as lb
import numpy as np

import geopandas as gpd
from tqdm import tqdm

load_dotenv()

import time

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

def load_annotations(path: str) -> gpd.GeoDataFrame:
    # Initialize an empty list to store JSON objects
    images_annotations = []

    # Open the .ndjson file
    with open(path, 'r') as file:
        for line in file:
            # Parse each line as a JSON object
            json_object = json.loads(line.strip())  # .strip() removes leading/trailing whitespace
            images_annotations.append(json_object)

    translation = {
        'arbol': 'tree',
        'trepadora': 'liana',
        'otra': 'other'
    }

    parsed_annotations = []

    image_annotation = images_annotations[0]

    for image_annotation in tqdm(images_annotations, desc='Parsing annotations for each image'):
        image_name = image_annotation['data_row']['global_key']
        selected_label_id
        project_id = list(image_annotation['projects'].keys())[0]
        annotations = image_annotation['projects'][project_id]['labels'][0]['annotations']['objects']


        # annotation = annotations[0]

        for annotation in annotations:
            classes = annotation['classifications']
            if not classes: continue

            annotation_data = {'mission_id'
                               'image_name': image_name,
                               'image_url',
                               'plant_type': translation[annotation['value']],
                               'scientific_name': None,
                               'gbif_id': None,
                                }
            
            class_type = classes[0]

            for class_type in classes:
                # if class_type['value'] == 'nome_vulgar':
                #     annotation_data['common_name'] = class_type['text_answer']['content']

                # if class_type['value'] == 'familia':
                #     annotation_data['family'] = class_type['text_answer']['content']

                # if class_type['value'] == 'nome_cientifico':
                #     annotation_data['scientific_name'] = class_type['text_answer']['content']

                if class_type['value'] == 'Taxon':
                    annotation_data['scientific_name'] = class_type['checklist_answers'][0]['name']
            
            parsed_annotations.append(annotation_data)

            # mask_url = annotation['mask']['url']

            # mask = get_mask_with_retries(mask_url, headers=lb_client.headers)
            # if mask:
            #     mask = mask.convert('L')
            #     segmentation = mask_to_polygon(np.array(mask), simplify_tolerance=1.0)
            #     annotation_data['segmentation'] = segmentation
            #     parsed_annotations.append(annotation_data)
            # else:
            #     print('Skipping annotation, could not get the mask.')

    gdf = gpd.GeoDataFrame(parsed_annotations, crs=None)
    gdf.set_geometry('segmentation', inplace=True)

    return gdf


if __name__ == '__main__':
    annotations_path = 'C:\Users\Antoine\Documents\GitHub\lefolab-utils\Labelbox\data\Export  project - 2024_BCI_northeast - 4_8_2025.ndjson'
    path = "C:/Users/Antoine/Documents/GitHub/lefolab-utils/Labelbox/data/Export  project - 2024_BCI_northeast - 4_8_2025.ndjson"
    parsed_annotations_gdf = load_annotations(annotations_path)
    print(parsed_annotations_gdf.columns)
    parsed_annotations_gdf.to_file('./data.gpkg')
