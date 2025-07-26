# 🚀 PetPages Quick Start Guide

Get PetPages running in minutes! Choose your preferred setup method:

## 📋 Prerequisites

Before starting, you'll need:
- **Python 3.8+** installed
- **Git** installed
- **API Keys** (see setup instructions below)

## 🎯 Method 1: Automated Setup (Recommended)

### 1. Clone and Setup
```bash
git clone <your-repo-url>
cd final_github
python setup.py
```

### 2. Follow the Interactive Setup
The setup script will guide you through:
- ✅ Environment configuration
- ✅ Firebase setup
- ✅ Dependency installation
- ✅ Google Cloud instructions

### 3. Complete Google Cloud Setup
Follow the instructions in `GOOGLE_CLOUD_SETUP.md`

### 4. Run the Application
```bash
python api_server.py
```

## 🐳 Method 2: Docker Setup

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd final_github
```

### 2. Configure Environment
```bash
# Copy and edit environment template
cp .env.template .env
# Edit .env with your API keys
```

### 3. Configure Firebase
```bash
# Copy and edit Firebase template
cp public/firebase-config.template.js public/firebase-config.js
# Edit firebase-config.js with your Firebase details
```

### 4. Run with Docker
```bash
# Build and run
docker-compose up --build

# Or run without compose
docker build -t petpages .
docker run -p 8000:8000 --env-file .env petpages
```

## 🔧 Method 3: Manual Setup

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd final_github
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
# Copy template
cp .env.template .env

# Edit .env with your values:
# - OpenAI API Key
# - Google Cloud Project ID
# - Dog/Cat API Keys (optional)
```

### 4. Configure Firebase
```bash
# Copy template
cp public/firebase-config.template.js public/firebase-config.js

# Edit firebase-config.js with your Firebase project details
```

### 5. Setup Google Cloud
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable APIs: Speech-to-Text, Firebase, Storage
4. Create service account and download JSON key
5. Save as `gcloud-key.json` in project root

### 6. Run Application
```bash
python api_server.py
```

## 🌐 Access the Application

Once running, open your browser to:
- **Main Application**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## 📚 Required API Keys

### 1. OpenAI API Key
- **Get from**: https://platform.openai.com/api-keys
- **Required for**: AI assistant, voice transcription, analytics

### 2. Google Cloud Project
- **Get from**: https://console.cloud.google.com/
- **Required for**: Speech-to-Text, Firebase, Storage
- **Cost**: Free tier available

### 3. Firebase Project
- **Get from**: https://console.firebase.google.com/
- **Required for**: Database, Authentication, Storage
- **Cost**: Free tier available

### 4. Dog/Cat API Keys (Optional)
- **Dog API**: https://thedogapi.com/ (free registration)
- **Cat API**: https://thecatapi.com/ (free registration)
- **Required for**: Breed-specific AI recommendations

## 🔍 Troubleshooting

### Common Issues:

#### 1. "Module not found" errors
```bash
pip install -r requirements.txt
```

#### 2. "Google Cloud authentication failed"
- Ensure `gcloud-key.json` is in project root
- Check Google Cloud project ID in `.env`
- Verify APIs are enabled in Google Cloud Console

#### 3. "Firebase connection failed"
- Check Firebase config in `public/firebase-config.js`
- Verify Firebase project is set up correctly
- Ensure Firebase APIs are enabled

#### 4. "OpenAI API key invalid"
- Check your API key in `.env`
- Verify you have credits in your OpenAI account
- Ensure the key has proper permissions

#### 5. Port already in use
```bash
# Use different port
python api_server.py --port 8001
```

## 🛡️ Security Notes

- ✅ Never commit `.env` file to version control
- ✅ Keep API keys secure and rotate regularly
- ✅ Restrict Firebase API key to your domain
- ✅ Use environment variables for all sensitive data

## 📖 Next Steps

- 📚 Read the full [README.md](README.md) for detailed features
- 🔒 Review [SECURITY.md](SECURITY.md) for security best practices
- 🐛 Report issues on GitHub
- 🌟 Star the repository if you find it useful!

## 🆘 Need Help?

- 📖 Check the [README.md](README.md) for detailed documentation
- 🔍 Search existing issues on GitHub
- 💬 Create a new issue for bugs or feature requests
- 📧 Contact the maintainers for support

---

**Happy Pet Health Tracking! 🐾** 