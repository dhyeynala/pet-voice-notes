# 🐾 PetPages - AI-Powered Pet Health Tracking

> "Why should humans have all the smart health tech?"  
> This project brings **AI-powered health tracking** to pets — featuring real-time voice notes, document uploads, and personalized medical summaries.

---

## 🐾 Introduction

**PetPages** is an advanced pet health management system that allows pet parents and veterinarians to **record, summarize, and organize pet health updates** using only their voice or PDF documents. With pets unable to speak for themselves, this tool empowers owners to track medical history with ease and confidence.

This application combines **real-time audio processing**, **AI-powered summarization**, **cloud storage**, and **modern web technologies** into a comprehensive pet healthcare solution.

---

## 🎯 The Vision

The goal: make pet healthcare management **as simple as talking**.

**PetPages** allows users to:

- ✅ **Secure Authentication** - Log in seamlessly with Google
- 🐶 **Pet Management** - Create and manage multiple pet profiles
- 🎙️ **Voice Recording** - Record voice notes with manual start/stop controls
- 🤖 **AI Transcription** - Automatically transcribe speech using Google Cloud Speech-to-Text
- 📝 **Smart Summarization** - Generate medical summaries using OpenAI GPT-4o
- 📄 **PDF Processing** - Upload and analyze veterinary documents
- ☁️ **Cloud Storage** - Secure storage with Firebase Firestore and Storage
- 👥 **Collaboration** - Share pet pages with family members and veterinarians
- 📱 **Modern UI** - Beautiful, responsive interface with real-time feedback

---

## ⚙️ Tech Stack

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

## 🏗️ System Architecture

### **Backend API Endpoints**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/start_recording` | POST | Start voice recording session |
| `/api/stop_recording` | POST | Stop recording and process transcript |
| `/api/recording_status` | GET | Get current recording status |
| `/api/upload_pdf` | POST | Upload and analyze PDF documents |
| `/api/user-pets/{user_id}` | GET | Retrieve user's pet list |
| `/api/pets/{user_id}` | POST | Create new pet profile |
| `/api/pages/{page_id}` | GET/POST | Manage shared page notes |
| `/api/pets/{pet_id}/textinput` | POST | Add text-based pet notes |

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
          └── textinput/
              └── {inputId}
                  ├── input: "Manual note about behavior"
                  └── timestamp: "2025-06-27T..."
```

---

## 🎙️ Voice Recording Features

### **Manual Start/Stop Control**
- **User-Controlled Recording**: Click to start, click to stop
- **Real-Time Feedback**: Visual indicators during recording
- **Background Processing**: Audio transcription happens in real-time
- **Smart Summarization**: AI generates medical summaries automatically

### **Technical Implementation**
```python
# Real-time audio capture with PyAudio
def callback(in_data, frame_count, time_info, status):
    if recording_state["is_recording"]:
        audio_queue.put(in_data)
    return (None, pyaudio.paContinue)

# Google Cloud Speech-to-Text streaming
def transcription_worker():
    client = speech.SpeechClient()
    responses = client.streaming_recognize(streaming_config, requests)
    # Process real-time transcription results
```

---

## 📄 PDF Processing Pipeline

1. **Upload**: Secure file upload to Firebase Storage
2. **Text Extraction**: PyMuPDF extracts text content
3. **AI Analysis**: GPT-4o summarizes medical information
4. **Storage**: Summary and file URL saved to Firestore
5. **Access**: Searchable medical document history

```python
def extract_text_and_summarize(file_path, user_id, pet_id, file_name, file_url):
    # Extract PDF text
    doc = fitz.open(file_path)
    text = "\n".join([page.get_text() for page in doc])
    
    # AI summarization
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "system",
            "content": "You are a veterinary assistant AI. Summarize this medical document..."
        }]
    )
```

---

## 🎨 Modern UI/UX Features

### **Responsive Design**
- **Mobile-First**: Optimized for phones and tablets
- **Progressive Enhancement**: Works across all devices
- **Accessibility**: Proper focus states and keyboard navigation

### **Interactive Elements**
- **Real-Time Status**: Recording indicators and progress feedback
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

## 🔧 Installation & Setup

### **Prerequisites**
```bash
# Python 3.8+
pip install -r requirements.txt

# Google Cloud credentials
export GOOGLE_APPLICATION_CREDENTIALS="gcloud-key.json"

# Environment variables
OPENAI_API_KEY=your_openai_key
FIREBASE_STORAGE_BUCKET=your_firebase_bucket
```

### **Run the Application**
```bash
# Start the server
python -m uvicorn api_server:app --reload

# Access the application
open http://localhost:8000
```

---

## 🧠 Key Technical Achievements

### **Real-Time Audio Processing**
- ✅ Streaming audio capture with PyAudio
- ✅ Google Cloud Speech-to-Text integration
- ✅ Manual start/stop recording controls
- ✅ Background transcription processing

### **AI-Powered Analysis**
- ✅ OpenAI GPT-4o integration for summarization
- ✅ Veterinary-specific prompt engineering
- ✅ Retry logic and error handling
- ✅ Context-aware medical summaries

### **Cloud Architecture**
- ✅ Firebase Authentication with Google Sign-In
- ✅ Firestore NoSQL database design
- ✅ Firebase Storage for file management
- ✅ Scalable multi-user architecture

### **Modern Web Development**
- ✅ FastAPI for high-performance APIs
- ✅ Responsive CSS Grid and Flexbox
- ✅ ES6+ JavaScript modules
- ✅ Progressive Web App features

---

## 🚀 Future Enhancements

### **Advanced AI Features**
- 🔮 **RAG-Based Health Assistant**: Query pet's health history with natural language
- 📊 **Health Trend Analysis**: AI-powered insights from historical data
- 🔍 **Symptom Recognition**: Pattern detection in voice notes
- 📱 **Mobile App**: Native iOS/Android applications

### **Collaboration Tools**
- 👥 **Veterinarian Portal**: Professional dashboard for vets
- 📧 **Smart Notifications**: Email/SMS alerts for health concerns
- 📅 **Appointment Integration**: Calendar sync with vet appointments
- 🔗 **Clinic Integration**: Direct sharing with veterinary practices

### **Data & Analytics**
- 📈 **Health Timeline**: Visual pet health journey
- 📊 **Analytics Dashboard**: Health metrics and trends
- 📋 **Report Generation**: Automated health reports
- 🔒 **Data Export**: HIPAA-compliant data portability

---

## 🏆 Impact & Vision

**PetPages** represents the convergence of **AI technology** and **pet healthcare**, creating a solution that:

- **Empowers Pet Owners**: Easy health tracking and documentation
- **Supports Veterinarians**: Comprehensive patient history and insights
- **Improves Pet Health**: Early detection and better care continuity
- **Democratizes Technology**: Bringing enterprise-level AI to pet care

---

## 🤝 Contributing

This project is built with love for our furry friends. Contributions are welcome!

### **Areas for Contribution**
- 🐛 **Bug Fixes**: Help improve stability
- ✨ **Feature Development**: Add new capabilities
- 🎨 **UI/UX Improvements**: Enhance user experience
- 📝 **Documentation**: Improve guides and tutorials
- 🧪 **Testing**: Automated testing and QA

---

## 📞 Connect

If you're passionate about **AI + Pet Healthcare** or want to collaborate:

- **LinkedIn**: [Dhyey Desai](https://www.linkedin.com/in/dhyey-desai-80659a216/)
- **GitHub**: [DHYEY166](https://github.com/DHYEY166)

---

**Made with ❤️ for pets and their humans** 🐾