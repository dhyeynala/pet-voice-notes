#auth.py

import firebase_admin
from firebase_admin import auth, credentials, firestore
import os

# Initialize Firebase Admin
cred = credentials.Certificate("gcloud-key.json")
firebase_admin.initialize_app(cred)

db = firestore.client()

def sign_up(email, password, pet_name):
    user = auth.create_user(email=email, password=password)
    print("✅ User created:", user.uid)

    # Create initial pet document
    db.collection("users").document(user.uid).set({
        "email": email,
        "pet": pet_name
    })
    return user.uid

def sign_in(email, password):
    # Firebase Admin does not support client-side login.
    raise NotImplementedError("Use Firebase client SDK (JS) for login in UI.")
