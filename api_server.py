from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from main import main as run_main

app = FastAPI()

# Optional: allow frontend to talk to backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # use specific origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ POST endpoint to trigger speech → summary → Firestore
@app.post("/api/start")
async def start(request: Request):
    data = await request.json()
    user_id = data["uid"]
    pet_id = data["pet"]

    print("📥 Received POST:", data)  # 👈 Add this for debug visibility

    run_main(user_id, pet_id)
    return {"message": "Data stored successfully"}
