import firebase_admin
from firebase_admin import credentials, firestore

try:
    # Load service account
    cred = credentials.Certificate("gcloud-key.json")
    firebase_admin.initialize_app(cred)

    # Get Firestore client
    db = firestore.client()

    # Try writing to a test collection
    doc_ref = db.collection("test-write").document("check")
    doc_ref.set({"status": "working!"})

    print("✅ Firestore write succeeded.")

except Exception as e:
    print(f"❌ Firestore write failed: {e}")
