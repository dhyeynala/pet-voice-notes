import fitz
import os
from datetime import datetime
import google.generativeai as genai
from firestore_store import store_pdf_summary

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY"),
    transport="rest" 
)

def extract_text_and_summarize(file_path, user_id, pet_id, file_name, file_url):
    # Extract text
    doc = fitz.open(file_path)
    text = "\n".join([page.get_text() for page in doc])
    doc.close()

    # Use Gemini
    model = genai.GenerativeModel("models/gemini-1.5-pro-latest")
    prompt = (
        "You are a veterinary assistant AI. Read the following medical document "
        "and extract key details like symptoms, diagnosis, medications, or treatments. "
        "Give a short summary suitable for a pet health record.\n\n"
        + text[:30000]
    )

    try:
        response = model.generate_content(prompt)
        summary = response.text.strip()
    except Exception as e:
        print("Gemini error:", e)
        summary = "Summary could not be generated due to quota limits."

    # Save
    timestamp = datetime.utcnow().isoformat()
    store_pdf_summary(user_id, pet_id, summary, timestamp, file_name, file_url)

    return {"summary": summary}
