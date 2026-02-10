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

# Activate the conda environment
source /opt/miniconda3/bin/activate labelbox

# Get the project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Set environment variables
set -a
source "${PROJECT_ROOT}/.env"
set +a

# Define projects array
projects=("2025_TBS" "2024_BCI" "2024_BCI_PLOTS" "2024_BCI_OFFISLAND" "2024_BCI_PLOTS_OLD" "2024_BCI_NORTHEAST_OLD")
output_dir="/data/sharing/labelbox/exports"

# Loop through each project
for project in "${projects[@]}"; do
    # Get the corresponding environment variable
    env_var="LABELBOX_${project}"
    project_id="${!env_var}"
    
    if [ -z "$project_id" ]; then
        error_message "Environment variable ${env_var} is not set"
        continue
    fi
    
    log_message "Processing project: ${project}"

    # Run the Python script
    python "${PROJECT_ROOT}/scripts/python/export_data.py" \
        --project_id "$project_id" \
        --output "$output_dir"
    check_command "Export for project ${project}"
    
    log_message "Completed export for ${project}"
done

# Rename TBS export file
tbs_export_file=$(find "${output_dir}" -maxdepth 1 -type f -name "2025_TBS.json")
if [ -f "$tbs_export_file" ]; then
    new_tbs_file="${output_dir}/labelbox_exports_2025_tbs.json"
    mv "$tbs_export_file" "$new_tbs_file"
    log_message "Renamed TBS export to ${new_tbs_file}"
else
    error_message "TBS export file not found for renaming"
fi

# Merge all BCI JSON files into a single file
merged_bci_file="${output_dir}/labelbox_exports_2024_bci.json"
log_message "Merging BCI exports into ${merged_bci_file}"

mapfile -t bci_files < <(find "${output_dir}" -maxdepth 1 -type f -name "2024_BCI*.json" ! -name "2024_BCI_Off-island.json" ! -name "labelbox_exports_2024_bci.json")

if [ ${#bci_files[@]} -gt 0 ]; then
    # Clear the merged file if it exists
    > "$merged_bci_file"

    for file in "${bci_files[@]}"; do
        log_message "Adding $(basename "$file") to merged BCI export"
        cat "$file" >> "$merged_bci_file"
    done

    log_message "Successfully merged ${#bci_files[@]} BCI files into ${merged_bci_file}"
else
    log_message "No BCI files found to merge"
fi

# Transfer files to Arbutus server
log_message "Transferring export files to Arbutus server"

rclone --config /etc/rclone.conf copy "$output_dir" AllianceCanBuckets:lefolab_labelbox --include "labelbox_exports_2025_tbs.json" --include "labelbox_exports_2024_bci.json"
check_command "Transfer to Arbutus server"
log_message "Transfer completed successfully"

log_message "All exports, merges and transfers completed"
