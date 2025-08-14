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

I built this because I kept noticing something frustrating: my dog would have subtle changes in behavior that I'd mention to the vet weeks later, but I could never remember exactly when they started or how they progressed. "He's been less energetic lately" - but was it since last Tuesday, or three weeks ago?

This system lets me quickly record observations by voice, then uses AI to track patterns I'd miss otherwise. When I say "Max didn't finish his breakfast and seems tired," it categorizes this as a potential health concern and connects it to previous observations about his energy levels.

The AI assistant can answer questions like "When did I first mention Max being tired?" or "Show me his eating patterns this month" - connecting dots that I'd never remember to connect manually.

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

## How I Built It

**Backend: FastAPI + Python**
I chose FastAPI because it handles async operations well and generates API documentation automatically. The backend processes speech, calls various AI APIs, and manages data flow between services.

**Database: Firebase Firestore**  
NoSQL made sense here because pet data doesn't fit neatly into tables - each pet has different numbers of notes, medical records, and activity entries. Firebase also handles real-time syncing and user authentication.

**AI Integration**
- **Google Speech-to-Text**: Converts voice recordings to text
- **OpenAI GPT-4**: Processes transcripts to extract health information and generate insights
- **Function Calling**: Lets GPT-4 automatically generate appropriate charts based on natural language queries

**Frontend: Vanilla JavaScript**
Kept it simple with vanilla JS since the complexity is in the backend AI processing. Uses Firebase SDK for real-time updates and Chart.js for visualizations.

**Key Architecture Decisions:**
- Split functionality across multiple service files to keep code organized
- Implemented caching to reduce AI API costs and improve response times
- Used OpenAI function calling instead of trying to parse user queries manually

## Implementation Details

**The Function Calling Setup**
This was the trickiest part to get working. You define your functions in JSON schema format, and GPT-4 figures out which one to call based on what the user asks for:

```python
chart_functions = [
    {
        "name": "generate_chart",
        "description": "Create visualizations for pet health data",
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {"type": "string", "enum": ["bar", "line", "doughnut"]},
                "data_category": {"type": "string", "enum": ["diet", "exercise", "energy", "medication"]},
                "time_range": {"type": "string", "enum": ["week", "month", "3months"]},
                "aggregation": {"type": "string", "enum": ["daily", "weekly"]}
            }
        }
    }
]
```

**Caching Implementation**
I store expensive AI responses for 30 minutes to avoid repeated API calls:

```python
cache = {}  # In production, use Redis

@app.post("/api/pets/{pet_id}/analytics")
async def get_analytics(pet_id: str):
    cache_key = f"analytics_{pet_id}"
    
    if cache_key in cache:
        return cache[cache_key]
    
    # Expensive AI processing here
    result = await process_analytics_data(pet_id)
    cache[cache_key] = result
    
    return result
```

**Speech Processing Pipeline**
Raw transcripts from Google go through OpenAI to extract structured information:

```python
# Step 1: Speech to text
transcript = speech_client.recognize(audio_data)

# Step 2: Extract health information  
health_info = openai.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "Extract health observations from this pet note..."},
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
  │   ├── category: "medical" | "daily_activity"
  │   └── timestamp
  ├── textinput/{inputId} - typed notes with AI analysis
  ├── records/{recordId} - uploaded PDF documents  
  └── analytics/{entryId} - structured health tracking data
       ├── category: "diet" | "exercise" | "energy" | "medication"
       ├── level: 1-5 rating scale
       ├── notes: additional context
       └── timestamp
```

Each voice note gets processed by AI to extract the important health information and categorize it. The analytics collection stores more structured data like energy levels on a 1-5 scale.

## Getting Started

**Quick start with Docker:**
```bash
git clone https://github.com/dhyeynala/pet-voice-notes.git
cd pet-voice-notes
docker-compose up --build
```

**Manual setup:**
```bash
pip install -r requirements.txt

# Set up environment variables
cp .env.template .env
# Edit .env with your API keys

python api_server.py
```

**Required API Keys:**
- OpenAI API key (for AI features)
- Firebase project credentials (for database/auth)  
- Google Cloud credentials (for speech-to-text)

The `.env.template` file shows exactly what environment variables you need.

## API Reference

FastAPI generates interactive documentation automatically at `http://localhost:8000/docs` when you run the server. This shows all endpoints with request/response schemas.

**Key endpoints:**
- `POST /api/pets/{pet_id}/chat` - Ask the AI questions about your pet's data
- `POST /api/pets/{pet_id}/textinput` - Add typed notes with AI analysis
- `POST /api/start_recording` - Start voice recording session
- `POST /api/stop_recording` - Stop recording and process transcript  
- `POST /api/upload_pdf` - Upload veterinary documents
- `GET /api/pets/{pet_id}/visualizations` - Generate charts from natural language queries
- `GET /api/pets/{pet_id}/analytics` - Get structured analytics data
- `POST /api/pets/{pet_id}/analytics/{category}` - Add specific health tracking data

The system has about 20 endpoints total covering voice notes, text input, PDF processing, analytics, and AI chat functionality.

## Performance Notes

The caching system significantly improved response times. Chart generation requests that used to take 2-3 seconds while waiting for OpenAI now return instantly for repeated queries. This also reduced my API costs by about 67%.

Firebase handles real-time syncing automatically, so notes appear across devices without refresh. The async Python backend processes multiple concurrent requests efficiently, which is important when handling speech transcription and AI analysis at the same time.

For production scale, I'd replace the in-memory cache with Redis and add proper error monitoring, but this setup works well for the current scope.

## What I Learned

This project taught me how different AI APIs work together in practice. Function calling with GPT-4 is much more reliable than trying to parse free-form responses. Google's Speech-to-Text handles background noise better than I expected, but you still need post-processing to extract useful information.

Caching AI responses was crucial for both performance and cost control. Firebase's real-time features simplified the multi-device synchronization significantly.

The biggest challenge was getting the right balance between automation and user control - the AI should be smart enough to categorize observations correctly, but users need to be able to override when it gets things wrong.

## Next Steps

**Computer Vision Integration**: Add photo analysis to track visual changes like weight loss or coat condition over time. This could help catch gradual changes that are hard to notice day-to-day.

**Mobile App**: Build native iOS/Android apps for better camera integration and offline note-taking. The mobile web version works but has limitations with camera access and offline functionality.

**Advanced Pattern Detection**: Implement algorithms that automatically flag concerning trends before they become obvious to owners - like detecting gradual appetite changes across multiple observations.

**Veterinary Integration**: Build API endpoints for vets to access patient history (with owner permission) and add professional observations to the timeline.

---

I built this during an internship to learn how modern AI APIs work together in practice. The goal was understanding these technologies deeply, not just using them superficially.