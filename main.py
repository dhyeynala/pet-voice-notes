# main.py

import os
from dotenv import load_dotenv
import openai
from transcribe import transcribe_audio
from summarize_openai import summarize_text
from firestore_store import store_to_firestore

# Load env variables
load_dotenv()

# Set OpenAI key
openai.api_key = os.getenv("OPENAI_API_KEY")

def main():
    print(" Starting real-time voice notes system...")

    try:
        # Transcribe from mic
        transcript = transcribe_audio()
        print("\n TRANSCRIPT:\n", transcript)

        # Summarize
        summary = summarize_text(transcript)
        print("\n SUMMARY:\n", summary)

        # Store in Firestore
        user_id = "demo-user"
        pet_id = "tom"
        store_to_firestore(user_id, pet_id, transcript, summary)

    except Exception as e:
        print(f" Error: {e}")

if __name__ == "__main__":
    main()
