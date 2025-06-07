import os
import fitz  # PyMuPDF
from datetime import datetime
from firestore_store import store_pdf_summary
import google.generativeai as genai
from google.auth import load_credentials_from_file
from dotenv import load_dotenv

# ✅ Load .env (for consistency, even if GEMINI_API_KEY is unused)
load_dotenv()

# ✅ Load service account credentials from gcloud-key.json
creds, _ = load_credentials_from_file(
    "gcloud-key.json",
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)

# ✅ Configure Gemini with IAM credentials
genai.configure(
    credentials=creds,
    transport="rest"
)

def extract_text_and_summarize(file_path, user_id, pet_id, file_name, file_url):
    # Step 1: Extract text from PDF
    try:
        doc = fitz.open(file_path)
        text = "\n".join([page.get_text() for page in doc])
        doc.close()
    except Exception as e:
        return {"summary": f"[Error reading PDF: {str(e)}]"}

    # Step 2: Create Gemini model client (with IAM auth)
    model = genai.GenerativeModel("models/gemini-1.5-pro-latest")

    prompt = (
        "You are a veterinary assistant AI. Read the following medical document "
        "and extract key information such as symptoms, treatments, diagnoses, and medications. "
        "Give a short summary suitable for a pet health record.\n\n"
        + text[:30000]  # Truncate to stay within model limits
    )

    # Step 3: Generate summary from Gemini
    try:
        response = model.generate_content(prompt)
        summary = response.text.strip()
    except Exception as e:
        summary = f"[Error summarizing PDF: {str(e)}]"

    # Step 4: Store result in Firestore
    timestamp = datetime.utcnow().isoformat()
    store_pdf_summary(user_id, pet_id, summary, timestamp, file_name, file_url)

    return {"summary": summary}
