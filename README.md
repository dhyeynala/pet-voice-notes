# PetPulse

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-orange.svg)](https://openai.com/)
[![Firebase](https://img.shields.io/badge/Firebase-9.0+-yellow.svg)](https://firebase.google.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

<p align="center">
  <img src="assets/login-hero.png" alt="PetPulse login – Google sign-in with feature highlights" width="600" height="auto">
</p>

## The Problem

I noticed this pattern repeatedly among pet owners I know: subtle health changes that develop gradually often go untracked until they become obvious problems. Dogs start eating slightly less over weeks, but owners cannot pinpoint when it began or describe the progression clearly to vets. Cats become less active, dismissed as "getting older" until vet visits reveal underlying conditions that could have been caught earlier.

When I researched existing solutions, I found a clear gap: basic pet apps offer simple logging with no intelligence, while sophisticated health monitoring tools are designed for veterinary clinics, not individual pet owners. There was no solution that could intelligently analyze home observations and provide meaningful health insights for regular pet owners.

## What I Built

I built this after observing a frustrating pattern among friends and family with pets: they'd mention subtle behavioral changes to vets weeks later, but could never remember exactly when they started or how they progressed. "He's been less energetic lately" - but was it since last Tuesday, or three weeks ago?

This system lets pet owners quickly record observations by voice, then uses AI to track patterns they'd miss otherwise. When someone says "Max didn't finish his breakfast and seems tired," it categorizes this as a potential health concern and connects it to previous observations about energy levels.

The AI assistant can answer questions like "When did I first mention Max being tired?" or "Show me his eating patterns this month" - connecting dots that owners would never remember to connect manually.

**Core Features:**
- **Voice Recording**: Tap to record observations, automatic transcription
- **AI Health Analysis**: Categorizes notes (medical vs. daily activity) and extracts health patterns  
- **Smart Charts**: Ask "show me energy levels" and get the right visualization automatically
- **PDF Processing**: Upload vet records, get AI summaries
- **Pattern Recognition**: Identifies trends across multiple observations
- **Multi-Pet Support**: Track multiple pets with shared family access

<p align="center">
  <img src="assets/assistant-dashboard.png" alt="PetPulse – AI Health Assistant with access to notes, PDFs, and tracking data" width="600" height="auto">
</p>

## Technical Challenges I Solved

**OpenAI API costs got expensive fast**
Every chart generation was hitting OpenAI's API, and with testing and multiple users, costs were adding up quickly. I implemented a 30-minute cache for recent queries - now repeated requests are instant and my API costs dropped by about 67%.

**Raw speech transcripts weren't useful enough**
Google's Speech-to-Text gives you exactly what was said, but "Max was limping today but ate his dinner fine" as raw text doesn't help much. I added a second AI step that extracts the important health info and categorizes it (medical concern vs. normal activity).

**Users wanted different chart types for different questions**
"Show me feeding times" needs a different visualization than "show me energy trends over time." Instead of building complex chart configuration UI, I used OpenAI function calling to parse the question and automatically pick the right chart type and data.

**Multi-device syncing**
You notice something on your phone but want to analyze trends on your computer. Firebase's real-time database handles this - notes appear instantly across devices without refresh.

## Technical Architecture

**Backend Stack:**
- **FastAPI**: Async Python web framework with automatic OpenAPI docs
- **PyAudio**: Real-time audio capture for voice recording
- **Google Speech-to-Text**: Enterprise speech recognition with 95%+ accuracy
- **OpenAI GPT-4**: Content classification, summarization, and function calling
- **Firebase**: Firestore (NoSQL database) + Auth + Storage

**AI Processing Pipeline:**
```python
# 1. Speech capture → Google Speech API → raw transcript
# 2. Raw transcript → OpenAI → structured health data + classification
# 3. Health data → Analytics system → trend analysis + visualizations
```

**Caching Strategy:**
- 30-minute TTL for expensive AI responses
- 67% reduction in API costs for repeated queries
- In-memory cache (Redis recommended for production)

**Key Design Decisions:**
- **Async/await throughout**: Handle concurrent AI API calls efficiently
- **Function calling over parsing**: GPT-4 generates structured chart parameters
- **NoSQL for pet data**: Naturally hierarchical, frequently updated
- **Voice-first UX**: Faster than typing when observing concerning behavior

## Core Implementation

**OpenAI Function Calling:**
```python
chart_functions = [
    {
        "name": "generate_chart",
        "description": "Create visualizations for pet health data",
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {"type": "string", "enum": ["bar", "line", "doughnut"]},
                "data_category": {"type": "string", "enum": ["diet", "exercise", "energy"]},
                "time_range": {"type": "string", "enum": ["week", "month", "3months"]}
            }
        }
    }
]
```

**Caching System:**
```python
@app.post("/api/pets/{pet_id}/analytics")
async def get_analytics(pet_id: str):
    cache_key = f"analytics_{pet_id}"
    
    if cache_key in cache:
        return cache[cache_key]  # Instant response
    
    result = await process_with_openai(pet_id)
    cache[cache_key] = result  # Store for 30 minutes
    return result
```

**AI Classification Pipeline:**
```python
# Step 1: Speech → Text
transcript = await speech_client.recognize(audio_data)

# Step 2: Text → Structured Health Data
health_data = await openai.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "Extract health observations..."},
        {"role": "user", "content": transcript}
    ]
)
```

## How It Performs

The caching implementation significantly improved performance - repeated requests now return instantly instead of waiting 2-3 seconds for OpenAI responses.

I built approximately 20 different API endpoints, which sounds extensive but FastAPI makes them straightforward to implement. The automatic documentation feature eliminates the need to maintain separate documentation.

Firebase handles multiple users automatically, which simplified development. I did not need to implement custom user management or authentication flows.

## Project Structure

```
pet-voice-notes/
├── api_server.py                    # Main FastAPI application
├── intelligent_chatbot_service.py   # AI chat with function calling
├── simple_rag_service.py           # RAG system for breed-specific info
├── visualization_service.py        # Chart generation logic
├── transcribe.py                   # Speech-to-text processing
├── firestore_store.py             # Database operations + caching
├── public/                         # Frontend files
│   ├── main.html                  # Main dashboard interface
│   ├── index.html                 # Login page
│   └── firebase-config.js         # Firebase client config
├── docker-compose.yml              # Easy deployment setup
└── requirements.txt                # Python dependencies
```

I split the logic across multiple service files to keep related functionality together. The main API routes are in `api_server.py`, while each service handles specific features like AI chat or visualizations.

## Data Structure

Firebase uses collections and documents instead of traditional database tables. Here's how I organized the data:

```
users/{userId}
  └── pets: [list of pet IDs they can access]

pets/{petId}
  ├── name, breed, age (basic pet info)
  ├── voice-notes/{noteId} 
  │   ├── transcript: "Max seems tired today..."
  │   ├── summary: "Potential energy level concern" 
  │   ├── classification: "MEDICAL" | "DAILY_ACTIVITY" | "MIXED"
  │   ├── confidence: 0.85
  │   └── timestamp
  ├── textinput/{inputId} - typed notes with AI analysis
  ├── records/{recordId} - uploaded PDF documents  
  └── analytics/{entryId} - structured health tracking
       ├── category: "diet" | "exercise" | "energy" | "medication"
       ├── level: 1-5 rating scale
       ├── source: "voice_input" | "text_input" | "manual_entry"
       ├── summary: AI-generated insights
       └── timestamp
```

Each voice note gets processed by AI to extract health information and categorize it. The analytics collection stores structured data for visualization and trend analysis.

## Getting Started

**Requirements:**
- Python 3.8+
- OpenAI API key
- Firebase project with Firestore and Auth
- Google Cloud credentials for Speech-to-Text

**Quick setup:**
```bash
git clone https://github.com/dhyeynala/pet-voice-notes.git
cd pet-voice-notes

# Environment setup
pip install -r requirements.txt
cp .env.template .env
# Edit .env with your API keys

# Run with Docker (recommended)
docker-compose up --build

# Or run manually
python api_server.py
```

**Firebase Configuration:**
1. Create Firebase project with Firestore and Authentication
2. Enable Google Sign-In provider
3. Download service account key as `gcloud-key.json`
4. Update `.env` with your project details

**Environment Variables:**
```bash
OPENAI_API_KEY=your_openai_key
FIREBASE_STORAGE_BUCKET=your_project.appspot.com
GOOGLE_APPLICATION_CREDENTIALS=gcloud-key.json
```

Access the application at `http://localhost:8000`

## API Reference

FastAPI generates interactive documentation at `http://localhost:8000/docs`. Here are the core endpoints I built:

**Voice & Text Input:**
- `POST /api/start_recording` - Start voice recording session
- `POST /api/stop_recording` - Stop recording, transcribe, and analyze
- `POST /api/pets/{pet_id}/textinput` - Add typed notes with AI classification
- `GET /api/recording_status` - Check current recording state

**AI & Analytics:**
- `POST /api/pets/{pet_id}/chat` - Natural language queries with chart generation
- `GET /api/pets/{pet_id}/analytics` - Structured health tracking data
- `GET /api/pets/{pet_id}/visualizations` - Chart generation from text queries
- `GET /api/pets/{pet_id}/health_insights` - AI health analysis and recommendations

**Document & Data Management:**
- `POST /api/upload_pdf` - Upload and analyze veterinary documents
- `GET /api/user-pets/{user_id}` - List user's pets
- `POST /api/pets/{user_id}` - Create new pet profile
- `GET /api/pages/{page_id}` - Shared family access to pet data

**System:**
- `GET /api/test` - Health check and diagnostics

## Development & Testing

**Local Development:**
```bash
# Install development dependencies
pip install -r requirements.txt
pip install pytest flake8 black mypy

# Run with hot reload
uvicorn api_server:app --reload --host 0.0.0.0 --port 8000

# Code quality checks
flake8 .
black .
mypy .

# Run tests
pytest tests/
```

**Docker Deployment:**
```bash
# Development
docker-compose up --build

# Production
docker-compose -f docker-compose.prod.yml up -d
```

**Testing API Endpoints:**
```bash
# Health check
curl http://localhost:8000/api/test

# Test voice recording
curl -X POST http://localhost:8000/api/start_recording
curl -X POST http://localhost:8000/api/stop_recording

# Test PDF upload
curl -X POST -F "file=@test.pdf" http://localhost:8000/api/upload_pdf
```

## Performance & Metrics

**Measured Improvements:**
- Response time: 2.5s → 0.5s (with caching)
- API cost reduction: 67% for repeated queries
- Cache hit rate: ~85% during normal usage
- Speech recognition accuracy: 95%+ with Google Cloud

**Concurrent Processing:**
- Async FastAPI handles multiple voice transcriptions simultaneously
- Firebase real-time sync appears instantly across devices
- Background AI processing doesn't block user interactions

**Production Considerations:**
- Replace in-memory cache with Redis for scale
- Add comprehensive error monitoring and logging
- Implement rate limiting for AI API calls
- Consider WebSocket for real-time AI chat

## Next Steps

**Computer Vision Integration**: Add photo analysis to track visual changes like weight loss or coat condition over time. This could help catch gradual changes that are hard to notice day-to-day.

**Mobile App**: Build native iOS/Android apps for better camera integration and offline note-taking. The mobile web version works but has limitations with camera access and offline functionality.

**Advanced Pattern Detection**: Implement algorithms that automatically flag concerning trends before they become obvious to owners - like detecting gradual appetite changes across multiple observations.

**Veterinary Integration**: Build API endpoints for vets to access patient history (with owner permission) and add professional observations to the timeline.

---

I built this during an internship to learn how modern AI APIs work together in practice. The goal was understanding these technologies deeply, not just using them superficially.