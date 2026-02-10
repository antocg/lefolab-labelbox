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

DTM_PATH=""             # Path to DTM file, if available (optional)
GITHUB_PROJECT=""       # Github project name for copying DTM overview file from GitHub repo (optional)
MAPPING_MISSION=""      # Name of the mapping mission to use for overview (optional)

OUTPUT_DIR="/data/$USER/Labelbox/$LABELBOX_PROJECT"
mkdir -p "$OUTPUT_DIR"

# Loop through each project
for MISSION in "${MISSIONS[@]}"; do
    echo "Generating maps for $MISSION. Output will be saved in $OUTPUT_DIR"

    if [ -n "$MAPPING_MISSION" ]; then
        MAPPING_MISSION_ARG="--mapping_mission $MAPPING_MISSION"
    else
        MAPPING_MISSION_ARG=""
    fi
    
    if [ -z "$DTM_PATH" ]; then
        echo "DTM path is not set for $MISSION"
        python /app/lefolab-utils/Labelbox/generate_maps.py --mission_id $MISSION --output_dir $OUTPUT_DIR $MAPPING_MISSION_ARG
    else
        if [ -n "$GITHUB_PROJECT" ]; then
            GITHUB_PROJECT_ARG="--github_project $GITHUB_PROJECT"
        else
            GITHUB_PROJECT_ARG=""
        fi
        python /app/lefolab-utils/Labelbox/generate_maps.py --mission_id $MISSION --dtm_path  $DTM_PATH --output_dir $OUTPUT_DIR $GITHUB_PROJECT_ARG $MAPPING_MISSION_ARG
    fi
    
    echo "Maps generated for $MISSION and saved in $OUTPUT_DIR"
done
