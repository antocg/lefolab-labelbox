#!/bin/bash

# Exit on any error
set -e

# Function for logging with timestamp
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function for error logging
error_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >&2
}

# Function to check if command succeeded
check_command() {
    if [ $? -ne 0 ]; then
        error_message "$1 failed"
        exit 1
    fi
}

# List of missions
MISSIONS=(
"" # Add mission_id
"" # Add mission_id
# Add more mission_id here
)

# To import data into Labelbox
LABELBOX_PREFIX=""      # Prefix for the dataset name
LABELBOX_PROJECT=""     # Project name to send data rows

# To generate maps
DTM_PATH=""             # Path to DTM file, if available (optional)
GITHUB_PROJECT=""       # Github project name for copying DTM overview file from GitHub repo (optional)
MAPPING_MISSION=""      # Name of the mapping mission to use for overview (optional)

# Validate required paths exist
if [ ! -z "$DTM_PATH" ] && [ ! -f "$DTM_PATH" ]; then
    error_message "DTM file not found at: $DTM_PATH"
    exit 1
fi

# Check if required directories exist
if [ ! -d "/mnt/nfs/lefodata/data/drone_missions/" ]; then
    error_message "Source directory not found: /mnt/nfs/lefodata/data/drone_missions/"
    exit 1
fi

OUTPUT_DIR="/data/$USER/Labelbox/$LABELBOX_PROJECT"
mkdir -p "$OUTPUT_DIR"

# Loop through each mission
for MISSION in "${MISSIONS[@]}"; do
    log_message "Processing mission: $MISSION"

    # Check if mission directory exists
    YEAR="${MISSION:0:4}"
    if [ ! -d "/mnt/nfs/lefodata/data/drone_missions/$YEAR/$MISSION" ]; then
        error_message "Mission directory not found: /mnt/nfs/lefodata/data/drone_missions/$YEAR/$MISSION"
        continue
    fi

    log_message "Copying data from lefodata to Arbutus for $MISSION"
    rclone --config /etc/rclone.conf copy /mnt/nfs/lefodata/data/drone_missions/$YEAR/$MISSION/ AllianceCanBuckets:$MISSION -c
    check_command "rclone copy for $MISSION"
    log_message "Data copied to Arbutus for $MISSION"

    source /opt/miniconda3/bin/activate
    conda activate labelbox
    check_command "conda activate labelbox"
    
    log_message "Importing data rows for $MISSION in Labelbox"
    python /app/lefolab-utils/Labelbox/import_datarows.py --mission_id "$MISSION" --prefix "$LABELBOX_PREFIX"
    check_command "import_datarows.py for $MISSION"
    log_message "Data rows imported for $MISSION in Labelbox"

    log_message "Generating maps for $MISSION. Output will be saved in $OUTPUT_DIR"
    if [ -n "$MAPPING_MISSION" ]; then
        MAPPING_MISSION_ARG="--mapping_mission $MAPPING_MISSION"
    else
        MAPPING_MISSION_ARG=""
    fi
    
    if [ -z "$DTM_PATH" ]; then
        log_message "DTM path is not set for $MISSION"
        python /app/lefolab-utils/Labelbox/generate_maps.py --mission_id $MISSION --output_dir $OUTPUT_DIR $MAPPING_MISSION_ARG
        check_command "generate_maps.py (without DTM) for $MISSION"
    else
        if [ -n "$GITHUB_PROJECT" ]; then
            GITHUB_PROJECT_ARG="--github_project $GITHUB_PROJECT"
        else
            GITHUB_PROJECT_ARG=""
        fi
        python /app/lefolab-utils/Labelbox/generate_maps.py --mission_id $MISSION --dtm_path  $DTM_PATH --output_dir $OUTPUT_DIR $GITHUB_PROJECT_ARG $MAPPING_MISSION_ARG
        check_command "generate_maps.py (with DTM) for $MISSION"
    fi
    log_message "Maps generated for $MISSION and saved in $OUTPUT_DIR"

    log_message "Sending data rows for $MISSION to $LABELBOX_PROJECT"
    python /app/lefolab-utils/Labelbox/send_to_annotate.py --mission_id "$MISSION" --prefix "$LABELBOX_PREFIX" --project "$LABELBOX_PROJECT"
    check_command "send_to_annotate.py for $MISSION"
    log_message "Data rows sent for $MISSION to $LABELBOX_PROJECT"

    conda deactivate

    log_message "Copying maps to Arbutus for $MISSION"
    rclone --config /etc/rclone.conf copy "$OUTPUT_DIR/$MISSION/" "AllianceCanBuckets:$MISSION" -c
    check_command "rclone copy maps for $MISSION"
    log_message "Maps copied to Arbutus for $MISSION"

    log_message "Mission $MISSION completed successfully"

done

log_message "All missions completed successfully"
