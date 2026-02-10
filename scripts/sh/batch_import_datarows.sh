#!/bin/bash

# Activate the conda environment
source /opt/miniconda3/bin/activate
conda activate labelbox

# List of missions_id
MISSIONS=(
"" # Add mission_id
"" # Add mission_id
# Add more mission_id here
)

LABELBOX_PREFIX=""  # Prefix for the dataset name

# Loop through each mission
for MISSION in "${MISSIONS[@]}"; do
    echo "Importing data rows for $MISSION in Labelbox"
    python /app/lefolab-utils/Labelbox/import_datarows.py --mission_id "$MISSION" --prefix "$LABELBOX_PREFIX"
done
