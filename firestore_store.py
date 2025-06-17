# firestore_store.py

import firebase_admin
from firebase_admin import credentials, firestore, storage
from dotenv import load_dotenv
from datetime import datetime
import uuid
import os

load_dotenv()
if not firebase_admin._apps:
    cred = credentials.Certificate("gcloud-key.json")
    firebase_admin.initialize_app(cred, {
        "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET")
    })

db = firestore.client()

def store_to_firestore(user_id, pet_id, transcript, summary):
    db.collection("pets").document(pet_id).collection("voice-notes").add({
        "transcript": transcript,
        "summary": summary,
        "timestamp": datetime.utcnow().isoformat()
    })

def store_pdf_summary(user_id, pet_id, summary, timestamp, file_name, file_url):
    db.collection("pets").document(pet_id).collection("records").add({
        "summary": summary,
        "file_name": file_name,
        "file_url": file_url,
        "timestamp": timestamp
    })

def get_pets_by_user_id(user_id):
    user_doc = db.collection("users").document(user_id).get()
    if not user_doc.exists:
        return []
    pet_ids = user_doc.to_dict().get("pets", [])
    return [
        {"id": pid, **db.collection("pets").document(pid).get().to_dict()}
        for pid in pet_ids
    ]

def add_pet_to_page_and_user(user_id, pet_name, page_id):
    pet_id = pet_name.lower().replace(" ", "_")
    pet_ref = db.collection("pets").document(pet_id)
    pet_ref.set({ "name": pet_name })

    db.collection("users").document(user_id).set({
        "pets": firestore.ArrayUnion([pet_id])
    }, merge=True)

    db.collection("pages").document(page_id).set({
        "pets": firestore.ArrayUnion([pet_id])
    }, merge=True)
    return { "id": pet_id, "name": pet_name }

def handle_user_invite(data):
    email = data["email"]
    page_id = data["pageId"]

    user_query = db.collection("users").where("email", "==", email).limit(1).stream()
    user_doc = next(user_query, None)

    if user_doc:
        uid = user_doc.id
    else:
        uid = str(uuid.uuid4())
        create_user_entry(uid, email)

    db.collection("pages").document(page_id).set({
        "authorizedUsers": firestore.ArrayUnion([uid])
    }, merge=True)

    db.collection("users").document(uid).set({
        "pages": firestore.ArrayUnion([page_id])
    }, merge=True)

    return {"status": "success", "userId": uid}

