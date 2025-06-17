#auth.py

import firebase_admin
from firebase_admin import auth, credentials, firestore

cred = credentials.Certificate("gcloud-key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

def create_user_entry(uid, email):
    db.collection("users").document(uid).set({
        "email": email,
        "pages": [],
        "pets": []
    })

