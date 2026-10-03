# firestore_store.py

# Persistence now goes through the demo ``Store`` (petpulse.store), not Firebase Admin.
# ``db`` is a Firestore-shaped facade that resolves the configured store on every call,
# so nothing is initialised at import time and no credentials are needed.
from datetime import datetime

from petpulse.deps import get_store, legacy_db
from petpulse.pets import create_pet, get_pet, list_pets

db = legacy_db()


# Store voice transcript + summary
def store_to_firestore(user_id, pet_id, transcript, summary):
    db.collection("pets").document(pet_id).collection("voice-notes").add(
        {"transcript": transcript, "summary": summary, "timestamp": datetime.utcnow().isoformat()}
    )


# Store PDF summary
def store_pdf_summary(user_id, pet_id, summary, timestamp, file_name, file_url, blob_key=None):
    db.collection("pets").document(pet_id).collection("records").add(
        {"summary": summary, "file_name": file_name, "file_url": file_url, "blob_key": blob_key, "timestamp": timestamp}
    )


# Get pets owned by a user (ownership lives on the pet: ``owners`` contains the uid).
def get_pets_by_user_id(user_id):
    return list_pets(get_store(), user_id)


# Get individual pet by ID
def get_pet_by_id(pet_id):
    """Get individual pet data by pet ID"""
    return get_pet(get_store(), pet_id)


# Create a pet owned by ``user_id`` under a server-generated uuid4 id (review C2). The shared
# "page" concept is gone; ``page_id`` is accepted for old callers and ignored.
def add_pet_to_page_and_user(user_id, pet_data, page_id=None):
    return create_pet(get_store(), user_id, pet_data)


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
        print(f"Stored daily activity as '{best_category}' in analytics collection")

    except Exception as e:
        print(f"Error storing voice analytics: {e}")
