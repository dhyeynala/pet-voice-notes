# PetPages - AI-Powered Pet Health Tracking

> Comprehensive pet health management through AI-powered voice notes, document analysis, and intelligent health insights.

---

## Introduction

**PetPages** is an advanced pet health management system that enables pet owners and veterinarians to record, summarize, and organize pet health information using voice input or PDF document uploads. This tool empowers owners to maintain comprehensive medical histories with professional-grade documentation and AI-powered insights.

The application integrates real-time audio processing, AI-powered summarization, cloud storage, and modern web technologies into a unified pet healthcare solution.

---

## Core Features

PetPages provides a comprehensive suite of tools for modern pet healthcare management:

- **Secure Authentication** - Google OAuth integration for seamless access control
- **Pet Profile Management** - Create and manage multiple pet profiles with detailed health histories
- **Voice Recording System** - Manual start/stop voice recording with real-time transcription
- **AI Transcription** - Automatic speech-to-text conversion using Google Cloud Speech-to-Text
- **Intelligent Summarization** - AI-generated summaries for both medical concerns and daily activities
- **Health Analytics** - Professional medical analysis for symptoms, treatments, and veterinary visits
- **Activity Tracking** - Comprehensive logging of exercise, training, and behavioral observations
- **Content Classification** - Automatic detection and categorization of medical vs. daily activity content
- **PDF Document Processing** - Upload and analysis of veterinary documents with AI summarization
- **Cloud Storage Integration** - Secure data storage with Firebase Firestore and Cloud Storage
- **Collaboration Tools** - Share pet health information with family members and veterinarians
- **Responsive Interface** - Modern, mobile-first design with unified navigation and real-time feedback
- **Advanced Analytics Dashboard** - Interactive charts and visualizations for health tracking
- **AI Health Insights** - Personalized recommendations and pattern recognition

---

## Technology Stack

| Component            | Technology                                |
|---------------------|-------------------------------------------|
| **Frontend**        | HTML5, JavaScript ES6+, CSS3             |
| **Backend**         | FastAPI (Python) + REST API              |
| **Authentication**  | Firebase Auth with Google Sign-In        |
| **Voice Processing** | Google Cloud Speech-to-Text API          |
| **AI Summarization** | OpenAI GPT-4o via latest SDK            |
| **PDF Processing**  | PyMuPDF (fitz) for text extraction       |
| **Database**        | Firebase Firestore (NoSQL)               |
| **File Storage**    | Firebase Cloud Storage                    |
| **Audio Processing** | PyAudio for real-time audio capture     |
| **Deployment**      | Uvicorn ASGI server                       |

---

## System Architecture

### **Backend API Endpoints**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/start_recording` | POST | Start voice recording session |
| `/api/stop_recording` | POST | Stop recording and process transcript |
| `/api/recording_status` | GET | Get current recording status |
| `/api/upload_pdf` | POST | Upload and analyze PDF documents |
| `/api/user-pets/{user_id}` | GET | Retrieve user's pet list |
| `/api/pets/{user_id}` | POST | Create new pet profile |
| `/api/pets/{pet_id}/textinput` | POST | Add text-based pet notes with AI classification |
| `/api/pets/{pet_id}/analytics/{category}` | POST | Add health tracking data by category |
| `/api/pets/{pet_id}/analytics` | GET | Retrieve analytics data with filtering |
| `/api/pets/{pet_id}/analytics/summary` | GET | Get summary statistics for all categories |
| `/api/pets/{pet_id}/visualizations` | GET | Get chart data for analytics dashboard |
| `/api/pets/{pet_id}/daily_routine` | POST | Generate AI-powered daily headlines |
| `/api/pets/{pet_id}/health_insights` | GET | Get AI health insights and recommendations |
| `/api/pages/{page_id}` | GET/POST | Manage shared page notes |
| `/api/markdown` | GET/POST | Handle markdown content for notes |

### **Data Architecture (Firestore)**

```plaintext
users/
  └── {userId}/
      ├── email: "user@example.com"
      ├── pages: [pageId, ...]
      └── pets: [petId, ...]

pages/
  └── {pageId}/
      ├── authorizedUsers: [userId, ...]
      ├── pets: [petId, ...]
      └── markdown: "Shared notes..."

pets/
  └── {petId}/
      ├── name: "Buddy"
      └── subcollections:
          ├── voice-notes/
          │   └── {noteId}
          │       ├── transcript: "Dog was limping today..."
          │       ├── summary: "Possible leg injury, monitor closely"
          │       └── timestamp: "2025-06-27T..."
          ├── records/
          │   └── {recordId}
          │       ├── summary: "Blood work shows normal values"
          │       ├── file_url: "https://storage.googleapis.com/..."
          │       ├── file_name: "blood_work_results.pdf"
          │       └── timestamp: "2025-06-27T..."
          ├── textinput/
          │   └── {inputId}
          │       ├── input: "Manual note about behavior"
          │       ├── summary: "AI-generated summary"
          │       ├── content_type: "DAILY_ACTIVITY" | "MEDICAL" | "MIXED"
          │       ├── confidence: 0.85
          │       ├── keywords: ["keyword1", "keyword2"]
          │       └── timestamp: "2025-06-27T..."
          └── analytics/
              └── {analyticsId}
                  ├── category: "diet" | "exercise" | "medication" | "grooming" | 
                  │             "energy_levels" | "bowel_movements" | "exit_events" |
                  │             "weight" | "temperature" | "mood" | "sleep" | "water_intake"
                  ├── source: "manual_entry" | "voice_input" | "text_input"
                  ├── timestamp: "2025-06-27T..."
                  ├── [category-specific fields]:
                  │   ├── diet: {food, quantity, time, type, notes}
                  │   ├── exercise: {type, duration, intensity, location, notes}
                  │   ├── medication: {name, dosage, time, frequency, purpose}
                  │   ├── energy_levels: {level: 1-5, notes}
                  │   ├── mood: {level: 1-5, triggers[], behavior[], notes}
                  │   ├── weight: {value, unit, method, notes}
                  │   └── sleep: {duration, quality, location, interruptions, notes}
                  └── notes: "Additional observations"
```

---

## Health Analytics & Tracking

### **Comprehensive Health Monitoring**
PetPages includes a robust analytics system for tracking various aspects of pet health and behavior:

- **Diet & Nutrition**: Track food types, quantities, meal timing, and dietary habits
- **Exercise & Activity**: Monitor exercise duration, intensity, types, and location data
- **Medication Management**: Log medications, dosages, frequencies, and compliance
- **Energy Levels**: Record daily energy levels on a 1-5 scale with contextual notes
- **Mood & Behavior**: Track behavioral patterns, triggers, and emotional states
- **Sleep Monitoring**: Record sleep duration, quality, location, and disturbances
- **Grooming & Hygiene**: Log grooming activities, products used, and pet cooperation
- **Weight Tracking**: Monitor weight changes with various measurement methods
- **Bowel Movement Tracking**: Record consistency, timing, and patterns
- **Exit Events**: Track outdoor activities, destinations, and duration

### **AI-Powered Insights**
- **Daily Headlines**: AI-generated summaries of daily activities and achievements
- **Health Recommendations**: Personalized suggestions based on tracking data
- **Pattern Recognition**: Automatic detection of health trends and anomalies
- **Veterinary Reports**: Professional summaries for veterinary consultations
- **Content Classification**: Automatic categorization of medical vs. daily activity content

### **Data Visualization**
- **Interactive Charts**: Weekly activity trends, energy level distributions, diet frequency
- **Health Dashboards**: Overview metrics with real-time updates
- **Progress Tracking**: Visual representation of health improvements over time
- **Comparative Analysis**: Compare current metrics with historical baselines

---

## Voice Recording Features

### **Manual Start/Stop Control**
- **User-Controlled Recording**: Click to start, click to stop
- **Real-Time Feedback**: Visual indicators during recording
- **Background Processing**: Audio transcription happens in real-time
- **Smart Summarization**: AI generates context-aware summaries for both medical concerns and daily activities
- **Intelligent Classification**: Automatically detects content type (Medical, Daily Activity, or Mixed)
- **Adaptive Tone**: Professional tone for health concerns, encouraging tone for daily celebrations

### **Technical Implementation**
```python
# Enhanced Google Cloud authentication setup
def setup_google_cloud_auth():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "project_name")
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "gcloud-key.json")
    
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
    
    return speech.SpeechClient()

# Real-time audio capture with manual controls
def start_recording():
    recording_state["is_recording"] = True
    recording_thread = threading.Thread(target=_record_audio)
    recording_thread.daemon = True
    recording_thread.start()
    return {"status": "recording", "message": "Recording started"}

def stop_recording():
    recording_state["is_recording"] = False
    audio_data = b''.join(recording_state["audio_data"])
    transcript = _transcribe_audio_data(audio_data)
    return {"status": "stopped", "transcript": transcript}
```

---

## PDF Processing Pipeline

1. **Upload**: Secure file upload to Firebase Storage with drag-and-drop support
2. **Text Extraction**: PyMuPDF extracts text content from medical documents
3. **AI Analysis**: GPT-4o analyzes and summarizes medical information with veterinary context
4. **Storage**: Summary and file URL saved to Firestore with proper document structure
5. **Access**: Searchable medical document history with unified interface

```python
def extract_text_and_summarize(file_path, user_id, pet_id, file_name, file_url):
    # Extract PDF text with error handling
    try:
        doc = fitz.open(file_path)
        text = "\n".join([page.get_text() for page in doc])
        doc.close()
    except Exception as e:
        return {"error": f"PDF extraction failed: {str(e)}"}
    
    # AI summarization with veterinary context
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "system",
            "content": "You are a veterinary assistant AI. Analyze this medical document and provide a concise, professional summary focusing on key health indicators, treatments, and recommendations..."
        }, {
            "role": "user", 
            "content": f"Please summarize this veterinary document:\n\n{text}"
        }]
    )
    
    # Store with proper document structure
    store_pdf_summary(user_id, pet_id, summary, timestamp, file_name, file_url)
```

---

## Modern UI/UX Features

### **Responsive Design**
- **Mobile-First**: Optimized for phones and tablets
- **Progressive Enhancement**: Works across all devices  
- **Unified Navigation**: Single-page interface with seamless tabbed navigation between Voice Recording and Notes & Files
- **Accessibility**: Proper focus states and keyboard navigation

### **Interactive Elements**
- **Real-Time Status**: Recording indicators and progress feedback
- **Unified Navigation Tabs**: Seamless switching between Voice Recording and Notes & Files sections
- **URL Fragment Support**: Direct navigation with URLs like `/main.html#notes` or `/main.html#recording`
- **Drag & Drop**: PDF upload with visual feedback
- **Smooth Animations**: CSS transitions and loading states
- **Error Handling**: User-friendly error messages

### **Design System**
```css
:root {
  --primary-color: #667eea;
  --secondary-color: #4ecdc4;
  --success-color: #38a169;
  --error-color: #e53e3e;
  --font-family: 'Inter', sans-serif;
}
```

---

## Installation & Setup

### **Prerequisites**
```bash
# Python 3.8+
pip install -r requirements.txt
```

### Environment Setup

**Security Important**: Copy `.env.example` to `.env` and fill in your actual API keys. Never commit `.env` to version control!

```bash
# Copy the template and edit with your keys
cp .env.example .env
# Edit .env with your actual API keys
```

Required environment variables in `.env`:
```bash
# OpenAI API Key - Get from https://platform.openai.com/api-keys
OPENAI_API_KEY=your_actual_openai_api_key_here

# Firebase Configuration  
FIREBASE_STORAGE_BUCKET=
GOOGLE_CLOUD_PROJECT=

# Google Cloud Service Account JSON file path
GOOGLE_APPLICATION_CREDENTIALS=gcloud-key.json
```

**Security Note**: See `SECURITY.md` for detailed security guidelines and key rotation procedures.

### Google Cloud APIs Setup
Enable the following APIs in Google Cloud Console for this project:

1. **Cloud Speech-to-Text API** (Required for voice transcription)
2. **Firebase Authentication API** (Required for Google Sign-In)
3. **Cloud Storage API** (Required for file uploads)
4. **Cloud Firestore API** (Required for database)
5. **Cloud Resource Manager API** (Required for project management)

### Firebase Configuration
Ensure your `gcloud-key.json` service account file is in the project root with proper permissions for:
- Firestore Database User
- Storage Admin
- Speech API User

### Run the Application
```bash
# Start the server
python -m uvicorn api_server:app --reload

# Access the application
open http://localhost:8000/main.html
```

### Application URLs
- **Main Dashboard**: `http://localhost:8000/main.html`
- **Voice Recording**: `http://localhost:8000/main.html#recording`
- **Notes & Files**: `http://localhost:8000/main.html#notes`
- **Login Page**: `http://localhost:8000/index.html`

---

## Key Technical Achievements

### Real-Time Audio Processing
- Manual start/stop recording controls with visual feedback
- Google Cloud Speech-to-Text integration with proper authentication
- Background audio processing with PyAudio
- Optimized audio configuration (16kHz, 16-bit, mono)

### AI-Powered Analysis
- OpenAI GPT-4o integration for medical summarization
- Veterinary-specific prompt engineering for accurate health insights
- Retry logic and comprehensive error handling
- Context-aware medical summaries from voice and PDF content

### Cloud Architecture
- Firebase Authentication with Google Sign-In
- Firestore NoSQL database with optimized document structure
- Firebase Storage for secure file management
- Scalable multi-user architecture with proper permissions

### Modern Web Development
- **Unified Single-Page Application**: Tabbed navigation between Voice Recording and Notes & Files
- **URL Fragment Support**: Direct navigation with bookmarkable URLs (`#recording`, `#notes`)
- **Responsive Design**: Mobile-first approach with CSS Grid and Flexbox
- **Progressive Enhancement**: Works across all devices and browsers
- **Real-Time Feedback**: Loading states, progress indicators, and status messages

### Authentication & Security
- Google Cloud service account authentication with quota project configuration
- Environment-based configuration for secure credential management
- Proper API key management and rate limiting
- User session management with Firebase Auth

---

## Future Enhancements

### Advanced AI Features
- **RAG-Based Health Assistant**: Query pet's health history with natural language
- **Health Trend Analysis**: AI-powered insights from historical voice notes and documents
- **Symptom Pattern Recognition**: Automatic detection of recurring health issues
- **Mobile App**: Native iOS/Android applications with offline voice recording

### Enhanced User Experience
- **Voice Commands**: Navigate the app using voice controls
- **Smart Templates**: Pre-filled forms for common health situations
- **Smart Notifications**: AI-driven health reminders and alerts
- **Customizable Dashboard**: Personalized interface for different user types

### Collaboration & Integration
- **Veterinarian Portal**: Professional dashboard with advanced analytics
- **Smart Notifications**: Email/SMS alerts for health concerns with severity detection
- **Appointment Integration**: Calendar sync with vet appointments and medication schedules
- **Clinic Integration**: Direct sharing with veterinary practices and HIPAA compliance

### Data & Analytics
- **Interactive Health Timeline**: Visual pet health journey with clickable events
- **Advanced Analytics Dashboard**: Health metrics, trends, and predictive insights
- **Automated Report Generation**: Professional health reports for veterinary visits
- **Enhanced Data Security**: End-to-end encryption and HIPAA-compliant data export

---

## Impact & Vision

**PetPages** represents the convergence of **AI technology** and **pet healthcare**, creating a solution that:

- **Empowers Pet Owners**: Easy health tracking and documentation
- **Supports Veterinarians**: Comprehensive patient history and insights
- **Improves Pet Health**: Early detection and better care continuity
- **Democratizes Technology**: Bringing enterprise-level AI to pet care

---

## Contributing

This project is built with dedication to improving pet healthcare. Contributions are welcome!

### Areas for Contribution
- **Bug Fixes**: Help improve stability and performance
- **Feature Development**: Add new capabilities and functionality
- **UI/UX Improvements**: Enhance user experience and accessibility
- **Documentation**: Improve guides and tutorials
- **Testing**: Automated testing and quality assurance

---

## Connect

If you're passionate about **AI + Pet Healthcare** or want to collaborate:

- **LinkedIn**: [Dhyey Desai](https://www.linkedin.com/in/dhyey-desai-80659a216/)
- **GitHub**: [DHYEY166](https://github.com/DHYEY166)

---

**Made with care for pets and their humans**