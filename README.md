# Pet Health Voice Notes

<p align="center">
  <img src="assets/login-hero.png" alt="PetPulse login – Google sign-in with feature highlights" width="600" height="auto">
</p>

## Why I Built This

During my internship, I wanted to tackle a real problem while learning specific technologies that I knew I needed to understand better. I'd been reading about how hard it is for pet owners to track subtle health changes over time - the kind of gradual shifts that are easy to miss day-to-day but important for vets to know about.

That got me thinking: people take notes about everything else, why not their pets? But more importantly, I realized this was a perfect chance to dive deep into AI integration and learn how to build something actually useful.

## What I Wanted to Learn

Going into this project, I had three specific learning goals:
1. **How to implement OpenAI function calling properly** - I had read about it but never built anything real with it
2. **Building fast APIs that can handle real-time data** - I wanted to understand caching, async programming, and database optimization
3. **Making AI actually useful instead of just a chatbot** - I wanted the AI to take actions and generate insights, not just answer questions

I also knew I wanted experience with Firebase because so many companies use it, and I wanted to understand how speech-to-text APIs work since voice interfaces are becoming more common.

## How It Actually Works

The core concept is straightforward: simplify pet health tracking and use AI to identify patterns that might otherwise be missed.

**Voice Notes**: Record observations like "Buddy seems tired today, did not finish his breakfast" and the system transcribes and categorizes them automatically.

**Smart Summaries**: The AI analyzes accumulated notes and provides insights such as "You have mentioned lethargy 3 times in the past week" or "Eating patterns changed after the vet visit."

**Visualization**: Ask "show me Buddy's energy levels this month" and it generates the appropriate chart without requiring manual data selection.

I prioritized voice input because capturing observations in real-time is more practical than typing detailed notes. Voice recording allows for immediate documentation of behavioral changes as they happen.

<p align="center">
  <img src="assets/assistant-dashboard.png" alt="PetPulse – AI Health Assistant with access to notes, PDFs, and tracking data" width="600" height="auto">
</p>

## Problems I Solved While Building This

**Problem 1: OpenAI API costs and latency**
I was calling the OpenAI API every time someone requested a chart. This became expensive quickly and created noticeable delays in the application response time.

*Solution*: Implemented a caching system that stores recent data for 30 minutes. Repeated requests now return instantly and API costs were reduced by approximately 67%.

**Problem 2: Unstructured speech-to-text output**
Google's speech API returns raw transcripts as continuous text blocks. This format was not useful for extracting specific health information and categorizing observations.

*Solution*: I process the transcript through OpenAI to extract relevant information and categorize it by type (medical observations, daily activity, feeding patterns, etc.).

**Problem 3: Dynamic visualization requirements**
Different queries require different chart types - "Show me feeding times" needs a different visualization approach than "show me energy levels over time."

*Solution*: Implemented OpenAI function calling to parse natural language queries and automatically select appropriate chart types and data parameters.

## What I Used and Why

**FastAPI + Python**: I chose FastAPI because I wanted to learn async programming properly. The automatic API documentation was a significant advantage - I could test endpoints without building a separate test interface.

**Firebase**: This was a specific learning objective. I wanted to understand how Firebase works since many companies use it. The real-time updates proved particularly useful - when you add a note on your phone, it appears instantly on the web dashboard.

**OpenAI GPT-4**: I started with GPT-3.5 but switched to GPT-4 when I discovered function calling works much more reliably. GPT-4 is significantly better at extracting the correct parameters for chart generation.

**Google Cloud Speech-to-Text**: I evaluated several speech APIs. Google's proved most accurate, particularly with background noise (dogs barking, household sounds, etc.).

**Vanilla JavaScript**: This might seem like an unusual choice, but I wanted to focus on backend learning. Adding React would have introduced another learning curve, and the UI requirements were relatively straightforward.

**Docker**: This simplified deployment considerably. Instead of environment-specific configuration issues, I can provide a docker-compose file for consistent setup.

## Some Key Technical Decisions

**FastAPI vs Flask**: I wanted to learn async programming, and FastAPI makes this much easier than Flask. The automatic API documentation also saved significant development time - I did not have to write separate documentation.

**Firebase vs PostgreSQL**: I almost chose PostgreSQL because it was familiar, but Firebase was a specific learning objective. The real-time synchronization proved very useful for this use case. When tracking a pet, you might add notes from your phone but want to analyze trends on a larger screen.

**Custom caching vs Redis**: I probably should have used Redis, but I wanted to understand caching fundamentals first. I built a simple in-memory cache with TTL. It works for this project size, though I would definitely use Redis for larger applications.

**OpenAI function calling**: This was the primary technology I wanted to learn. Instead of parsing queries like "show me Buddy's weight over time" with regex, I let GPT-4 determine the intent and extract parameters. This proved much more reliable than I expected.

## The Interesting Technical Bits

**Function Calling Setup**: This was the most challenging aspect to implement correctly. Functions must be defined in JSON schema format, then OpenAI selects which function to call and extracts the parameters. Here is my chart generation function:

```python
functions = [
    {
        "name": "generate_dynamic_chart",
        "description": "Create custom visualizations with flexible parameters",
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {"type": "string", "enum": ["bar", "line", "doughnut", "scatter"]},
                "x_axis": {"type": "string"},
                "y_axis": {"type": "string"},
                "filters": {"type": "object"},
                "aggregation": {"type": "string", "enum": ["count", "sum", "average"]}
            }
        }
    }
]
```

**The Caching System**: Caching proved more straightforward than expected once I understood the fundamentals. I store expensive API results in memory for 30 minutes:

```python
@app.post("/api/pets/{pet_id}/preload")
async def preload_pet_data(pet_id: str):
    cache_key = f"pet_data_{pet_id}"
    cached_data = await cache.get(cache_key)
    
    if not cached_data:
        data = await aggregate_pet_data(pet_id)
        await cache.set(cache_key, data, expire=1800)  # 30 minutes
    
    return {"status": "cached"}
```

**Voice Processing**: The Google Speech API returns raw text, but I needed structured data. I process the transcript through OpenAI to extract relevant information and categorize it appropriately.

## How It Performs

The caching implementation significantly improved performance - repeated requests now return instantly instead of waiting 2-3 seconds for OpenAI responses.

I built approximately 20 different API endpoints, which sounds extensive but FastAPI makes them straightforward to implement. The automatic documentation feature eliminates the need to maintain separate documentation.

Firebase handles multiple users automatically, which simplified development. I did not need to implement custom user management or authentication flows.

## What's In Here

```
pet-voice-notes/
├── api_server.py              # Main FastAPI app
├── intelligent_chatbot_service.py  # OpenAI function calling
├── simple_rag_service.py      # AI responses with breed info
├── visualization_service.py   # Chart generation
├── transcribe.py             # Speech-to-text processing
├── firestore_store.py        # Database + caching
├── public/                   # Frontend 
│   ├── main.html            # Main dashboard
│   └── index.html           # Login page
├── docker-compose.yml        # Easy deployment
└── requirements.txt          # Python dependencies
```

The main logic is split across a few files because I wanted to keep related functionality together. `api_server.py` handles routing, the service files handle specific features.

## How I Structured the Data

Firebase uses collections and documents instead of tables. Here's the basic structure:

```
users/{userId}
  └── pets: [list of pet IDs]

pets/{petId}
  ├── name, breed, age (basic info)
  ├── voice-notes/{noteId} - transcripts + AI summaries
  ├── textinput/{inputId} - typed notes + AI categorization  
  ├── records/{recordId} - uploaded PDFs
  └── analytics/{entryId} - structured health tracking
```

Each note (voice or text) gets processed by AI to extract the important info and categorize it as medical, feeding, exercise, etc. The analytics collection is for more structured data like weight measurements.

## Running It Yourself

**Easiest way (Docker):**
```bash
git clone [this repo]
cd pet-voice-notes
docker-compose up --build
```

**Manual setup:**
```bash
pip install -r requirements.txt
python api_server.py
```

**You'll need API keys for:**
- OpenAI (for the AI features)
- Firebase (for database/auth)  
- Google Cloud (for speech-to-text)

I put a template in the repo for the environment variables.

## API Docs

FastAPI automatically generates interactive documentation at `http://localhost:8000/docs` when you run it. This is one of the most valuable features - I did not need to write any of this documentation manually.

**Main endpoints:**
- `/api/pets/{pet_id}/chat` - Talk to the AI about your pet
- `/api/pets/{pet_id}/textinput` - Add typed notes  
- `/api/start_recording` & `/api/stop_recording` - Voice notes
- `/api/upload_pdf` - Upload vet documents
- `/api/pets/{pet_id}/visualizations` - Generate charts

There are approximately 20 endpoints total, but those are the primary ones for core functionality.

## What I Learned

**OpenAI Function Calling**: This proved much more powerful than expected. Instead of parsing user intent with regex or traditional NLP, you can describe your functions and let GPT-4 determine what the user wants and extract the parameters. Much more reliable than anticipated.

**Async Programming**: FastAPI required me to properly understand async/await patterns. The performance difference is significant when making multiple API calls.

**Caching Strategy**: I learned that Redis is not always necessary. For this project size, a simple in-memory cache with TTL worked effectively and reduced API costs dramatically.

**Firebase Real-time**: The real-time synchronization proved very useful for this application type. When tracking a pet, you might add notes from your phone but want to analyze trends on a computer.

## What I Would Do Differently

- Use Redis instead of custom caching for larger applications
- Set up proper monitoring from the start (such as Prometheus)
- Write more comprehensive tests (I focused on getting features working first)
- Consider React for the frontend if building for production users

## Future Improvements I Want to Explore

- Adding computer vision to analyze pet photos for health insights
- Building a dedicated mobile application instead of a mobile-responsive web app  
- Implementing WebSocket for real-time chat with the AI
- Adding more sophisticated data analysis (trend detection, anomaly detection)

---

Built during my internship to learn AI integration and modern web development practices. The goal was understanding how these technologies work together, not building a production product.