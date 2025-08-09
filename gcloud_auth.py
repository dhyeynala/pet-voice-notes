"""Google Cloud authentication helpers."""

import os

from google.auth import default
from google.auth.exceptions import DefaultCredentialsError
from dotenv import load_dotenv


load_dotenv()


def setup_google_cloud_auth() -> bool:
    """Set up Google Cloud authentication with an explicit project.

    Returns True when credentials can be resolved, False otherwise.
    Never raises on missing configuration so CI/imports remain safe.
    """

    try:
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if not project_id:
            # Do not fail here; some environments (e.g., CI) intentionally lack secrets.
            print("GOOGLE_CLOUD_PROJECT is not set; continuing without explicit binding")

        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "gcloud-key.json")
        if project_id:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        # Attempt to resolve default credentials
        credentials, project = default()
        print("Google Cloud authentication successful")
        print(f"Project: {project}")
        print(f"Credentials: {type(credentials).__name__}")
        return True

    except DefaultCredentialsError as exc:
        print(f"Google Cloud authentication failed: {exc}")
        print("Make sure gcloud-key.json is available or set GOOGLE_APPLICATION_CREDENTIALS")
        return False
    except Exception as exc:
        print(f"Unexpected authentication error: {exc}")
        return False


if __name__ == "__main__":
    setup_google_cloud_auth()
