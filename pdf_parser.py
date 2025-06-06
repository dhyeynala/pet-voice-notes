#pdf_parser.py

import fitz 
import os
from datetime import datetime
import google.generativeai as genai
from firestore_store import store_pdf_summary

# Load Gemini key
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def extract_text_and_summarize(file_path, user_id, pet_id, file_name, file_url):
    # Step 1: Extract text
    doc = fitz.open(file_path)
    text = "\n".join([page.get_text() for page in doc])
    doc.close()

    # Step 2: Summarize with Gemini
    model = genai.GenerativeModel("gemini-pro")
    prompt = (
        "You are a veterinary assistant AI. Read the following medical document "
        "and extract key details like symptoms, diagnosis, medications, or treatments. "
        "Give a short summary suitable for a pet health record.\n\n"
        + text[:30000]
    )
    summary = model.generate_content(prompt).text.strip()

    # Step 3: Store in Firestore
    timestamp = datetime.utcnow().isoformat()
    store_pdf_summary(user_id, pet_id, summary, timestamp, file_name, file_url)

    return {"summary": summary}
