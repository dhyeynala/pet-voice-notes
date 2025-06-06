#api_server.py

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from main import main as run_main
from firestore_store import store_to_firestore, get_pets_for_user, add_pet_for_user

app = FastAPI()

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ POST endpoint: Transcribe + Summarize
@app.post("/api/start")
async def start(request: Request):
    data = await request.json()
    user_id = data["uid"]
    pet_id = data["pet"]
    print(" Received POST:", data)
    response = run_main(user_id, pet_id)
    return response


@app.get("/api/pets/{user_id}")
async def get_pets(user_id: str):
    return get_pets_for_user(user_id)

@app.post("/api/pets/{user_id}")
async def create_pet(user_id: str, request: Request):
    data = await request.json()
    pet_name = data["name"]
    return add_pet_for_user(user_id, pet_name)

app.mount("/", StaticFiles(directory="public", html=True), name="static")
