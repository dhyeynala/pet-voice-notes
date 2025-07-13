# uvicorn_config.py
import os

# Uvicorn configuration
bind = "localhost:8000"
reload = True
reload_dirs = ["."]
reload_excludes = [
    ".venv/*",
    ".venv/**/*",
    "__pycache__/*",
    "*.pyc",
    ".git/*",
    ".vscode/*",
    "*.log",
    "*.backup",
    "*.old"
]

# Only include specific directories to watch
reload_includes = [
    "*.py",
    "public/*.html",
    "public/*.js",
    "public/*.css"
]
