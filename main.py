# main.py

import os
import argparse
from dotenv import load_dotenv
import openai
from transcribe import transcribe_audio
from summarize_openai import summarize_text, classify_pet_content
from firestore_store import store_to_firestore, store_analytics_from_voice

# Load env variables
load_dotenv()

# Set OpenAI key
openai.api_key = os.getenv("OPENAI_API_KEY")


def main(user_id, pet_id):
    print(" Starting real-time voice notes system...")

    try:
        transcript = transcribe_audio(duration_seconds=20)
        print("\n TRANSCRIPT:\n", transcript)

        summary = summarize_text(transcript)
        print("\n SUMMARY:\n", summary)

        # Classify content to check if it's daily activity
        classification = classify_pet_content(transcript)
        print(f"\n CLASSIFICATION: {classification}")

        # Store to voice-notes collection
        store_to_firestore(user_id, pet_id, transcript, summary)
        print(" Data stored to Firestore voice-notes.")

        # If daily activity content, also store in analytics for dashboard visibility
        if classification.get('classification') == 'DAILY_ACTIVITY':
            store_analytics_from_voice(pet_id, transcript, summary, classification)
            print(" Daily activity data also stored to analytics.")

        # Return for FastAPI
        return {"transcript": transcript, "summary": summary, "classification": classification}

    except Exception as e:
        print(f" Error: {e}")
        return {"error": str(e)}


# CLI usage (safe to keep)
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice note system for pets.")
    parser.add_argument("--user_id", required=True, help="User ID for Firestore")
    parser.add_argument("--pet_id", required=True, help="Pet ID for Firestore")
    args = parser.parse_args()

    main(args.user_id, args.pet_id)
