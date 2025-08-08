#!/bin/bash

# Copy PetPulse project to GitHub repository
# Usage: ./copy_to_github.sh /path/to/your/github/repo

if [ -z "$1" ]; then
    echo "Usage: $0 /path/to/your/github/repo"
    echo "Example: $0 /Users/dhyeydesai/Desktop/my-petpulse-repo"
    exit 1
fi

TARGET_DIR="$1"
SOURCE_DIR="/Users/dhyeydesai/Desktop/PETPULSE/pet-6-structurechange_ui_samepage"

echo "Copying PetPulse project to: $TARGET_DIR"

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
echo ""
echo "Next steps:"
echo "1. cd $TARGET_DIR"
echo "2. Create your .env file: cp .env.example .env"
echo "3. Add your API keys to .env"
echo "4. Add your gcloud-key.json file"
echo "5. git add ."
echo "6. git commit -m 'Add PetPulse application'"
echo "7. git push"
