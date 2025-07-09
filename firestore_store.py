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

# Store voice transcript + summary
def store_to_firestore(user_id, pet_id, transcript, summary):
    db.collection("pets").document(pet_id).collection("voice-notes").add({
        "transcript": transcript,
        "summary": summary,
        "timestamp": datetime.utcnow().isoformat()
    })

# Store PDF summary
def store_pdf_summary(user_id, pet_id, summary, timestamp, file_name, file_url):
    db.collection("pets").document(pet_id).collection("records").add({
        "summary": summary,
        "file_name": file_name,
        "file_url": file_url,
        "timestamp": timestamp
    })

# Get pets linked to a user
def get_pets_by_user_id(user_id):
    user_doc = db.collection("users").document(user_id).get()
    if not user_doc.exists:
        return []
    pet_ids = user_doc.to_dict().get("pets", [])
    return [
        {"id": pid, **db.collection("pets").document(pid).get().to_dict()}
        for pid in pet_ids
    ]

# Add a pet and sync it across user and page, with authorizedUsers and markdown
def add_pet_to_page_and_user(user_id, pet_name, page_id):
    pet_id = pet_name.lower().replace(" ", "_")

    # Create or update pet
    db.collection("pets").document(pet_id).set({ "name": pet_name })

    # Link pet to user and page
    db.collection("users").document(user_id).set({
        "pets": firestore.ArrayUnion([pet_id]),
        "pages": firestore.ArrayUnion([page_id])
    }, merge=True)

    db.collection("pages").document(page_id).set({
        "pets": firestore.ArrayUnion([pet_id]),
        "authorizedUsers": firestore.ArrayUnion([user_id]),
        "markdown": ""  # initialized only if not set yet
    }, merge=True)

    return { "id": pet_id, "name": pet_name }

# Invite user by email and link to page
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

    # Add user to page
    db.collection("pages").document(page_id).set({
        "authorizedUsers": firestore.ArrayUnion([uid])
    }, merge=True)

    # Add page to user
    db.collection("users").document(uid).set({
        "pages": firestore.ArrayUnion([page_id])
    }, merge=True)

    return {"status": "success", "userId": uid}

# (Optional) Create blank user entry when invited
def create_user_entry(uid, email):
    db.collection("users").document(uid).set({
        "email": email,
        "pets": [],
        "pages": []
    })

# Analytics helper functions
def get_analytics_summary(pet_id, days=30):
    """Get analytics summary for a pet"""
    from collections import defaultdict
    from datetime import timedelta
    
    cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    results = db.collection("pets").document(pet_id).collection("analytics").where(
        "timestamp", ">=", cutoff_date
    ).stream()
    
    summary = defaultdict(lambda: {
        "total": 0,
        "this_week": 0,
        "recent_entries": []
    })
    
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    
    for doc in results:
        data = doc.to_dict()
        category = data.get("category", "unknown")
        timestamp = datetime.fromisoformat(data.get("timestamp", ""))
        
        summary[category]["total"] += 1
        summary[category]["recent_entries"].append(data)
        
        if timestamp >= one_week_ago:
            summary[category]["this_week"] += 1
    
    return dict(summary)
