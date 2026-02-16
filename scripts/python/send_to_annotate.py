import argparse
import labelbox as lb
import logging
import os
import sys
import xml.etree.ElementTree as ET

from dotenv import load_dotenv

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
load_dotenv()

# Get environment variables
LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")

# Verify environment variables are set
if not LABELBOX_API_KEY:
    logger.error("LABELBOX_API_KEY environment variable is not set")
    raise ValueError("LABELBOX_API_KEY environment variable is not set")

client = lb.Client(api_key=LABELBOX_API_KEY)

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Send data rows to Labelbox project.")
parser.add_argument("--mission_id", required=True, help="Mission ID to generate the dataset.")
parser.add_argument("--project", required=True, help="Project name where the data rows are sent.")
parser.add_argument("--prefix", help="Prefix for the dataset name.")
args = parser.parse_args()

mission_id = args.mission_id
project_name = args.project

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

# Find the project by name
projects = client.get_projects()
project = next((p for p in projects if p.name == project_name), None)
if not project:
    logger.error(f"Project '{project_name}' not found.")

# Send to annotate (create batch)
dataset_name = f"{prefix}_{mission_id}"
datasets = client.get_datasets()
dataset = next((ds for ds in datasets if ds.name == dataset_name), None)
if not dataset:
    logger.warning(f"Dataset '{dataset_name}' not found. Skipping.")
else:
    batch = project.create_batches_from_dataset(
        name_prefix=f"{mission_id}_",
        dataset_id=dataset.uid,
        priority=3
    )
    logger.info(f"Batch created for {mission_id}: {batch.result()}")
