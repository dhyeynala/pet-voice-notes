#api_server.py

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from main import main as run_main
from firestore_store import (
    store_to_firestore,
    get_pets_for_user,
    add_pet_for_user,
    store_pdf_summary,
)
from pdf_parser import extract_text_and_summarize
from firebase_admin import storage
import uuid

app = FastAPI()

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Transcribe + Summarize (Voice)
@app.post("/api/start")
async def start(request: Request):
    data = await request.json()
    user_id = data["uid"]
    pet_id = data["pet"]
    print(" Received POST:", data)
    response = run_main(user_id, pet_id)
    return response

# Upload PDF + Summarize
@app.post("/api/upload_pdf")
async def upload_pdf(uid: str, pet: str, file: UploadFile = File(...)):
    contents = await file.read()
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, "wb") as f:
        f.write(contents)

    # Upload to Firebase Storage
    bucket = storage.bucket()
    blob = bucket.blob(f"{uid}/{pet}/records/{uuid.uuid4()}_{file.filename}")
    blob.upload_from_filename(temp_path)
    blob.make_public()
    file_url = blob.public_url

    # Extract + summarize using Gemini
    result = extract_text_and_summarize(temp_path, uid, pet, file.filename, file_url)

    return {"message": "PDF processed", "summary": result["summary"], "url": file_url}

# Pets API
@app.get("/api/pets/{user_id}")
async def get_pets(user_id: str):
    return get_pets_for_user(user_id)

@app.post("/api/pets/{user_id}")
async def create_pet(user_id: str, request: Request):
    data = await request.json()
    pet_name = data["name"]
    return add_pet_for_user(user_id, pet_name)

# Static HTML
app.mount("/", StaticFiles(directory="public", html=True), name="static")

