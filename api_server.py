from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from main import main as run_main

app = FastAPI()

# Optional: allow local frontend to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or set specific domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/start")
async def start(request: Request):
    data = await request.json()
    user_id = data["uid"]
    pet_id = data["pet"]
    
    run_main(user_id, pet_id)
    return {"message": "Data stored successfully"}
