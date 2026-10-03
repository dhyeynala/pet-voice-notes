# api_server.py
from fastapi import Depends, FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from datetime import datetime, timedelta
from pathlib import Path
import os

"""
Environment setup

The app imports and starts with no environment at all. Configuration lives in
``petpulse.config.Settings`` (every field has a demo-safe default); storage and AI
providers are resolved lazily through ``petpulse.deps``. Nothing reads key files or
builds SDK clients at import time.
"""

# Load .env (if present) so legacy os.getenv() reads see the same values as Settings.
load_dotenv()

from fastapi import HTTPException  # noqa: E402

from petpulse import errors, seed  # noqa: E402
from petpulse.auth import (  # noqa: E402
    current_user,
    require_body_pet_access,
    require_pet_access,
    require_query_pet_access,
    require_self,
)
from petpulse.deps import get_blobs, get_llm, get_settings, get_store  # noqa: E402
from petpulse.routers import analytics as analytics_router  # noqa: E402
from petpulse.routers import assistant as assistant_router  # noqa: E402
from petpulse.routers import demo as demo_router  # noqa: E402
from petpulse.routers import health as health_router  # noqa: E402
from petpulse.routers import insights as insights_router  # noqa: E402
from petpulse.routers import notes as notes_router  # noqa: E402
from petpulse.routers import pets as pets_router  # noqa: E402
from petpulse.routers import records as records_router  # noqa: E402

from main import main as run_main
from firestore_store import get_pets_by_user_id, add_pet_to_page_and_user, db, store_to_firestore
from transcribe import start_recording, stop_recording, get_recording_status

# Lazy-loaded service instances to improve startup performance
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


PUBLIC_DIR = Path(__file__).resolve().parent / "public"

app = FastAPI(title="PetPulse")

# Errors: one JSON shape ({"detail", "request_id"}), real status codes, no str(e) leaks on 500.
errors.install(app)

# CORS: explicit allow-list from settings (ALLOWED_ORIGINS). Auth is a bearer header, not a
# cookie, so credentials are never allowed and no origin is reflected.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

# Every /api route except /api/health, /api/demo/users and /api/demo/login needs a bearer
# token (petpulse.auth); routes that touch a pet also check that the caller owns it.
PET_ACCESS = [Depends(require_pet_access)]
BODY_PET_ACCESS = [Depends(require_body_pet_access)]


# Startup event to pre-warm critical services
@app.on_event("startup")
async def startup_event():
    """Pre-warm critical services to improve first request performance"""
    print("🚀 Starting PetPulse API server...")
    # Fail fast on contradictory provider config (e.g. LLM_PROVIDER=openai without a key).
    settings = get_settings()
    settings.check()
    print(
        f"Mode: {settings.overall_mode()} | store={settings.store} llm={settings.resolved_llm()} stt={settings.resolved_stt()}"
    )
    print("🔥 Pre-warming critical services...")

    # Pre-warm only the most commonly used service (visualization)
    # to balance startup time vs first-request performance
    try:
        _ = get_visualization_service()
        print("Visualization service pre-warmed")
    except Exception as e:
        print(f"⚠️ Failed to pre-warm visualization service: {e}")

    print("🎉 PetPulse API server ready!")


@app.on_event("startup")
async def load_demo_seed():
    """Load the demo seed into an empty store (SEED_ON_START=true, the default)."""
    if get_settings().seed_on_start:
        seed.seed_if_empty(get_store(), blobs=get_blobs())


@app.post("/api/start", dependencies=BODY_PET_ACCESS)
async def start(request: Request):
    data = await request.json()
    return run_main(data["uid"], data["pet"])


@app.post("/api/upload_pdf", dependencies=BODY_PET_ACCESS)
async def upload_pdf(request: Request, file: UploadFile = File(...)):
    """Legacy upload route; delegates to the safe implementation in petpulse/routers/records.py.

    Kept until the frontend switches to ``POST /api/pets/{pet_id}/records`` (review C3).
    """
    from petpulse.deps import get_store

    form = await request.form()
    pet = form.get("pet")
    if not isinstance(pet, str) or not pet:
        raise HTTPException(status_code=422, detail="Missing pet parameter")
    store = get_store()
    if store.get(f"pets/{pet}") is None:
        raise HTTPException(status_code=404, detail="pet not found")

    data = await records_router.read_capped(file)
    record = await records_router.create_record(store, get_blobs(), pet, data, file.filename)
    # No public URL: the original is served by the owner-checked records/{id}/file route.
    return {"message": "PDF processed", "summary": record["summary"], "url": None, "record": record}


@app.get("/api/user-pets/{user_id}", dependencies=[Depends(require_self)])
async def get_user_pets(user_id: str):
    return get_pets_by_user_id(user_id)


@app.post("/api/pets/{user_id}", dependencies=[Depends(require_self)])
async def create_pet(user_id: str, request: Request):
    data = await request.json()

    # Validate required fields
    if not data.get("name"):
        raise HTTPException(status_code=422, detail="Pet name is required")
    if not data.get("animal_type"):
        raise HTTPException(status_code=422, detail="Animal type is required")

    try:
        result = add_pet_to_page_and_user(user_id, data, data.get("pageId", "default-page"))
        return {"status": "success", "pet": result}
    except Exception as e:
        print(f"Failed to create pet: {e}")
        raise HTTPException(status_code=500, detail="Failed to create pet") from None


# Markdown notes live on the (owned) pet only; the shared "pages" (default-page) are gone (C2).
# ``page`` is still accepted from old clients and ignored.
@app.get("/api/markdown", dependencies=[Depends(require_query_pet_access)])
async def get_markdown(page: str = None, pet: str = None):
    if not pet:
        return {"markdown": ""}

    pet_data = db.collection("pets").document(pet).get().to_dict() or {}
    return {"markdown": pet_data.get("markdown", "")}


@app.post("/api/markdown", dependencies=BODY_PET_ACCESS)
async def update_markdown(request: Request):
    data = await request.json()
    pet = data["pet"]
    markdown = data.get("markdown", "")

    db.collection("pets").document(pet).set({"markdown": markdown}, merge=True)
    return {"status": "updated"}


# NEW: Add text input note under each pet
@app.post("/api/pets/{pet_id}/textinput", dependencies=PET_ACCESS)
async def add_pet_textinput(pet_id: str, request: Request):
    data = await request.json()
    input_text = data.get("input", "")
    if not input_text:
        raise HTTPException(status_code=422, detail="Input is empty")

    # Enhanced: Classify and summarize the content
    from summarize_openai import summarize_text, classify_pet_content

    # Classify the content type (UNKNOWN + needs_review when the model is unavailable or invalid)
    classification = classify_pet_content(input_text)

    # Generate AI summary (None when it could not be generated; never an error string)
    summary = summarize_text(input_text)

    content_type = classification.get("classification", "UNKNOWN")
    confidence = classification.get("confidence", 0.0)
    needs_review = bool(classification.get("needs_review")) or summary is None

    # Store with enhanced metadata
    entry_data = {
        "input": input_text,
        "summary": summary,
        "content_type": content_type,
        "confidence": confidence,
        "keywords": classification.get("keywords", []),
        "needs_review": needs_review,
        "timestamp": datetime.utcnow().isoformat(),
    }

    db.collection("pets").document(pet_id).collection("textinput").add(entry_data)

    # If daily activity content, also store in analytics for dashboard visibility
    if content_type == 'DAILY_ACTIVITY' and summary is not None:
        from firestore_store import store_analytics_from_voice

        store_analytics_from_voice(pet_id, input_text, summary, classification)
        print(f"Daily activity from text input also stored in analytics collection")

    return {
        "status": "success",
        "summary": summary,
        "content_type": content_type,
        "confidence": confidence,
        "keywords": classification.get("keywords", []),
        "needs_review": needs_review,
        "message": (
            "Added note; AI processing was unavailable, so it needs review"
            if needs_review
            else f"Added {content_type.lower()} note with AI summary"
        ),
    }


# NEW: Start recording endpoint
@app.post("/api/start_recording", dependencies=BODY_PET_ACCESS)
async def start_recording_endpoint(request: Request):
    data = await request.json()
    user_id = data.get("uid")
    pet_id = data.get("pet")

    if not user_id or not pet_id:
        raise HTTPException(status_code=422, detail="Missing uid or pet")

    result = start_recording()
    return result


# NEW: Stop recording endpoint
@app.post("/api/stop_recording", dependencies=BODY_PET_ACCESS)
async def stop_recording_endpoint(request: Request):
    data = await request.json()
    user_id = data.get("uid")
    pet_id = data.get("pet")

    if not user_id or not pet_id:
        raise HTTPException(status_code=422, detail="Missing uid or pet")

    try:
        result = stop_recording()

        # The legacy transcriber reports "no speech" and failures as transcript *strings*.
        # Those must never be classified, summarized or stored as a note (review H2).
        transcript = result.get("transcript") if result.get("status") == "stopped" else None
        if isinstance(transcript, str) and transcript.startswith("Error:"):
            print(f"Transcription failed: {transcript}")
            raise HTTPException(status_code=502, detail="Transcription failed; nothing was saved")
        if isinstance(transcript, str) and (transcript == "No speech detected" or not transcript.strip()):
            transcript = None

        # Handle the transcription result
        if transcript:
            # We have a transcript, try to process with AI
            try:
                from summarize_openai import summarize_text, classify_pet_content

                # Classify the content type
                classification = classify_pet_content(transcript)

                # Generate enhanced summary (None if unavailable)
                summary = summarize_text(transcript)
                content_type = classification.get("classification", "UNKNOWN")
                confidence = classification.get("confidence", 0.0)
                needs_review = bool(classification.get("needs_review")) or summary is None

            except Exception as ai_error:
                print(f"AI processing failed: {ai_error}")
                summary, content_type, confidence, needs_review = None, "UNKNOWN", 0.0, True
                classification = {"keywords": []}

            # Store with enhanced metadata
            entry_data = {
                "transcript": transcript,
                "summary": summary,
                "content_type": content_type,
                "confidence": confidence,
                "keywords": classification.get("keywords", []),
                "needs_review": needs_review,
                "timestamp": datetime.utcnow().isoformat(),
            }

            db.collection("pets").document(pet_id).collection("voice-notes").add(entry_data)

            return {
                "status": "success",
                "transcript": transcript,
                "summary": summary,
                "content_type": content_type,
                "confidence": confidence,
                "needs_review": needs_review,
                "message": (
                    "Saved voice note; AI processing was unavailable, so it needs review"
                    if needs_review
                    else f"Processed {content_type.lower()} voice note"
                ),
            }

        elif result["status"] == "stopped":
            # Recording stopped but no transcript (no speech detected): nothing is stored
            return {"status": "stopped", "message": "Recording stopped but no speech was detected"}

        else:
            # Recording failed or other error
            message = result.get("message", "Recording failed")
            raise HTTPException(status_code=409 if message == "Not recording" else 422, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in stop_recording_endpoint: {e}")
        raise HTTPException(status_code=500, detail="Server error while stopping the recording") from None


# NEW: Get recording status endpoint
@app.get("/api/recording_status", dependencies=[Depends(current_user)])
async def recording_status_endpoint():
    return get_recording_status()


# Enhanced Analytics endpoints for comprehensive pet tracking
@app.post("/api/pets/{pet_id}/analytics/{category}", dependencies=PET_ACCESS)
async def add_analytics_entry(pet_id: str, category: str, request: Request):
    """Typed write (review M7); delegates to petpulse/routers/analytics.py."""
    import json

    from fastapi.responses import JSONResponse

    from petpulse.deps import get_store

    try:
        data = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail="request body must be JSON") from None

    entry = analytics_router.create_entry(get_store(), pet_id, category, data)
    return JSONResponse(status_code=201, content=entry)


@app.get("/api/pets/{pet_id}/analytics", dependencies=PET_ACCESS)
async def get_analytics_data(pet_id: str, category: str = None, days: int = 30):
    """Typed analytics entries of the last ``days`` days, newest first (``[Entry]``, see the API contract).

    Notes (voice/text) are no longer mixed in here; they have their own routes.
    """
    from petpulse.deps import get_store

    return analytics_router.list_entries(get_store(), pet_id, category, days)


@app.get("/api/pets/{pet_id}/analytics/summary", dependencies=PET_ACCESS)
async def get_analytics_summary(pet_id: str):
    """Get summary statistics for all analytics categories including voice-notes.

    Rows with a missing or malformed timestamp are skipped and counted in ``skipped_rows``
    instead of failing the whole request (review M3).
    """
    from collections import defaultdict
    from datetime import datetime, timedelta

    parse_timestamp = analytics_router.parse_timestamp

    # Get all analytics data
    analytics_results = db.collection("pets").document(pet_id).collection("analytics").stream()

    # Also get voice-notes that might contain daily activities
    voice_results = db.collection("pets").document(pet_id).collection("voice-notes").stream()

    # Also get text input notes
    text_results = db.collection("pets").document(pet_id).collection("textinput").stream()

    summary = defaultdict(lambda: {"total": 0, "this_week": 0, "avg_daily": 0, "recent_entries": []})
    skipped = 0

    one_week_ago = datetime.utcnow() - timedelta(days=7)

    def add(category, entry, timestamp):
        summary[category]["total"] += 1
        summary[category]["recent_entries"].append(entry)
        if timestamp >= one_week_ago:
            summary[category]["this_week"] += 1

    # Process analytics collection data
    for doc in analytics_results:
        data = doc.to_dict()
        timestamp = parse_timestamp(data.get("timestamp"))
        if timestamp is None:
            skipped += 1
            continue
        add(str(data.get("category") or "unknown"), data, timestamp)

    # Process voice-notes and classify as daily activities
    for doc in voice_results:
        data = doc.to_dict()
        timestamp = parse_timestamp(data.get("timestamp"))
        if timestamp is None:
            skipped += 1
            continue

        # Classify as daily activity for now (could enhance with stored classification)
        category = "daily_activity"
        voice_entry = {
            "category": category,
            "source": "voice_note",
            "transcript": data.get("transcript", ""),
            "summary": data.get("summary"),
            "timestamp": data.get("timestamp"),
        }
        add(category, voice_entry, timestamp)

    # Process text input data with classification
    for doc in text_results:
        data = doc.to_dict()
        timestamp = parse_timestamp(data.get("timestamp"))
        if timestamp is None:
            skipped += 1
            continue

        # Use the stored classification; anything else (including UNKNOWN) is not assumed to be daily activity
        content_type = data.get("content_type", "UNKNOWN")
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
            "summary": data.get("summary"),
            "content_type": content_type,
            "timestamp": data.get("timestamp"),
        }
        add(category, text_entry, timestamp)

    # Calculate averages
    for category in summary:
        if summary[category]["total"] > 0:
            summary[category]["avg_daily"] = round(summary[category]["this_week"] / 7, 1)
            # Keep only most recent 5 entries
            summary[category]["recent_entries"] = sorted(
                summary[category]["recent_entries"], key=lambda x: parse_timestamp(x.get("timestamp")), reverse=True
            )[:5]

    if skipped:
        print(f"analytics summary: skipped {skipped} row(s) with a missing or invalid timestamp (pet={pet_id})")
    return {"summary": dict(summary), "skipped_rows": skipped}


@app.post("/api/pets/{pet_id}/daily_routine", dependencies=PET_ACCESS)
async def generate_daily_routine_headlines(pet_id: str, request: Request):
    """Generate AI-powered daily routine headlines based on analytics data"""
    try:
        pet_ai = get_pet_ai()

        data = await request.json()
        date = data.get("date", datetime.utcnow().strftime("%Y-%m-%d"))

        # Get analytics data for the specified date
        start_date = f"{date}T00:00:00"
        end_date = f"{date}T23:59:59"

        query = (
            db.collection("pets")
            .document(pet_id)
            .collection("analytics")
            .where("timestamp", ">=", start_date)
            .where("timestamp", "<=", end_date)
        )

        daily_data = []
        for doc in query.stream():
            data_entry = doc.to_dict()
            data_entry["id"] = doc.id
            daily_data.append(data_entry)

        # Get historical data for context (last 30 days)
        historical_start = (datetime.utcnow() - timedelta(days=30)).isoformat()
        historical_query = (
            db.collection("pets").document(pet_id).collection("analytics").where("timestamp", ">=", historical_start)
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

        return {"headlines": headlines, "date": date, "data_points": len(daily_data), "pet_name": pet_name}

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

    query = (
        db.collection("pets")
        .document(pet_id)
        .collection("analytics")
        .where("timestamp", ">=", start_date)
        .where("timestamp", "<=", end_date)
    )

    daily_data = []
    for doc in query.stream():
        daily_data.append(doc.to_dict())

    # Get pet name
    pet_doc = db.collection("pets").document(pet_id).get()
    pet_name = pet_doc.to_dict().get("name", "Pet") if pet_doc.exists else "Pet"

    # Generate headlines based on the data
    headlines = generate_routine_headlines(pet_name, daily_data, date)

    return {"headlines": headlines, "date": date, "data_points": len(daily_data)}


@app.get("/api/pets/{pet_id}/health_insights", dependencies=PET_ACCESS)
async def get_health_insights(pet_id: str, days: int = 30):
    """Get AI-powered health insights and recommendations"""
    try:
        pet_ai = get_pet_ai()

        # Get analytics data for the specified timeframe
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        query = db.collection("pets").document(pet_id).collection("analytics").where("timestamp", ">=", cutoff_date)

        analytics_data = []
        for doc in query.stream():
            data_entry = doc.to_dict()
            data_entry["id"] = doc.id
            analytics_data.append(data_entry)

        # Get pet name
        pet_doc = db.collection("pets").document(pet_id).get()
        pet_name = pet_doc.to_dict().get("name", "Pet") if pet_doc.exists else "Pet"

        # Generate AI insights (rule-based, with no invented score, when the model is unavailable)
        insights = pet_ai.generate_health_insights(pet_name, analytics_data, days)

        return {"insights": insights, "timeframe_days": days, "data_points": len(analytics_data), "pet_name": pet_name}

    except Exception as e:
        # No fabricated fallback (review H2): say the insights are unavailable instead.
        print(f"Health insights failed for pet {pet_id}: {e}")
        raise HTTPException(status_code=503, detail="Health insights are temporarily unavailable") from None


@app.get("/api/pets/{pet_id}/visualizations", dependencies=PET_ACCESS)
async def get_visualization_data(pet_id: str, chart_type: str = "all", days: int = 30):
    """Get data for various chart visualizations including voice recordings"""
    try:
        visualization_service = get_visualization_service()

        # Get analytics data
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        query = db.collection("pets").document(pet_id).collection("analytics").where("timestamp", ">=", cutoff_date)

        analytics_data = []
        for doc in query.stream():
            data_entry = doc.to_dict()
            data_entry["id"] = doc.id
            analytics_data.append(data_entry)

        # Also include voice-notes as daily activities for charts
        voice_query = db.collection("pets").document(pet_id).collection("voice-notes").where("timestamp", ">=", cutoff_date)

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
                "notes": f"Voice recording: {data.get('summary', '')[:100]}...",
            }
            analytics_data.append(voice_entry)

        # Also include text input notes as daily activities for charts
        text_query = db.collection("pets").document(pet_id).collection("textinput").where("timestamp", ">=", cutoff_date)

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
                "notes": f"Text note: {data.get('summary', '')[:100]}...",
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

        return {"visualizations": visualizations, "data_points": len(analytics_data), "timeframe_days": days}

    except Exception as e:
        print(f"Failed to generate visualizations for pet {pet_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate visualizations") from None


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

    import math

    def number(value):
        # Missing or malformed values are skipped, not assumed (review M3, H2).
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return None
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None

    if "exercise" in categories:
        exercise_count = len(categories["exercise"])
        durations = [number(e.get("duration")) for e in categories["exercise"]]
        total_duration = int(sum(d for d in durations if d is not None and d > 0))
        if total_duration > 60:
            headlines.append(f"🏃 Active day: {pet_name} exercised for {total_duration} minutes!")
        elif exercise_count > 1:
            headlines.append(f"🚶 {pet_name} stayed active with {exercise_count} exercise sessions")

    if "energy_levels" in categories:
        energy_levels = [lvl for lvl in (number(e.get("level")) for e in categories["energy_levels"]) if lvl is not None]
        avg_energy = sum(energy_levels) / len(energy_levels) if energy_levels else None
        if avg_energy is None:
            pass
        elif avg_energy >= 4:
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


# NEW: RAG-powered AI Assistant endpoints
@app.post("/api/pets/{pet_id}/preload", dependencies=PET_ACCESS)
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
        print(f"Failed to preload pet data for {pet_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to preload pet data") from None


@app.post("/api/pets/{pet_id}/cache/clear", dependencies=PET_ACCESS)
async def clear_pet_cache(pet_id: str):
    """Clear cached data for a specific pet"""
    try:
        intelligent_chatbot_service = get_intelligent_chatbot_service()
        intelligent_chatbot_service.clear_pet_cache(pet_id)

        return {"status": "success", "message": f"Cache cleared for pet {pet_id}"}

    except Exception as e:
        print(f"Failed to clear cache for {pet_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear cache") from None


@app.get("/api/pets/{pet_id}/cache/status", dependencies=PET_ACCESS)
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
                    "pet_name": cached_data.get("pet_info", {}).get("name", "Unknown"),
                },
            }
        else:
            return {"status": "success", "cached": False, "message": "No cached data available for this pet"}

    except Exception as e:
        print(f"Failed to check cache status for {pet_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to check cache status") from None


@app.post("/api/pets/{pet_id}/chat", dependencies=PET_ACCESS)
async def chat_with_assistant(
    pet_id: str,
    request: Request,
    user=Depends(current_user),
    pet=Depends(require_pet_access),
    store=Depends(get_store),
    llm=Depends(get_llm),
):
    """Chat. A contract body ``{"message", "tz"}`` goes to the grounded assistant (Track C,
    ``petpulse.routers.assistant``); the legacy body ``{"query"}`` still reaches the legacy
    intelligent chatbot until the cleanup PR removes this handler."""
    payload = await request.json()
    if isinstance(payload, dict) and "message" in payload:
        return await assistant_router.chat_from_payload(pet_id, payload, user, pet, store, llm)
    try:
        intelligent_chatbot_service = get_intelligent_chatbot_service()

        data = await request.json()
        query = data.get("query", "")

        if not query:
            raise HTTPException(status_code=422, detail="Query is required")

        # Generate intelligent response with optional visualization
        response = await intelligent_chatbot_service.generate_intelligent_response(pet_id, query)
        if response.get("status") == "error":
            # The service reports a model failure in-band; surface it as an HTTP error, not a 200 answer.
            print(f"Chat failed for pet {pet_id}: {response.get('error')}")
            raise HTTPException(status_code=503, detail="The assistant is temporarily unavailable")

        return response

    except HTTPException:
        raise
    except Exception as e:
        print(f"Failed to process chat request for {pet_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process chat request") from None


@app.post("/api/pets/{pet_id}/knowledge_search", dependencies=PET_ACCESS)
async def search_knowledge_base(pet_id: str, request: Request):
    """Search veterinary knowledge base"""
    try:
        simple_rag_service = get_simple_rag_service()

        data = await request.json()
        query = data.get("query", "")

        if not query:
            raise HTTPException(status_code=422, detail="Query is required")

        # Search knowledge base
        knowledge_results = simple_rag_service.search_knowledge_base(query, top_k=5)

        results = []
        for result in knowledge_results:
            knowledge = result["knowledge"]
            results.append(
                {
                    "title": knowledge.get("title", ""),
                    "content": knowledge.get("content", ""),
                    "category": knowledge.get("category", ""),
                    "symptoms": knowledge.get("keywords", []),
                    "severity": knowledge.get("severity", ""),
                    "score": result["score"],
                }
            )

        return {"status": "success", "results": results, "query": query, "timestamp": datetime.utcnow().isoformat()}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Failed to search knowledge base: {e}")
        raise HTTPException(status_code=500, detail="Failed to search knowledge base") from None


@app.get("/api/pets/{pet_id}/assistant_summary", dependencies=PET_ACCESS)
async def get_assistant_summary(pet_id: str):
    """Get AI-powered health summary for assistant dashboard using cached data"""
    try:
        intelligent_chatbot_service = get_intelligent_chatbot_service()

        # Check if we have cached data first
        cached_data = intelligent_chatbot_service.get_cached_pet_data(pet_id)

        if cached_data:
            print("Using cached data for assistant summary")
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
            "used_cache": cached_data is not None,
        }

    except Exception as e:
        print(f"Failed to generate assistant summary for {pet_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate assistant summary") from None


# New-style routers (one per track). Registered before the static mount.
app.include_router(health_router.router)
app.include_router(demo_router.router)
app.include_router(pets_router.router)
app.include_router(records_router.router)
app.include_router(analytics_router.router)
# Track C. Note: the legacy POST /api/pets/{pet_id}/chat above still matches first until it is removed.
app.include_router(notes_router.router)
app.include_router(assistant_router.router)
app.include_router(insights_router.router)


# Serve index last to avoid route shadowing
@app.get("/")
async def serve_index():
    return FileResponse(PUBLIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="static")
