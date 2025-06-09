#main.py

import os
import argparse
from dotenv import load_dotenv
import openai
from transcribe import transcribe_audio
from summarize_openai import summarize_text
from firestore_store import store_to_firestore

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

        store_to_firestore(user_id, pet_id, transcript, summary)
        print(" Data stored to Firestore.")

        # Return for FastAPI
        return {
            "transcript": transcript,
            "summary": summary
        }

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
