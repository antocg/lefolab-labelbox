# List of missions
MISSIONS=(
"" # Add mission_id
"" # Add mission_id
# Add more mission_id here
)

# To import data into Labelbox
LABELBOX_PROJECT=""     # Project name to send data rows
LABELBOX_PREFIX=""      # Prefix for the dataset name (optional)

# To generate maps
DTM_PATH="/data/$USER/labelbox/$LABELBOX_PROJECT/dtm.tif"    # Path to DTM file, if available (optional)
GITHUB_PROJECT=""       # Github project name for copying DTM overview file from GitHub repo (optional)
MAPPING_MISSION=""      # Name of the mapping mission to use for overview (optional)
