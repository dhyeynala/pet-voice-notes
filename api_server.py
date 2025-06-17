#api_server.py

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from main import main as run_main
from firestore_store import *
from firebase_admin import storage
import uuid
from fastapi.responses import FileResponse
import os

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

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join("public", "index.html"))

app.mount("/", StaticFiles(directory="public", html=True), name="static")

