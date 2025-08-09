# gcloud_auth.py
import os
from google.auth import default
from google.auth.exceptions import DefaultCredentialsError
from dotenv import load_dotenv

load_dotenv()

def setup_google_cloud_auth():
    """Set up Google Cloud authentication with explicit project."""
    try:
        # Set environment variables
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if not project_id:
            # Avoid raising here; allow caller to decide how to handle missing config
            print("⚠️ GOOGLE_CLOUD_PROJECT is not set; skipping explicit project binding")
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "gcloud-key.json")
        
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        
        # Test authentication
        credentials, project = default()
        print("Google Cloud authentication successful")
        print(f"Project: {project}")
        print(f"Credentials: {type(credentials).__name__}")
        
        return True
        
    except DefaultCredentialsError as e:
        print(f"Google Cloud authentication failed: {e}")
        print("Make sure gcloud-key.json is in the project root")
        return False
    except Exception as e:
        print(f"Unexpected authentication error: {e}")
        return False

if __name__ == "__main__":
    setup_google_cloud_auth()
