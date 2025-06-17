#api_server.py
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from main import main as run_main
from firestore_store import *
from pdf_parser import extract_text_and_summarize
from firebase_admin import storage

import os
import uuid


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/start")
async def start(request: Request):
    data = await request.json()
    return run_main(data["uid"], data["pet"])

@app.post("/api/upload_pdf")
async def upload_pdf(uid: str, pet: str, file: UploadFile = File(...)):
    contents = await file.read()
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, "wb") as f:
        f.write(contents)

    blob = storage.bucket().blob(f"{uid}/{pet}/records/{uuid.uuid4()}_{file.filename}")
    blob.upload_from_filename(temp_path)
    blob.make_public()

    result = extract_text_and_summarize(temp_path, uid, pet, file.filename, blob.public_url)
    return {"message": "PDF processed", "summary": result["summary"], "url": blob.public_url}

@app.get("/api/user-pets/{user_id}")
async def get_user_pets(user_id: str):
    return get_pets_by_user_id(user_id)

@app.post("/api/pets/{user_id}")
async def create_pet(user_id: str, request: Request):
    data = await request.json()
    return add_pet_to_page_and_user(user_id, data["name"], data.get("pageId", "default-page"))

@app.post("/api/pages/invite")
async def invite_user(request: Request):
    data = await request.json()
    return handle_user_invite(data)

@app.get("/api/pages/{page_id}")
async def get_page(page_id: str):
    doc = db.collection("pages").document(page_id).get()
    return doc.to_dict() or {}

@app.post("/api/pages/{page_id}")
async def update_page(page_id: str, request: Request):
    data = await request.json()
    db.collection("pages").document(page_id).update({
        "markdown": data.get("markdown", "")
    })
    return {"status": "updated"}

@app.get("/api/markdown")
async def get_markdown(page: str, pet: str):
    page_doc = db.collection("pages").document(page).get()
    pet_doc = db.collection("pets").document(pet).get()

    pet_data = pet_doc.to_dict() or {}
    page_data = page_doc.to_dict() or {}

    return {
        "markdown": pet_data.get("markdown") or page_data.get("markdown", "")
    }

@app.post("/api/markdown")
async def update_markdown(request: Request):
    data = await request.json()
    page = data["page"]
    pet = data["pet"]
    markdown = data.get("markdown", "")

    db.collection("pets").document(pet).set({ "markdown": markdown }, merge=True)
    db.collection("pages").document(page).set({ "markdown": markdown }, merge=True)
    return { "status": "updated" }

# ✅ Move this to the bottom so it doesn’t block routes above
@app.get("/")
async def serve_index():
    return FileResponse(os.path.join("public", "index.html"))

app.mount("/", StaticFiles(directory="public", html=True), name="static")

