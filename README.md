# Pet Health Voice Notes

<p align="center">
  <img src="assets/login-hero.png" alt="PetPulse login – Google sign-in with feature highlights" width="600" height="auto">
</p>

## Why I Built This

During my internship, I wanted to tackle a real problem while learning specific technologies that I knew I needed to understand better. I'd been reading about how hard it is for pet owners to track subtle health changes over time - the kind of gradual shifts that are easy to miss day-to-day but important for vets to know about.

That got me thinking: people take notes about everything else, why not their pets? But more importantly, I realized this was a perfect chance to dive deep into AI integration and learn how to build something actually useful.

## What I Wanted to Learn

Going into this project, I had three specific learning goals:
1. **How to implement OpenAI function calling properly** - I'd read about it but never built anything real with it
2. **Building fast APIs that can handle real-time data** - I wanted to understand caching, async programming, and database optimization
3. **Making AI actually useful instead of just a chatbot** - I wanted the AI to take actions and generate insights, not just answer questions

I also knew I wanted experience with Firebase because so many companies use it, and I wanted to understand how speech-to-text APIs work since voice interfaces are becoming more common.

## How It Actually Works

The core idea is simple: make it dead easy to track your pet's behavior and health, then use AI to spot patterns you might miss.

**Voice Notes**: Tap to record "Buddy seems tired today, didn't finish his breakfast" and it gets transcribed and categorized automatically.

**Smart Summaries**: The AI reads through all your notes and tells you things like "You've mentioned lethargy 3 times in the past week" or "Eating patterns changed after the vet visit."

**Visualization**: Ask "show me Buddy's energy levels this month" and it generates the right chart without you having to figure out what data to plot.

I focused on voice input because typing on your phone while your dog is doing something weird is annoying. Speaking is faster and more natural.

<p align="center">
  <img src="assets/assistant-dashboard.png" alt="PetPulse – AI Health Assistant with access to notes, PDFs, and tracking data" width="600" height="auto">
</p>

## Problems I Solved While Building This

**Problem 1: OpenAI was expensive and slow**
I was calling the OpenAI API every time someone asked for a chart. That got expensive fast and made the app feel sluggish. 

*Solution*: Built a caching system that remembers recent data for 30 minutes. Now repeated requests are instant and I cut API costs by about 67%.

**Problem 2: Speech-to-text gave me walls of text**
Google's speech API just dumps everything into one long transcript. Not helpful when you want to track specific health info.

*Solution*: I pipe the transcript through OpenAI to extract the important bits and categorize them (medical vs daily activity vs feeding, etc.).

**Problem 3: People wanted different charts for different questions**
"Show me feeding times" needs a different visualization than "show me energy levels over time."

*Solution*: Used OpenAI function calling to let people ask in plain English and have the AI pick the right chart type and data automatically.

## What I Used and Why

**FastAPI + Python**: I picked FastAPI because I wanted to learn async programming properly. The automatic API docs were a nice bonus - I could test endpoints without building a separate test UI.

**Firebase**: This was a learning goal. I wanted to understand how Firebase works since so many companies use it. The real-time updates are actually useful here - when you add a note on your phone, it shows up instantly on the web dashboard.

**OpenAI GPT-4**: Started with GPT-3.5 but switched to GPT-4 when I realized function calling works way better. GPT-4 is much more reliable at extracting the right parameters for charts.

**Google Cloud Speech-to-Text**: Tried a few different speech APIs. Google's was the most accurate, especially with background noise (dogs barking, etc.).

**Vanilla JavaScript**: I know this might seem weird, but I wanted to focus on the backend learning. Adding React would have been another learning curve, and the UI is pretty simple anyway.

**Docker**: Made deployment so much easier. Instead of "works on my machine" problems, I can just send someone the docker-compose file.

## Some Key Technical Decisions

**FastAPI vs Flask**: I wanted to learn async programming, and FastAPI makes it much easier than Flask. Plus the automatic API documentation saved me tons of time - I didn't have to write separate docs.

**Firebase vs PostgreSQL**: I almost went with Postgres because it's what I know, but Firebase was a learning goal. The real-time syncing actually turned out to be really useful for this use case. When you're tracking a pet, you might add notes from your phone but want to see trends on a bigger screen.

**Custom caching vs Redis**: I probably should have used Redis, but I wanted to understand caching fundamentals first. Built a simple in-memory cache with TTL. It works for this project size, though I'd definitely use Redis for anything bigger.

**OpenAI function calling**: This was the main thing I wanted to learn. Instead of trying to parse "show me Buddy's weight over time" with regex or something, I let GPT-4 figure out the intent and extract parameters. Way more reliable than I expected.

## The Interesting Technical Bits

**Function Calling Setup**: This was the trickiest part to get right. You have to define your functions in JSON schema format, then OpenAI picks which one to call and extracts the parameters. Here's what my chart generation function looks like:

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

**The Caching System**: Turns out caching is pretty simple once you understand it. I keep expensive API results in memory for 30 minutes:

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

**Voice Processing**: The Google Speech API gives you raw text, but I needed structured data. So I run the transcript through OpenAI to extract the important bits and categorize them.

## How It Performs

The caching made a huge difference - repeated requests are basically instant now instead of waiting 2-3 seconds for OpenAI. 

I built about 20 different API endpoints, which sounds like a lot but FastAPI makes them pretty easy to add. The automatic documentation feature means I don't have to maintain separate docs.

Firebase handles multiple users automatically, which is nice. I didn't have to think about user management or authentication flows.

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

FastAPI automatically generates interactive documentation at `http://localhost:8000/docs` when you run it. That's honestly one of the best features - I didn't have to write any of this documentation manually.

**Main endpoints:**
- `/api/pets/{pet_id}/chat` - Talk to the AI about your pet
- `/api/pets/{pet_id}/textinput` - Add typed notes  
- `/api/start_recording` & `/api/stop_recording` - Voice notes
- `/api/upload_pdf` - Upload vet documents
- `/api/pets/{pet_id}/visualizations` - Generate charts

There are about 20 endpoints total, but those are the main ones you'd actually use.

## What I Learned

**OpenAI Function Calling**: This was way more powerful than I expected. Instead of trying to parse user intent with regex or traditional NLP, you can just describe your functions and let GPT-4 figure out what the user wants and extract the parameters. Much more reliable.

**Async Programming**: FastAPI forced me to really understand async/await. The performance difference is significant when you're making multiple API calls.

**Caching Strategy**: I learned that you don't always need Redis. For this project size, a simple in-memory cache with TTL worked great and reduced API costs dramatically.

**Firebase Real-time**: The real-time syncing is actually really useful for this kind of app. When you're tracking a pet, you might add notes from your phone but want to analyze trends on a computer.

## What I'd Do Differently

- Use Redis instead of custom caching for anything bigger
- Set up proper monitoring from the start (like Prometheus)
- Write more tests (I focused on getting features working first)
- Maybe use React for the frontend if I were building this for real users

## Stuff I Want to Try Next

- Adding computer vision to analyze pet photos for health insights
- Building a proper mobile app instead of a mobile-responsive web app  
- Implementing WebSocket for real-time chat with the AI
- Adding more sophisticated data analysis (trend detection, anomaly detection)

---

Built during my internship to learn AI integration and modern web development practices. The goal was understanding how these technologies work together, not building a production product.