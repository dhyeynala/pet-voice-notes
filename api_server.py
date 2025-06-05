from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from main import main as run_main

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

    return {"message": "Data stored successfully"}

# ✅ Mount static frontend AFTER defining routes
app.mount("/", StaticFiles(directory="public", html=True), name="static")
