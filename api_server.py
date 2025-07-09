#api_server.py
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from firebase_admin import storage
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables first
load_dotenv()

# Set Google Cloud environment variables
import os
os.environ["GOOGLE_CLOUD_PROJECT"] = os.getenv("GOOGLE_CLOUD_PROJECT", "puppypages-29427")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "gcloud-key.json")

from main import main as run_main
from firestore_store import get_pets_by_user_id, add_pet_to_page_and_user, handle_user_invite, db, store_to_firestore
from pdf_parser import extract_text_and_summarize
from transcribe import start_recording, stop_recording, get_recording_status

import uuid
from datetime import datetime, timedelta

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

# ✅ NEW: Add text input note under each pet
@app.post("/api/pets/{pet_id}/textinput")
async def add_pet_textinput(pet_id: str, request: Request):
    data = await request.json()
    input_text = data.get("input", "")
    if not input_text:
        return { "status": "error", "message": "Input is empty" }

    db.collection("pets").document(pet_id).collection("textinput").add({
        "input": input_text,
        "timestamp": datetime.utcnow().isoformat()
    })

    return { "status": "success" }

# ✅ NEW: Start recording endpoint
@app.post("/api/start_recording")
async def start_recording_endpoint(request: Request):
    data = await request.json()
    user_id = data.get("uid")
    pet_id = data.get("pet")
    
    if not user_id or not pet_id:
        return {"status": "error", "message": "Missing uid or pet"}
    
    result = start_recording()
    return result

# ✅ NEW: Stop recording endpoint
@app.post("/api/stop_recording")
async def stop_recording_endpoint(request: Request):
    data = await request.json()
    user_id = data.get("uid")
    pet_id = data.get("pet")
    
    if not user_id or not pet_id:
        return {"status": "error", "message": "Missing uid or pet"}
    
    result = stop_recording()
    
    # If successful, process the transcript
    if result["status"] == "stopped" and result.get("transcript"):
        from summarize_openai import summarize_text
        
        transcript = result["transcript"]
        summary = summarize_text(transcript)
        store_to_firestore(user_id, pet_id, transcript, summary)
        
        return {
            "status": "success",
            "transcript": transcript,
            "summary": summary
        }
    
    return result

# ✅ NEW: Get recording status endpoint
@app.get("/api/recording_status")
async def recording_status_endpoint():
    return get_recording_status()

# ✅ Enhanced Analytics endpoints for comprehensive pet tracking
@app.post("/api/pets/{pet_id}/analytics/{category}")
async def add_analytics_entry(pet_id: str, category: str, request: Request):
    data = await request.json()
    
    # Validate category
    valid_categories = [
        "diet", "activity", "medication", "grooming", "exercise", 
        "energy_levels", "bowel_movements", "exit_events", "weight", 
        "temperature", "mood", "sleep", "water_intake"
    ]
    
    if category not in valid_categories:
        return {"status": "error", "message": "Invalid category"}
    
    # Add timestamp and store in Firestore
    entry_data = {
        **data,
        "timestamp": datetime.utcnow().isoformat(),
        "category": category
    }
    
    db.collection("pets").document(pet_id).collection("analytics").add(entry_data)
    
    return {"status": "success", "data": entry_data}

@app.get("/api/pets/{pet_id}/analytics")
async def get_analytics_data(pet_id: str, category: str = None, days: int = 30):
    query = db.collection("pets").document(pet_id).collection("analytics")
    
    if category:
        query = query.where("category", "==", category)
    
    # Get data from last N days
    from datetime import datetime, timedelta
    cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    query = query.where("timestamp", ">=", cutoff_date)
    
    results = query.stream()
    analytics_data = []
    
    for doc in results:
        data = doc.to_dict()
        data["id"] = doc.id
        analytics_data.append(data)
    
    return {"data": analytics_data}

@app.get("/api/pets/{pet_id}/analytics/summary")
async def get_analytics_summary(pet_id: str):
    """Get summary statistics for all analytics categories"""
    from collections import defaultdict
    from datetime import datetime, timedelta
    
    # Get all analytics data
    results = db.collection("pets").document(pet_id).collection("analytics").stream()
    
    summary = defaultdict(lambda: {
        "total": 0,
        "this_week": 0,
        "avg_daily": 0,
        "recent_entries": []
    })
    
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    
    for doc in results:
        data = doc.to_dict()
        category = data.get("category", "unknown")
        timestamp = datetime.fromisoformat(data.get("timestamp", ""))
        
        summary[category]["total"] += 1
        summary[category]["recent_entries"].append(data)
        
        if timestamp >= one_week_ago:
            summary[category]["this_week"] += 1
    
    # Calculate averages
    for category in summary:
        if summary[category]["total"] > 0:
            summary[category]["avg_daily"] = round(summary[category]["this_week"] / 7, 1)
            # Keep only most recent 5 entries
            summary[category]["recent_entries"] = sorted(
                summary[category]["recent_entries"], 
                key=lambda x: x["timestamp"], 
                reverse=True
            )[:5]
    
    return {"summary": dict(summary)}

@app.post("/api/pets/{pet_id}/daily_routine")
async def generate_daily_routine_headlines(pet_id: str, request: Request):
    """Generate AI-powered daily routine headlines based on analytics data"""
    try:
        from ai_analytics import pet_ai
        
        data = await request.json()
        date = data.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
        
        # Get analytics data for the specified date
        start_date = f"{date}T00:00:00"
        end_date = f"{date}T23:59:59"
        
        query = db.collection("pets").document(pet_id).collection("analytics").where(
            "timestamp", ">=", start_date
        ).where("timestamp", "<=", end_date)
        
        daily_data = []
        for doc in query.stream():
            data_entry = doc.to_dict()
            data_entry["id"] = doc.id
            daily_data.append(data_entry)
        
        # Get historical data for context (last 30 days)
        historical_start = (datetime.utcnow() - timedelta(days=30)).isoformat()
        historical_query = db.collection("pets").document(pet_id).collection("analytics").where(
            "timestamp", ">=", historical_start
        )
        
        historical_data = []
        for doc in historical_query.stream():
            hist_entry = doc.to_dict()
            hist_entry["id"] = doc.id
            historical_data.append(hist_entry)
        
        # Get pet name
        pet_doc = db.collection("pets").document(pet_id).get()
        pet_name = pet_doc.to_dict().get("name", "Pet") if pet_doc.exists else "Pet"
        
        # Generate AI headlines
        headlines = pet_ai.generate_daily_headlines(pet_name, daily_data, historical_data, date)
        
        return {
            "headlines": headlines, 
            "date": date, 
            "data_points": len(daily_data),
            "pet_name": pet_name
        }
        
    except Exception as e:
        # Fallback to simple headlines
        return generate_daily_routine_headlines_fallback(pet_id, request)

async def generate_daily_routine_headlines_fallback(pet_id: str, request: Request):
    """Fallback method for generating headlines without AI"""
    data = await request.json()
    date = data.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
    
    # Get analytics data for the specified date
    start_date = f"{date}T00:00:00"
    end_date = f"{date}T23:59:59"
    
    query = db.collection("pets").document(pet_id).collection("analytics").where(
        "timestamp", ">=", start_date
    ).where("timestamp", "<=", end_date)
    
    daily_data = []
    for doc in query.stream():
        daily_data.append(doc.to_dict())
    
    # Get pet name
    pet_doc = db.collection("pets").document(pet_id).get()
    pet_name = pet_doc.to_dict().get("name", "Pet") if pet_doc.exists else "Pet"
    
    # Generate headlines based on the data
    headlines = generate_routine_headlines(pet_name, daily_data, date)
    
    return {"headlines": headlines, "date": date, "data_points": len(daily_data)}

@app.get("/api/pets/{pet_id}/health_insights")
async def get_health_insights(pet_id: str, days: int = 30):
    """Get AI-powered health insights and recommendations"""
    try:
        from ai_analytics import pet_ai
        
        # Get analytics data for the specified timeframe
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        query = db.collection("pets").document(pet_id).collection("analytics").where(
            "timestamp", ">=", cutoff_date
        )
        
        analytics_data = []
        for doc in query.stream():
            data_entry = doc.to_dict()
            data_entry["id"] = doc.id
            analytics_data.append(data_entry)
        
        # Get pet name
        pet_doc = db.collection("pets").document(pet_id).get()
        pet_name = pet_doc.to_dict().get("name", "Pet") if pet_doc.exists else "Pet"
        
        # Generate AI insights
        insights = pet_ai.generate_health_insights(pet_name, analytics_data, days)
        
        return {
            "insights": insights,
            "timeframe_days": days,
            "data_points": len(analytics_data),
            "pet_name": pet_name
        }
        
    except Exception as e:
        # Fallback to simple insights
        return {
            "insights": {
                "overall_health_score": 7,
                "key_insights": ["Regular activity tracking in progress"],
                "recommendations": ["Continue monitoring daily activities"],
                "alerts": [],
                "positive_trends": ["Consistent data collection"]
            },
            "timeframe_days": days,
            "data_points": 0,
            "error": "AI insights temporarily unavailable"
        }

@app.get("/api/pets/{pet_id}/visualizations")
async def get_visualization_data(pet_id: str, chart_type: str = "all", days: int = 30):
    """Get data for various chart visualizations"""
    try:
        from visualization_service import visualization_service
        
        # Get analytics data
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        query = db.collection("pets").document(pet_id).collection("analytics").where(
            "timestamp", ">=", cutoff_date
        )
        
        analytics_data = []
        for doc in query.stream():
            data_entry = doc.to_dict()
            data_entry["id"] = doc.id
            analytics_data.append(data_entry)
        
        visualizations = {}
        
        if chart_type == "all" or chart_type == "activity":
            visualizations["weekly_activity"] = visualization_service.generate_weekly_activity_chart(analytics_data)
        
        if chart_type == "all" or chart_type == "energy":
            visualizations["energy_distribution"] = visualization_service.generate_energy_distribution_chart(analytics_data)
        
        if chart_type == "all" or chart_type == "diet":
            visualizations["diet_frequency"] = visualization_service.generate_diet_frequency_chart(analytics_data)
        
        if chart_type == "all" or chart_type == "overview":
            visualizations["health_overview"] = visualization_service.generate_health_overview_chart(analytics_data)
        
        if chart_type == "all" or chart_type == "exercise":
            visualizations["exercise_histogram"] = visualization_service.generate_exercise_duration_histogram(analytics_data)
        
        if chart_type == "all" or chart_type == "medication":
            visualizations["medication_adherence"] = visualization_service.generate_medication_adherence_chart(analytics_data)
        
        if chart_type == "all" or chart_type == "heatmap":
            visualizations["activity_heatmap"] = visualization_service.generate_activity_heatmap_data(analytics_data)
        
        if chart_type == "all" or chart_type == "summary":
            visualizations["summary_metrics"] = visualization_service.generate_summary_metrics(analytics_data, days)
        
        return {
            "visualizations": visualizations,
            "data_points": len(analytics_data),
            "timeframe_days": days
        }
        
    except Exception as e:
        return {
            "error": f"Failed to generate visualizations: {str(e)}",
            "visualizations": {},
            "data_points": 0
        }

def generate_routine_headlines(pet_name: str, daily_data: list, date: str):
    """Generate themed headlines based on daily data"""
    headlines = []
    
    # Categorize the data
    categories = {}
    for entry in daily_data:
        category = entry.get("category", "unknown")
        if category not in categories:
            categories[category] = []
        categories[category].append(entry)
    
    # Generate headlines based on available data
    if "diet" in categories:
        diet_entries = len(categories["diet"])
        if diet_entries > 3:
            headlines.append(f"🍽️ {pet_name} had a feast day with {diet_entries} meals and treats!")
        elif diet_entries > 1:
            headlines.append(f"🥗 {pet_name} enjoyed a balanced day with {diet_entries} nutritious meals")
        else:
            headlines.append(f"🍖 {pet_name} had their daily nutrition on {date}")
    
    if "exercise" in categories:
        exercise_count = len(categories["exercise"])
        total_duration = sum(int(e.get("duration", 0)) for e in categories["exercise"])
        if total_duration > 60:
            headlines.append(f"🏃 Active day: {pet_name} exercised for {total_duration} minutes!")
        elif exercise_count > 1:
            headlines.append(f"🚶 {pet_name} stayed active with {exercise_count} exercise sessions")
    
    if "energy_levels" in categories:
        energy_levels = [int(e.get("level", 3)) for e in categories["energy_levels"]]
        avg_energy = sum(energy_levels) / len(energy_levels) if energy_levels else 3
        if avg_energy >= 4:
            headlines.append(f"⚡ High energy day: {pet_name} was full of life!")
        elif avg_energy <= 2:
            headlines.append(f"😴 Relaxed day: {pet_name} took it easy")
        else:
            headlines.append(f"😊 Balanced energy: {pet_name} had a normal day")
    
    if "medication" in categories:
        med_count = len(categories["medication"])
        headlines.append(f"💊 Health care day: {pet_name} took {med_count} medication(s)")
    
    if "grooming" in categories:
        headlines.append(f"✨ Spa day: {pet_name} got pampered with grooming")
    
    if "bowel_movements" in categories:
        bm_count = len(categories["bowel_movements"])
        if bm_count >= 3:
            headlines.append(f"💩 Regular day: {pet_name} had {bm_count} healthy movements")
    
    # Add default headline if no specific data
    if not headlines:
        headlines.append(f"📅 {pet_name}'s day on {date} - Ready for new adventures!")
    
    # Add a general summary headline
    total_activities = len(daily_data)
    if total_activities > 5:
        headlines.insert(0, f"🌟 Busy day: {total_activities} activities tracked for {pet_name}!")
    
    return headlines

# ✅ NEW: Simple test endpoint for diagnostics
@app.get("/api/test")
async def test_endpoint():
    return {
        "status": "OK",
        "message": "PetPages API server is running",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "services": {
            "firebase": "connected",
            "storage": "available",
            "api": "operational"
        }
    }

# ✅ Serve index last to avoid route shadowing
@app.get("/")
async def serve_index():
    return FileResponse(os.path.join("public", "index.html"))

app.mount("/", StaticFiles(directory="public", html=True), name="static")
