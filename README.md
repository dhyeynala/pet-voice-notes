# Pet Voice Notes

A web app for recording voice notes about your pets and getting AI insights about their health.

## Why I Built This

During my internship, I wanted to get hands-on experience with APIs that I'd only read about but never implemented. I was specifically curious about OpenAI's function calling feature and Google Cloud's speech-to-text service. 

My dog has some ongoing health issues, and I kept forgetting to mention things to the vet during appointments. I thought it would be useful to have a simple way to record quick voice notes about his behavior and symptoms, then have AI help me spot patterns or organize the information before vet visits.

This seemed like a good project to practice building a full-stack application with some interesting technical challenges: real-time audio processing, AI integration, and handling user data securely.

## What It Does

- Record voice notes about your pet's behavior, symptoms, or general observations
- Automatically transcribe the audio using Google Cloud Speech-to-Text
- Use OpenAI to summarize the notes and categorize them (medical, daily activity, etc.)
- Upload and parse PDF medical records from your vet
- Create simple charts and visualizations of your pet's health data
- Ask questions about your pet's health history using an AI assistant

The main goal was to have a single place where I could quickly capture information about my pet and then use AI to help me make sense of it all.

## Technology Choices

### Backend: FastAPI + Python
I chose FastAPI because I wanted to learn about async Python programming and was interested in the automatic API documentation feature. The async support seemed important for handling audio file uploads and API calls to external services without blocking other requests.

### Database: Firebase Firestore
I went with Firebase because I wanted to focus on the application logic rather than setting up and managing a database server. The real-time synchronization features seemed useful for a multi-user application, and Firebase Auth handled user management without me having to implement it from scratch.

### AI Services: OpenAI + Google Cloud
- **OpenAI GPT-4**: I used this for text summarization and the function calling feature to dynamically generate charts based on natural language queries
- **Google Cloud Speech-to-Text**: This handles the voice-to-text transcription. I tried a few different options but Google's service had the best accuracy for casual speech

### Frontend: Vanilla JavaScript
I deliberately avoided React or other frameworks because I wanted to understand how modern JavaScript features work without abstractions. All the interactivity is built with ES6+ features, and I used Chart.js for data visualizations.

## Technical Challenges I Worked Through

### Handling Audio Files
Getting audio recording to work in the browser was trickier than I expected. I had to learn about the MediaRecorder API and figure out how to stream audio data to the backend. The main issue was that different browsers support different audio formats, so I had to add conversion logic on the server side.

### OpenAI Function Calling
This was the most interesting part for me. Instead of just asking OpenAI to generate text, I can give it a set of functions (like "create a chart" or "search health records") and it decides which function to call based on what the user asks. Getting the function definitions right took some trial and error.

### Managing API Costs
OpenAI API calls can get expensive quickly, especially when summarizing lots of text. I implemented a simple caching system that stores results for 30 minutes to avoid re-processing the same data. This helped a lot with both cost and response times.

### Real-time Data Updates
Firebase's real-time features are pretty neat, but I had to be careful about when to trigger updates. Too many real-time listeners can impact performance, so I only use them for critical data that needs to stay synchronized across multiple browser tabs.

## Code Structure

The application has several main components:

### API Server (`api_server.py`)
This is the main FastAPI application that handles all the HTTP endpoints. It coordinates between different services and manages the request/response cycle.

### AI Services
- `intelligent_chatbot_service.py` - Handles the OpenAI function calling for the chat interface
- `simple_rag_service.py` - Manages AI-powered search through pet health data
- `summarize_openai.py` - Summarizes voice notes and text input using OpenAI

### Data Processing
- `transcribe.py` - Converts audio files to text using Google Cloud Speech-to-Text
- `pdf_parser.py` - Extracts text from uploaded medical documents
- `visualization_service.py` - Generates charts and graphs based on user requests

### Database
- `firestore_store.py` - All database operations and basic caching logic

### Frontend (`public/`)
- `main.html` - The main application interface
- `index.html` - Login and authentication page
- `styles.css` - All the styling
- Plain JavaScript handles user interactions and calls the API endpoints

## Getting Started

### Using Docker (Easiest)
```bash
git clone https://github.com/YOUR_USERNAME/pet-voice-notes.git
cd pet-voice-notes
docker-compose up --build
```

### Manual Setup
```bash
git clone https://github.com/YOUR_USERNAME/pet-voice-notes.git
cd pet-voice-notes
pip install -r requirements.txt

# You'll need to set up API keys:
# - OpenAI API key
# - Firebase project credentials
# - Google Cloud Speech-to-Text API key

python api_server.py
```

The app will be available at `http://localhost:8000`

## What I Learned

### Technical Skills
- **Async Python**: Understanding how async/await works in practice, not just in theory
- **API Design**: Building RESTful endpoints that are actually useful and well-documented
- **AI Integration**: Working with OpenAI's function calling feature and managing API costs
- **Real-time Data**: Using Firebase for live updates without overwhelming the browser
- **Audio Processing**: Browser APIs for recording and server-side transcription

### Development Process
- **API-First Design**: Building the backend endpoints before implementing the frontend helped me think through the data flow
- **Iterative Problem Solving**: Many features required multiple attempts to get right (especially the audio recording)
- **Cost Management**: Learning to optimize AI API usage through caching and smart request batching

## Areas I Want to Improve

- **Error Handling**: The app could be more robust when API services are down
- **Performance**: Some operations are still slower than I'd like, especially when processing long audio files  
- **Testing**: I focused more on getting features working than writing comprehensive tests
- **User Experience**: The interface is functional but could be more intuitive

## Future Improvements

If I continue working on this project, I'd like to:
- Add automated tests for the core functionality
- Implement proper user management (right now it's pretty basic)
- Add support for multiple pets per user
- Build a mobile-friendly version of the interface
- Add integration with actual veterinary systems

This project taught me a lot about building full-stack applications with AI services, and I feel much more confident working with APIs and async programming than when I started.