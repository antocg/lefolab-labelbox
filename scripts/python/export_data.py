import argparse
import json
import labelbox as lb
import logging
import os
import sys

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
parser = argparse.ArgumentParser(description="Export data from Labelbox.")
parser.add_argument("--project_id", required=True, help="Labelbox Project ID")
parser.add_argument("--output", required=True, help="Output folder for JSON file")
args = parser.parse_args()

project_id = args.project_id
project = client.get_project(project_id)

# Set the export params to include/exclude certain fields.
export_params = {
    "attachments": True,
    "metadata_fields": True,
    "data_row_details": True,
    "project_details": True,
    "label_details": True,
    "performance_details": True,
    "interpolated_frames": False,
    "embeddings": False,
}

export_task = project.export(params=export_params)
export_task.wait_till_done()

# Log all results at once
logger.info("Export task results: %s", export_task.result)

output_folder = args.output
os.makedirs(output_folder, exist_ok=True)
output_file = os.path.join(output_folder, f"{project.name}.json")

# Clear the file before writing
open(output_file, 'w').close()

with open(output_file, "a", encoding="utf-8") as f:
    for row in export_task.get_buffered_stream():
        f.write(json.dumps(row.json))
        f.write("\n")

logger.info(f"Exported results as JSON to {output_file}")