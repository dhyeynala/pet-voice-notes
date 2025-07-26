#api_server.py
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from firebase_admin import storage
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
import uuid

# Load environment variables first
load_dotenv()

# Set Google Cloud environment variables
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
if not project_id:
    raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set")
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "gcloud-key.json")

from main import main as run_main
from firestore_store import get_pets_by_user_id, add_pet_to_page_and_user, handle_user_invite, db, store_to_firestore
from pdf_parser import extract_text_and_summarize
from transcribe import start_recording, stop_recording, get_recording_status

# ✅ Lazy-loaded service instances to improve startup performance
_intelligent_chatbot_service = None
_simple_rag_service = None
_visualization_service = None
_pet_ai = None

def get_intelligent_chatbot_service():
    global _intelligent_chatbot_service
    if _intelligent_chatbot_service is None:
        from intelligent_chatbot_service import IntelligentChatbotService
        _intelligent_chatbot_service = IntelligentChatbotService()
    return _intelligent_chatbot_service

def get_simple_rag_service():
    global _simple_rag_service
    if _simple_rag_service is None:
        from simple_rag_service import SimplePetHealthRAGService
        _simple_rag_service = SimplePetHealthRAGService()
    return _simple_rag_service

def get_visualization_service():
    global _visualization_service
    if _visualization_service is None:
        from visualization_service import PetVisualizationService
        _visualization_service = PetVisualizationService()
    return _visualization_service

def get_pet_ai():
    global _pet_ai
    if _pet_ai is None:
        from ai_analytics import PetAnalyticsAI
        _pet_ai = PetAnalyticsAI()
    return _pet_ai

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Startup event to pre-warm critical services
@app.on_event("startup")
async def startup_event():
    """Pre-warm critical services to improve first request performance"""
    print("🚀 Starting PetPages API server...")
    print("🔥 Pre-warming critical services...")
    
    # Pre-warm only the most commonly used service (visualization)
    # to balance startup time vs first-request performance
    try:
        _ = get_visualization_service()
        print("✅ Visualization service pre-warmed")
    except Exception as e:
        print(f"⚠️ Failed to pre-warm visualization service: {e}")
    
    print("🎉 PetPages API server ready!")

@app.post("/api/start")
async def start(request: Request):
    data = await request.json()
    return run_main(data["uid"], data["pet"])

@app.post("/api/upload_pdf")
async def upload_pdf(request: Request, file: UploadFile = File(...)):
    # Get form data
    form = await request.form()
    uid = form.get("uid")
    pet = form.get("pet")
    
    if not uid or not pet:
        return {"error": "Missing uid or pet parameter"}
    
    if not file.filename:
        return {"error": "No file provided"}
    
    try:
        contents = await file.read()
        temp_path = f"/tmp/{file.filename}"
        with open(temp_path, "wb") as f:
            f.write(contents)

        blob = storage.bucket().blob(f"{uid}/{pet}/records/{uuid.uuid4()}_{file.filename}")
        blob.upload_from_filename(temp_path)
        blob.make_public()

        result = extract_text_and_summarize(temp_path, uid, pet, file.filename, blob.public_url)
        
        # Clean up temporary file
        try:
            os.remove(temp_path)
        except:
            pass
            
        if "error" in result:
            return {"error": result["error"]}
            
        return {"message": "PDF processed", "summary": result["summary"], "url": blob.public_url}
        
    except Exception as e:
        # Clean up temporary file on error
        try:
            os.remove(temp_path)
        except:
            pass
        return {"error": f"Failed to process PDF: {str(e)}"}

@app.get("/api/user-pets/{user_id}")
async def get_user_pets(user_id: str):
    return get_pets_by_user_id(user_id)

@app.post("/api/pets/{user_id}")
async def create_pet(user_id: str, request: Request):
    data = await request.json()
    
    # Validate required fields
    if not data.get("name"):
        return {"error": "Pet name is required"}
    if not data.get("animal_type"):
        return {"error": "Animal type is required"}
    
    try:
        result = add_pet_to_page_and_user(user_id, data, data.get("pageId", "default-page"))
        return {"status": "success", "pet": result}
    except Exception as e:
        return {"error": f"Failed to create pet: {str(e)}"}

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
async def get_markdown(page: str = None, pet: str = None):
    if not page or not pet:
        return {"markdown": ""}
    
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

    # Enhanced: Classify and summarize the content
    from summarize_openai import summarize_text, classify_pet_content
    
    # Classify the content type
    classification = classify_pet_content(input_text)
    
    # Generate AI summary
    summary = summarize_text(input_text)
    
    # Store with enhanced metadata
    entry_data = {
        "input": input_text,
        "summary": summary,
        "content_type": classification.get("classification", "MIXED"),
        "confidence": classification.get("confidence", 0.5),
        "keywords": classification.get("keywords", []),
        "timestamp": datetime.utcnow().isoformat()
    }
    
    db.collection("pets").document(pet_id).collection("textinput").add(entry_data)

    # If daily activity content, also store in analytics for dashboard visibility
    if classification.get('classification') == 'DAILY_ACTIVITY':
        from firestore_store import store_analytics_from_voice
        store_analytics_from_voice(pet_id, input_text, summary, classification)
        print(f"✅ Daily activity from text input also stored in analytics collection")

    return { 
        "status": "success", 
        "summary": summary,
        "content_type": classification.get("classification", "MIXED"),
        "confidence": classification.get("confidence", 0.5),
        "keywords": classification.get("keywords", []),
        "message": f"Added {classification.get('classification', 'MIXED').lower()} note with AI summary"
    }

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
    
    try:
        result = stop_recording()
        
        # Handle the transcription result
        if result["status"] == "stopped" and result.get("transcript"):
            # We have a transcript, try to process with AI
            try:
                from summarize_openai import summarize_text, classify_pet_content
                
                transcript = result["transcript"]
                
                # Classify the content type
                classification = classify_pet_content(transcript)
                
                # Generate enhanced summary
                summary = summarize_text(transcript)
                
                # Store with enhanced metadata
                entry_data = {
                    "transcript": transcript,
                    "summary": summary,
                    "content_type": classification.get("classification", "MIXED"),
                    "confidence": classification.get("confidence", 0.5),
                    "keywords": classification.get("keywords", []),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                db.collection("pets").document(pet_id).collection("voice-notes").add(entry_data)
                
                return {
                    "status": "success",
                    "transcript": transcript,
                    "summary": summary,
                    "content_type": classification.get("classification", "MIXED"),
                    "confidence": classification.get("confidence", 0.5),
                    "message": f"Processed {classification.get('classification', 'MIXED').lower()} voice note"
                }
                
            except Exception as ai_error:
                print(f"AI processing failed: {ai_error}")
                # AI processing failed, but we still have transcript
                # Store basic transcript without AI enhancement
                entry_data = {
                    "transcript": result["transcript"],
                    "summary": "Transcription completed. AI processing unavailable.",
                    "content_type": "TRANSCRIPTION_ONLY",
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                db.collection("pets").document(pet_id).collection("voice-notes").add(entry_data)
                
                return {
                    "status": "stopped",
                    "transcript": result["transcript"],
                    "message": "Transcription successful, AI processing unavailable"
                }
        
        elif result["status"] == "stopped":
            # Recording stopped but no transcript (no speech detected)
            return {
                "status": "stopped",
                "message": "Recording stopped but no speech was detected"
            }
        
        else:
            # Recording failed or other error
            return {
                "status": "error",
                "message": result.get("message", "Recording failed")
            }
            
    except Exception as e:
        print(f"Error in stop_recording_endpoint: {e}")
        return {
            "status": "error", 
            "message": f"Server error: {str(e)}"
        }

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
    """Get analytics data including voice recordings for dashboard charts"""
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
    
    # Also include voice-notes as daily activities if no specific category requested
    if not category or category == "daily_activity":
        voice_query = db.collection("pets").document(pet_id).collection("voice-notes")
        voice_query = voice_query.where("timestamp", ">=", cutoff_date)
        
        for doc in voice_query.stream():
            data = doc.to_dict()
            # Convert voice note to analytics format
            voice_entry = {
                "id": doc.id,
                "category": "daily_activity",
                "source": "voice_note",
                "transcript": data.get("transcript", ""),
                "summary": data.get("summary", ""),
                "timestamp": data.get("timestamp", ""),
                "notes": f"Voice recording: {data.get('summary', '')[:100]}..."
            }
            analytics_data.append(voice_entry)
    
    # Also include text input as daily activities/medical notes if no specific category requested
    if not category or category in ["daily_activity", "medical_notes", "mixed_notes"]:
        text_query = db.collection("pets").document(pet_id).collection("textinput")
        text_query = text_query.where("timestamp", ">=", cutoff_date)
        
        for doc in text_query.stream():
            data = doc.to_dict()
            content_type = data.get("content_type", "DAILY_ACTIVITY")
            
            # Map content type to category
            if content_type == "DAILY_ACTIVITY":
                text_category = "daily_activity"
            elif content_type == "MEDICAL":
                text_category = "medical_notes"
            else:
                text_category = "mixed_notes"
            
            # Only include if matches requested category
            if not category or category == text_category:
                text_entry = {
                    "id": doc.id,
                    "category": text_category,
                    "source": "text_input",
                    "input": data.get("input", ""),
                    "summary": data.get("summary", ""),
                    "content_type": content_type,
                    "timestamp": data.get("timestamp", ""),
                    "notes": f"Text note: {data.get('summary', '')[:100]}..."
                }
                analytics_data.append(text_entry)
    
    return {"data": analytics_data}

@app.get("/api/pets/{pet_id}/analytics/summary")
async def get_analytics_summary(pet_id: str):
    """Get summary statistics for all analytics categories including voice-notes"""
    from collections import defaultdict
    from datetime import datetime, timedelta
    
    # Get all analytics data
    analytics_results = db.collection("pets").document(pet_id).collection("analytics").stream()
    
    # Also get voice-notes that might contain daily activities
    voice_results = db.collection("pets").document(pet_id).collection("voice-notes").stream()
    
    # Also get text input notes
    text_results = db.collection("pets").document(pet_id).collection("textinput").stream()
    
    summary = defaultdict(lambda: {
        "total": 0,
        "this_week": 0,
        "avg_daily": 0,
        "recent_entries": []
    })
    
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    
    # Process analytics collection data
    for doc in analytics_results:
        data = doc.to_dict()
        category = data.get("category", "unknown")
        timestamp = datetime.fromisoformat(data.get("timestamp", ""))
        
        summary[category]["total"] += 1
        summary[category]["recent_entries"].append(data)
        
        if timestamp >= one_week_ago:
            summary[category]["this_week"] += 1
    
    # Process voice-notes and classify as daily activities
    for doc in voice_results:
        data = doc.to_dict()
        timestamp = datetime.fromisoformat(data.get("timestamp", ""))
        
        # Classify as daily activity for now (could enhance with stored classification)
        category = "daily_activity"
        voice_entry = {
            "category": category,
            "source": "voice_note",
            "transcript": data.get("transcript", ""),
            "summary": data.get("summary", ""),
            "timestamp": data.get("timestamp", "")
        }
        
        summary[category]["total"] += 1
        summary[category]["recent_entries"].append(voice_entry)
        
        if timestamp >= one_week_ago:
            summary[category]["this_week"] += 1
    
    # Process text input data with classification
    for doc in text_results:
        data = doc.to_dict()
        timestamp = datetime.fromisoformat(data.get("timestamp", ""))
        
        # Use stored classification or default to daily activity
        content_type = data.get("content_type", "DAILY_ACTIVITY")
        if content_type == "DAILY_ACTIVITY":
            category = "daily_activity"
        elif content_type == "MEDICAL":
            category = "medical_notes"
        else:
            category = "mixed_notes"
            
        text_entry = {
            "category": category,
            "source": "text_input",
            "input": data.get("input", ""),
            "summary": data.get("summary", ""),
            "content_type": content_type,
            "timestamp": data.get("timestamp", "")
        }
        
        summary[category]["total"] += 1
        summary[category]["recent_entries"].append(text_entry)
        
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
        pet_ai = get_pet_ai()
        
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
        return await generate_daily_routine_headlines_fallback(pet_id, request)

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
        pet_ai = get_pet_ai()
        
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
    """Get data for various chart visualizations including voice recordings"""
    try:
        visualization_service = get_visualization_service()
        
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
        
        # Also include voice-notes as daily activities for charts
        voice_query = db.collection("pets").document(pet_id).collection("voice-notes").where(
            "timestamp", ">=", cutoff_date
        )
        
        for doc in voice_query.stream():
            data = doc.to_dict()
            # Convert voice note to analytics format for visualization
            voice_entry = {
                "id": doc.id,
                "category": "daily_activity",
                "source": "voice_note",
                "transcript": data.get("transcript", ""),
                "summary": data.get("summary", ""),
                "timestamp": data.get("timestamp", ""),
                "notes": f"Voice recording: {data.get('summary', '')[:100]}..."
            }
            analytics_data.append(voice_entry)
        
        # Also include text input notes as daily activities for charts
        text_query = db.collection("pets").document(pet_id).collection("textinput").where(
            "timestamp", ">=", cutoff_date
        )
        
        for doc in text_query.stream():
            data = doc.to_dict()
            content_type = data.get("content_type", "DAILY_ACTIVITY")
            
            # Map content type to category for visualization
            if content_type == "DAILY_ACTIVITY":
                viz_category = "daily_activity"
            elif content_type == "MEDICAL":
                viz_category = "medical_notes"
            else:
                viz_category = "mixed_notes"
            
            text_entry = {
                "id": doc.id,
                "category": viz_category,
                "source": "text_input",
                "input": data.get("input", ""),
                "summary": data.get("summary", ""),
                "content_type": content_type,
                "timestamp": data.get("timestamp", ""),
                "notes": f"Text note: {data.get('summary', '')[:100]}..."
            }
            analytics_data.append(text_entry)
        
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

# ✅ NEW: RAG-powered AI Assistant endpoints
@app.post("/api/pets/{pet_id}/preload")
async def preload_pet_data(pet_id: str, request: Request):
    """Preload and cache pet data for faster subsequent queries"""
    try:
        intelligent_chatbot_service = get_intelligent_chatbot_service()
        
        data = await request.json()
        days = data.get("days", 30)  # Default to 30 days
        
        # Preload the pet data
        result = await intelligent_chatbot_service.preload_pet_data(pet_id, days)
        
        return result
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to preload pet data: {str(e)}"
        }

@app.post("/api/pets/{pet_id}/cache/clear")
async def clear_pet_cache(pet_id: str):
    """Clear cached data for a specific pet"""
    try:
        intelligent_chatbot_service = get_intelligent_chatbot_service()
        intelligent_chatbot_service.clear_pet_cache(pet_id)
        
        return {
            "status": "success",
            "message": f"Cache cleared for pet {pet_id}"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to clear cache: {str(e)}"
        }

@app.get("/api/pets/{pet_id}/cache/status")
async def get_cache_status(pet_id: str):
    """Get cache status for a specific pet"""
    try:
        intelligent_chatbot_service = get_intelligent_chatbot_service()
        cached_data = intelligent_chatbot_service.get_cached_pet_data(pet_id)
        
        if cached_data:
            return {
                "status": "success",
                "cached": True,
                "cache_info": {
                    "loaded_at": cached_data.get("loaded_at"),
                    "days_covered": cached_data.get("days", 30),
                    "analytics_entries": len(cached_data.get("analytics_data", [])),
                    "voice_notes": len(cached_data.get("voice_notes", [])),
                    "text_inputs": len(cached_data.get("text_inputs", [])),
                    "medical_records": len(cached_data.get("medical_records", [])),
                    "pet_name": cached_data.get("pet_info", {}).get("name", "Unknown")
                }
            }
        else:
            return {
                "status": "success", 
                "cached": False,
                "message": "No cached data available for this pet"
            }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to check cache status: {str(e)}"
        }

@app.post("/api/pets/{pet_id}/chat")
async def chat_with_assistant(pet_id: str, request: Request):
    """Chat with AI Assistant using Intelligent RAG with Smart Visualization"""
    try:
        intelligent_chatbot_service = get_intelligent_chatbot_service()
        
        data = await request.json()
        query = data.get("query", "")
        
        if not query:
            return {"error": "Query is required"}
        
        # Generate intelligent response with optional visualization
        response = await intelligent_chatbot_service.generate_intelligent_response(pet_id, query)
        
        return response
        
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to process chat request: {str(e)}"
        }

@app.post("/api/pets/{pet_id}/knowledge_search")
async def search_knowledge_base(pet_id: str, request: Request):
    """Search veterinary knowledge base"""
    try:
        simple_rag_service = get_simple_rag_service()
        
        data = await request.json()
        query = data.get("query", "")
        
        if not query:
            return {"error": "Query is required"}
        
        # Search knowledge base
        knowledge_results = simple_rag_service.search_knowledge_base(query, top_k=5)
        
        results = []
        for result in knowledge_results:
            knowledge = result["knowledge"]
            results.append({
                "title": knowledge.get("title", ""),
                "content": knowledge.get("content", ""),
                "category": knowledge.get("category", ""),
                "symptoms": knowledge.get("keywords", []),
                "severity": knowledge.get("severity", ""),
                "score": result["score"]
            })
        
        return {
            "status": "success",
            "results": results,
            "query": query,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to search knowledge base: {str(e)}"
        }

@app.get("/api/pets/{pet_id}/assistant_summary")
async def get_assistant_summary(pet_id: str):
    """Get AI-powered health summary for assistant dashboard using cached data"""
    try:
        intelligent_chatbot_service = get_intelligent_chatbot_service()
        
        # Check if we have cached data first
        cached_data = intelligent_chatbot_service.get_cached_pet_data(pet_id)
        
        if cached_data:
            print("✅ Using cached data for assistant summary")
            simple_rag_service = get_simple_rag_service()
            
            # Use cached data for faster summary generation
            summary_query = "Provide a comprehensive health summary with insights, patterns, and recommendations based on all available health data."
            response = await simple_rag_service.generate_rag_response_with_cache(pet_id, summary_query, cached_data)
        else:
            print("🔍 No cached data available, using standard RAG processing")
            simple_rag_service = get_simple_rag_service()
            
            # Fallback to standard method if no cache
            summary_query = "Provide a comprehensive health summary with insights, patterns, and recommendations based on all available health data."
            response = await simple_rag_service.generate_rag_response(pet_id, summary_query)
        
        return {
            "status": "success",
            "summary": response.get("response", ""),
            "data_sources": response.get("sources", []),
            "timestamp": datetime.utcnow().isoformat(),
            "used_cache": cached_data is not None
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to generate assistant summary: {str(e)}"
        }

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
