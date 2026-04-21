import argparse
import json
import labelbox as lb
import logging
import os
import pandas as pd
import requests
import sys

from dotenv import load_dotenv
from pathlib import Path
from tqdm import tqdm

tqdm.pandas()

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
LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")

# Verify environment variables are set
if not LABELBOX_API_KEY:
    logger.error("LABELBOX_API_KEY environment variable is not set")
    raise ValueError("LABELBOX_API_KEY environment variable is not set")

client = lb.Client(api_key=LABELBOX_API_KEY)

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Export ontology from Labelbox.")
parser.add_argument("--ontology_id", required=True, help="Labelbox Ontology ID")
parser.add_argument("--prefix", required=True, help="Prefix for CSV file")
parser.add_argument("--output", required=True, help="Output folder for CSV file")
args = parser.parse_args()

ontology = client.get_ontology(args.ontology_id)
ontology_json = ontology.normalized

options = ontology_json["tools"][0]["classifications"][0]["options"]

df = pd.DataFrame([
    {
        "featureSchemaId": o.get("featureSchemaId"),
        "label": o.get("label"),
        "value": o.get("value"),
        "position": o.get("position"),
    }
    for o in options
])

df = df.drop(columns=["featureSchemaId", "position"]).rename(columns={"value": "gbif_id"})

output_path = Path(args.output)
output_path.mkdir(parents=True, exist_ok=True)
df.to_csv(output_path / f"{args.prefix}_ontology.csv", index=False, encoding="utf-8")

def get_gbif_info(gbif_id):
    for _ in range(3):
        try:
            r = requests.get(f"https://api.gbif.org/v1/species/{gbif_id}")
            r.raise_for_status()
            data = r.json()
            return pd.Series({
                "canonicalName": data.get("canonicalName"),
                "gbif_rank": data.get("rank"),
                "gbif_family": data.get("family"),
            })
        except Exception:
            pass
    return pd.Series({"canonicalName": None, "gbif_rank": None, "gbif_family": None})

df[["canonicalName", "gbif_rank", "gbif_family"]] = df["gbif_id"].progress_apply(get_gbif_info)
df.to_csv(output_path / f"{args.prefix}_ontology_gbif.csv", index=False, encoding="utf-8")