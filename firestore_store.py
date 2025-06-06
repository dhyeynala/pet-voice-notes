# firestore_store.py

import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# Load env and initialize Firebase app once
load_dotenv()
if not firebase_admin._apps:
    cred = credentials.Certificate("gcloud-key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

def store_to_firestore(user_id: str, pet_id: str, transcript: str, summary: str):
    data = {
        "user_id": user_id,
        "pet_id": pet_id,
        "timestamp": datetime.utcnow().isoformat(),
        "transcript": transcript,
        "summary": summary
    }

    doc_ref = db.collection("users") \
                .document(user_id) \
                .collection("pets") \
                .document(pet_id) \
                .collection("voice-notes") \
                .document()

    doc_ref.set(data)

    print(f"Stored voice note for user {user_id}, pet {pet_id}")

