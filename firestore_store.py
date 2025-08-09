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
    firebase_admin.initialize_app(cred, {"storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET")})

db = firestore.client()

# Store voice transcript + summary
def store_to_firestore(user_id, pet_id, transcript, summary):
    db.collection("pets").document(pet_id).collection("voice-notes").add(
        {"transcript": transcript, "summary": summary, "timestamp": datetime.utcnow().isoformat()}
    )

# Store PDF summary
def store_pdf_summary(user_id, pet_id, summary, timestamp, file_name, file_url):
    db.collection("pets").document(pet_id).collection("records").add(
        {"summary": summary, "file_name": file_name, "file_url": file_url, "timestamp": timestamp}
    )

# Get pets linked to a user
def get_pets_by_user_id(user_id):
    user_doc = db.collection("users").document(user_id).get()
    if not user_doc.exists:
        return []
    pet_ids = user_doc.to_dict().get("pets", [])
    return [{"id": pid, **db.collection("pets").document(pid).get().to_dict()} for pid in pet_ids]

# Get individual pet by ID
def get_pet_by_id(pet_id):
    """Get individual pet data by pet ID"""
    try:
        pet_doc = db.collection("pets").document(pet_id).get()
        if pet_doc.exists:
            return {"id": pet_id, **pet_doc.to_dict()}
        return None
    except Exception as e:
        print(f"Error getting pet by ID: {e}")
        return None
        

# Add a pet and sync it across user and page, with authorizedUsers and markdown
def add_pet_to_page_and_user(user_id, pet_data, page_id):
    pet_name = pet_data.get("name", "")
    pet_id = pet_name.lower().replace(" ", "_").replace(".", "").replace(",", "")
    
    # Create timestamp for breed_last_updated
    from datetime import datetime
    current_time = datetime.utcnow().isoformat()
    
    # Create enhanced pet document
    pet_document = {
        "name": pet_name,
        "animal_type": pet_data.get("animal_type", ""),
        "breed": pet_data.get("breed", ""),
        "breed_last_updated": current_time,
        "created_at": current_time,
    }
    
    # Add optional fields if provided
    if pet_data.get("age") is not None:
        pet_document["age"] = pet_data["age"]
    if pet_data.get("weight") is not None:
        pet_document["weight"] = pet_data["weight"]
    if pet_data.get("gender"):
        pet_document["gender"] = pet_data["gender"]

    # Create or update pet
    db.collection("pets").document(pet_id).set(pet_document)

    # Link pet to user and page
    db.collection("users").document(user_id).set(
        {"pets": firestore.ArrayUnion([pet_id]), "pages": firestore.ArrayUnion([page_id])}, merge=True
    )

    db.collection("pages").document(page_id).set(
        {
            "pets": firestore.ArrayUnion([pet_id]),
            "authorizedUsers": firestore.ArrayUnion([user_id]),
            "markdown": "",  # initialized only if not set yet
        },
        merge=True,
    )

    return {"id": pet_id, "name": pet_name, **pet_document}

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
    db.collection("pages").document(page_id).set({"authorizedUsers": firestore.ArrayUnion([uid])}, merge=True)

    # Add page to user
    db.collection("users").document(uid).set({"pages": firestore.ArrayUnion([page_id])}, merge=True)

    return {"status": "success", "userId": uid}

# (Optional) Create blank user entry when invited
def create_user_entry(uid, email):
    db.collection("users").document(uid).set({"email": email, "pets": [], "pages": []})

# Analytics helper functions
def get_analytics_summary(pet_id, days=30):
    """Get analytics summary for a pet"""
    from collections import defaultdict
    from datetime import timedelta
    
    cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    results = db.collection("pets").document(pet_id).collection("analytics").where("timestamp", ">=", cutoff_date).stream()
    
    summary = defaultdict(lambda: {"total": 0, "this_week": 0, "recent_entries": []})
    
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

# Store voice/text daily activities in analytics collection for dashboard visibility
def store_analytics_from_voice(pet_id, transcript, summary, classification):
    """Store daily activity data from voice/text input into analytics collection"""
    try:
        # Map activity keywords to analytics categories
        keywords = classification.get('keywords', [])
        content_type = classification.get('classification', 'DAILY_ACTIVITY')
        confidence = classification.get('confidence', 0.8)
        
        # Determine the most appropriate category based on keywords
        category_mapping = {
            'diet': ['food', 'eat', 'meal', 'breakfast', 'lunch', 'dinner', 'treat', 'feeding'],
            'exercise': ['walk', 'run', 'play', 'fetch', 'exercise', 'activity', 'training', 'park'],
            'sleep': ['sleep', 'nap', 'rest', 'tired', 'sleepy', 'bed'],
            'mood': ['happy', 'excited', 'calm', 'anxious', 'playful', 'mood', 'behavior'],
            'energy_levels': ['energy', 'active', 'lazy', 'lethargic', 'energetic', 'vigorous'],
            'grooming': ['bath', 'brush', 'groom', 'clean', 'nail', 'trim'],
            'bowel_movements': ['poop', 'bathroom', 'potty', 'bowel', 'outdoor'],
            'social': ['social', 'friend', 'dog', 'cat', 'people', 'visitor'],
        }
        
        # Find best matching category
        best_category = 'daily_activity'  # default
        max_matches = 0
        
        for category, category_keywords in category_mapping.items():
            matches = sum(1 for keyword in keywords if any(ck in keyword.lower() for ck in category_keywords))
            if matches > max_matches:
                max_matches = matches
                best_category = category
        
        # Create analytics entry
        analytics_entry = {
            "category": best_category,
            "source": "voice_input",
            "transcript": transcript,
            "summary": summary,
            "classification_confidence": confidence,
            "keywords": keywords,
            "content_type": content_type,
            "timestamp": datetime.utcnow().isoformat(),
            "notes": f"Daily activity recorded via voice/text: {summary[:100]}...",
        }
        
        # Store in analytics collection
        db.collection("pets").document(pet_id).collection("analytics").add(analytics_entry)
        print(f"✅ Stored daily activity as '{best_category}' in analytics collection")
        
    except Exception as e:
        print(f"❌ Error storing voice analytics: {e}")
