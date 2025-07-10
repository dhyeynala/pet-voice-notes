#pdf_parser.py

import fitz
import os
from openai import OpenAI
from datetime import datetime
from firestore_store import store_pdf_summary
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extract_text_and_summarize(file_path, user_id, pet_id, file_name, file_url):
    try:
        # Step 1: Extract PDF text
        doc = fitz.open(file_path)
        text = "\n".join([page.get_text() for page in doc])
        doc.close()
        
        if not text.strip():
            return {"error": "PDF appears to be empty or contains no readable text"}

        # Step 2: Summarize using GPT-4o (new SDK style)
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a veterinary assistant AI. Summarize this medical document. "
                            "Extract key points like symptoms, diagnosis, treatments, medications, and vet advice. "
                            "Keep it concise and useful for a pet health timeline."
                        )
                    },
                    {"role": "user", "content": text[:12000]}
                ],
                temperature=0.5
            )
            summary = response.choices[0].message.content.strip()
        except Exception as e:
            print("OpenAI error:", e)
            summary = "Summary could not be generated due to OpenAI error."

        # Step 3: Store in Firestore
        timestamp = datetime.utcnow().isoformat()
        store_pdf_summary(user_id, pet_id, summary, timestamp, file_name, file_url)

        return {"summary": summary}
    
    except Exception as e:
        print(f"PDF processing error: {e}")
        return {"error": f"Failed to process PDF: {str(e)}"}
