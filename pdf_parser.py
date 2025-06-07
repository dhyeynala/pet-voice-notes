import os
import fitz
from datetime import datetime
import google.generativeai as genai
from firestore_store import store_pdf_summary
from google.auth import load_credentials_from_file

# ✅ Load service account credentials (OAuth)
creds, _ = load_credentials_from_file("gcloud-key.json", scopes=["https://www.googleapis.com/auth/cloud-platform"])

# ✅ Configure Gemini with service account credentials
genai.configure(credentials=creds, transport="rest")

def extract_text_and_summarize(file_path, user_id, pet_id, file_name, file_url):
    # Step 1: Extract text from PDF
    doc = fitz.open(file_path)
    text = "\n".join([page.get_text() for page in doc])
    doc.close()

    # Step 2: Generate summary using Gemini with IAM credentials
    model = genai.GenerativeModel("models/gemini-1.5-pro-latest")

    prompt = (
        "You are a veterinary assistant AI. Read the following medical document "
        "and extract key details like symptoms, diagnosis, medications, or treatments. "
        "Give a short summary suitable for a pet health timeline.\n\n"
        + text[:30000]
    )

    try:
        response = model.generate_content(prompt)
        summary = response.text.strip()
    except Exception as e:
        summary = f"[Error summarizing PDF: {str(e)}]"

    # Step 3: Store result
    timestamp = datetime.utcnow().isoformat()
    store_pdf_summary(user_id, pet_id, summary, timestamp, file_name, file_url)

    return {"summary": summary}
