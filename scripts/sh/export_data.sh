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

# Set environment variables
set -a
source /data/acarong/GitHub/lefolab-utils/.env
set +a

# Define projects array
projects=("2025_TBS" "2024_BCI_NORTHEAST" "2024_BCI_PLOTS" "2024_BCI_50HAPLOT" "2024_BCI_OFFISLAND" "2024_BCI_NORTHEAST_OLD")
output_dir="/data/sharing/Labelbox/exports"

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
    python $HOME/GitHub/lefolab-utils/Labelbox/export_data.py \
        --project_id "$project_id" \
        --output "$output_dir"
    check_command "Export for project ${project}"
    
    log_message "Completed export for ${project}"
done

# Merge all BCI JSON files into a single file
merged_bci_file="${output_dir}/2024_BCI_exports.json"
log_message "Merging BCI exports into ${merged_bci_file}"

mapfile -t bci_files < <(find "${output_dir}" -maxdepth 1 -type f -name "2024_BCI*.json" ! -name "2024_BCI_exports.json")

for file in "${bci_files[@]}"; do
    log_message "Found BCI file: $(basename "$file")"
done

if [ ${#bci_files[@]} -gt 0 ]; then
    # Clear the merged file if it exists
    > "$merged_bci_file"

    for file in "${bci_files[@]}"; do
        log_message "Adding $file to merged BCI export"
        cat "$file" >> "$merged_bci_file"
    done

    log_message "Successfully merged ${#bci_files[@]} BCI files into ${merged_bci_file}"
else
    log_message "No BCI files found to merge"
fi

log_message "All exports and merges completed"
