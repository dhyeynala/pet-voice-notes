# firestore_store.py

import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime

# Load .env and initialize Firebase once
load_dotenv()
if not firebase_admin._apps:
    cred = credentials.Certificate("gcloud-key.json")
    firebase_admin.initialize_app(cred, {
        "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET") 
    })

db = firestore.client()

# Voice Note Storage
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

# PDF Summary Storage
def store_pdf_summary(user_id, pet_id, summary, timestamp, file_name, file_url):
    doc_ref = db.collection("users").document(user_id) \
        .collection("pets").document(pet_id) \
        .collection("records").document()

    doc_ref.set({
        "source": "pdf_upload",
        "file_name": file_name,
        "file_url": file_url,
        "summary": summary,
        "timestamp": timestamp
    })

# Pets Handling
def get_pets_for_user(user_id):
    pets_ref = db.collection("users").document(user_id).collection("pets")
    docs = pets_ref.stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]

def add_pet_for_user(user_id, pet_name):
    pet_id = pet_name.lower().replace(" ", "_")
    pet_doc = db.collection("users").document(user_id).collection("pets").document(pet_id)
    pet_doc.set({"name": pet_name})
    return {"id": pet_id, "name": pet_name}
