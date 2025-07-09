# 🐾 PetPages - AI-Powered Pet Health Tracking

> "Why should humans have all the smart health tech?"  
> This project brings **AI-powered health tracking** to pets — featuring real-time voice notes, document uploads, and personalized medical summaries.

## 🔐 Security Notice

**⚠️ IMPORTANT**: This project uses API keys and credentials that must be kept secure. Please read [SECURITY.md](./SECURITY.md) for complete setup instructions before running the application.

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
- 📱 **Modern UI** - Beautiful, responsive interface with unified navigation and real-time feedback

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
# Enhanced Google Cloud authentication setup
def setup_google_cloud_auth():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "puppypages-29427")
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

## 📄 PDF Processing Pipeline

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

## 🎨 Modern UI/UX Features

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

## 🔧 Installation & Setup

### **Prerequisites**
```bash
# Python 3.8+
pip install -r requirements.txt
```

### **Environment Setup**
Create a `.env` file in the project root:
```bash
# .env file
OPENAI_API_KEY=your_openai_api_key_here
FIREBASE_STORAGE_BUCKET=puppypages-29427.appspot.com
GOOGLE_CLOUD_PROJECT=puppypages-29427
GOOGLE_APPLICATION_CREDENTIALS=gcloud-key.json
```

### **Google Cloud APIs Setup**
Enable the following APIs in Google Cloud Console for project `puppypages-29427`:

1. **🎙️ Cloud Speech-to-Text API** (Required for voice transcription)
2. **🔥 Firebase Authentication API** (Required for Google Sign-In)
3. **📁 Cloud Storage API** (Required for file uploads)
4. **🗄️ Cloud Firestore API** (Required for database)
5. **📊 Cloud Resource Manager API** (Required for project management)

Direct links:
- [Enable Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com?project=puppypages-29427)
- [Enable Firebase Auth API](https://console.cloud.google.com/apis/library/identitytoolkit.googleapis.com?project=puppypages-29427)
- [View All APIs](https://console.cloud.google.com/apis/dashboard?project=puppypages-29427)

### **Firebase Configuration**
Ensure your `gcloud-key.json` service account file is in the project root with proper permissions for:
- Firestore Database User
- Storage Admin
- Speech API User

### **Run the Application**
```bash
# Start the server
python -m uvicorn api_server:app --reload

# Access the application
open http://localhost:8000/main.html
```

### **Application URLs**
- **Main Dashboard**: `http://localhost:8000/main.html`
- **Voice Recording**: `http://localhost:8000/main.html#recording`
- **Notes & Files**: `http://localhost:8000/main.html#notes`
- **Login Page**: `http://localhost:8000/index.html`

---

## 🔧 Troubleshooting

### **Common Issues & Solutions**

#### **Google Cloud Authentication Warnings**
```
WARNING: Your application has authenticated using end user credentials from Google Cloud SDK without a quota project.
```
**Solution**: Ensure your `.env` file contains:
```bash
GOOGLE_CLOUD_PROJECT=puppypages-29427
GOOGLE_APPLICATION_CREDENTIALS=gcloud-key.json
```

#### **Speech-to-Text API Errors**
- **Issue**: API not enabled
- **Solution**: Enable the [Cloud Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com?project=puppypages-29427)
- **Verify**: Run `python gcloud_auth.py` to test authentication

#### **Recording Not Working**
- **Check microphone permissions** in your browser
- **Verify PyAudio installation**: `pip install pyaudio`
- **Test audio capture**: Ensure microphone is not being used by other applications

#### **PDF Upload Failures**
- **File size limit**: Max 10MB per PDF
- **File format**: Only PDF files are supported
- **Storage permissions**: Verify Firebase Storage rules allow uploads

#### **Firebase Connection Issues**
- **Check internet connection**
- **Verify Firebase configuration** in `public/firebase-config.js`
- **Ensure billing is enabled** in Google Cloud Console

### **Development Tips**
- **Use browser developer tools** to debug JavaScript errors
- **Check FastAPI logs** for backend error details
- **Monitor Google Cloud Console** for API quota usage
- **Test with different browsers** for compatibility issues

---

## 🧠 Key Technical Achievements

### **Real-Time Audio Processing**
- ✅ Manual start/stop recording controls with visual feedback
- ✅ Google Cloud Speech-to-Text integration with proper authentication
- ✅ Background audio processing with PyAudio
- ✅ Optimized audio configuration (16kHz, 16-bit, mono)

### **AI-Powered Analysis**
- ✅ OpenAI GPT-4o integration for medical summarization
- ✅ Veterinary-specific prompt engineering for accurate health insights
- ✅ Retry logic and comprehensive error handling
- ✅ Context-aware medical summaries from voice and PDF content

### **Cloud Architecture**
- ✅ Firebase Authentication with Google Sign-In
- ✅ Firestore NoSQL database with optimized document structure
- ✅ Firebase Storage for secure file management
- ✅ Scalable multi-user architecture with proper permissions

### **Modern Web Development**
- ✅ **Unified Single-Page Application**: Tabbed navigation between Voice Recording and Notes & Files
- ✅ **URL Fragment Support**: Direct navigation with bookmarkable URLs (`#recording`, `#notes`)
- ✅ **Responsive Design**: Mobile-first approach with CSS Grid and Flexbox
- ✅ **Progressive Enhancement**: Works across all devices and browsers
- ✅ **Real-Time Feedback**: Loading states, progress indicators, and status messages

### **Authentication & Security**
- ✅ Google Cloud service account authentication with quota project configuration
- ✅ Environment-based configuration for secure credential management
- ✅ Proper API key management and rate limiting
- ✅ User session management with Firebase Auth

---

## 🚀 Future Enhancements

### **Advanced AI Features**
- 🔮 **RAG-Based Health Assistant**: Query pet's health history with natural language
- 📊 **Health Trend Analysis**: AI-powered insights from historical voice notes and documents
- 🔍 **Symptom Pattern Recognition**: Automatic detection of recurring health issues
- 📱 **Mobile App**: Native iOS/Android applications with offline voice recording

### **Enhanced User Experience**
- 🎙️ **Voice Commands**: Navigate the app using voice controls
- 📋 **Smart Templates**: Pre-filled forms for common health situations
- 🔔 **Smart Notifications**: AI-driven health reminders and alerts
- 🎨 **Customizable Dashboard**: Personalized interface for different user types

### **Collaboration & Integration**
- 👥 **Veterinarian Portal**: Professional dashboard with advanced analytics
- 📧 **Smart Notifications**: Email/SMS alerts for health concerns with severity detection
- 📅 **Appointment Integration**: Calendar sync with vet appointments and medication schedules
- 🔗 **Clinic Integration**: Direct sharing with veterinary practices and HIPAA compliance

### **Data & Analytics**
- 📈 **Interactive Health Timeline**: Visual pet health journey with clickable events
- 📊 **Advanced Analytics Dashboard**: Health metrics, trends, and predictive insights
- 📋 **Automated Report Generation**: Professional health reports for veterinary visits
- 🔒 **Enhanced Data Security**: End-to-end encryption and HIPAA-compliant data export

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