#!/bin/bash

# Copy PetPages project to GitHub repository
# Usage: ./copy_to_github.sh /path/to/your/github/repo

if [ -z "$1" ]; then
    echo "Usage: $0 /path/to/your/github/repo"
    echo "Example: $0 /Users/dhyeydesai/Desktop/my-petpages-repo"
    exit 1
fi

TARGET_DIR="$1"
SOURCE_DIR="/Users/dhyeydesai/Desktop/PETPAGES/pet-6-structurechange_ui_samepage"

echo "Copying PetPages project to: $TARGET_DIR"

# Create target directory if it doesn't exist
mkdir -p "$TARGET_DIR"

# Copy all files except sensitive ones and .git
rsync -av \
    --exclude='.git/' \
    --exclude='.env' \
    --exclude='gcloud-key.json' \
    --exclude='__pycache__/' \
    --exclude='.venv/' \
    --include='.*' \
    "$SOURCE_DIR/" "$TARGET_DIR/"

echo "✅ Copy completed!"
