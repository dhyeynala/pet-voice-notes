#!/bin/bash
# start_server.sh - Start the PetPages development server

echo "🚀 Starting PetPages development server..."
echo "📁 Project: $(pwd)"
echo "🐍 Python: $(which python)"
echo ""

# Start Uvicorn with proper exclusions to prevent .venv reload loops
python -m uvicorn api_server:app \
  --reload \
  --host localhost \
  --port 8000 \
  --reload-exclude ".venv" \
  --reload-exclude "__pycache__" \
  --reload-exclude "*.pyc" \
  --reload-exclude ".git" \
  --reload-exclude ".vscode" \
  --reload-exclude "*.log" \
  --reload-exclude "*.backup" \
  --reload-exclude "uvicorn_config.py" \
  --reload-exclude "start_server.sh"
