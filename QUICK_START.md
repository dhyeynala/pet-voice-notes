# PetPulse Quick Start Guide

Get PetPulse running in minutes! Choose your preferred setup method:

## Prerequisites

Before starting, you'll need:
- **Python 3.8+** installed
- **Git** installed
- **API Keys** (see setup instructions below)

## Method 1: Automated Setup (Recommended)

### 1. Clone and Setup
```bash
git clone <your-repo-url>
cd petpulse
python setup.py
```

### 2. Follow the Interactive Setup
The setup script will guide you through:
- Environment configuration
- Firebase setup
- Dependency installation
- Google Cloud instructions

### 3. Complete Google Cloud Setup
Follow the instructions provided by the setup script for Google Cloud configuration.

### 4. Run the Application
```bash
python api_server.py
```

## Method 2: Docker Setup

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd petpulse
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
# Build and run with Docker Compose (recommended)
docker-compose up --build

# Or run with Docker directly
docker build -t petpulse .
docker run -p 8000:8000 --env-file .env petpulse
```

## Method 3: Manual Setup

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd petpulse
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

## Access the Application

Once running, open your browser to:
- **Main Application**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Alternative API Docs**: http://localhost:8000/redoc

## Required API Keys

### 1. OpenAI API Key
- **Get from**: https://platform.openai.com/api-keys
- **Required for**: AI assistant, voice transcription, analytics
- **Features**: GPT-4 function calling, text summarization, content classification

### 2. Google Cloud Project
- **Get from**: https://console.cloud.google.com/
- **Required for**: Speech-to-Text, Firebase, Storage
- **Cost**: Free tier available (sufficient for development)

### 3. Firebase Project
- **Get from**: https://console.firebase.google.com/
- **Required for**: Database, Authentication, Storage
- **Features**: Real-time database, user authentication, file storage

### 4. Dog/Cat API Keys (Optional)
- **Dog API**: https://thedogapi.com/ (free registration)
- **Cat API**: https://thecatapi.com/ (free registration)
- **Required for**: Breed-specific AI recommendations and insights

## Troubleshooting

### Common Issues

#### 1. "Module not found" errors
```bash
# Ensure all dependencies are installed
pip install -r requirements.txt

# For development dependencies
pip install -r requirements-dev.txt
```

#### 2. "Google Cloud authentication failed"
- Ensure `gcloud-key.json` is in project root
- Check Google Cloud project ID in `.env`
- Verify APIs are enabled in Google Cloud Console:
  - Cloud Speech-to-Text API
  - Firebase Admin SDK
  - Cloud Storage API

#### 3. "Firebase connection failed"
- Check Firebase config in `public/firebase-config.js`
- Verify Firebase project is set up correctly
- Ensure Firestore and Storage are enabled
- Check Firebase Rules configuration

#### 4. "OpenAI API key invalid"
- Check your API key in `.env`
- Verify you have credits in your OpenAI account
- Ensure the key has proper permissions for GPT-4

#### 5. Port already in use
```bash
# Check what's using port 8000
lsof -i :8000

# Use different port
uvicorn api_server:app --port 8001
```

#### 6. Docker issues
```bash
# Clear Docker cache
docker system prune

# Rebuild without cache
docker-compose build --no-cache
```

## Security Best Practices

- **Never commit** `.env` file or `gcloud-key.json` to version control
- **Rotate API keys** regularly for security
- **Restrict Firebase API keys** to your domain in production
- **Use environment variables** for all sensitive configuration
- **Enable Firebase Security Rules** for production deployment

## Performance Optimization

### Development Mode
- Use the caching system by preloading pet data
- Monitor API response times in browser developer tools
- Check cache status via `/api/pets/{pet_id}/cache/status`

### Production Deployment
- Use Docker for consistent deployment
- Configure environment variables properly
- Set up monitoring and logging
- Consider using a reverse proxy (nginx) for static files

## Next Steps

- **Read the full [README.md](README.md)** for detailed technical architecture
- **Review [SECURITY.md](SECURITY.md)** for security best practices
- **Check [CONTRIBUTING.md](CONTRIBUTING.md)** if you want to contribute
- **Explore the API** at http://localhost:8000/docs

## Need Help?

- **Documentation**: Check the [README.md](README.md) for detailed information
- **Issues**: Search existing issues on GitHub before creating new ones
- **Bugs**: Create a detailed bug report with reproduction steps
- **Features**: Submit feature requests with clear use cases
- **Support**: Contact maintainers for technical assistance

---

**Start building AI-powered pet health management solutions with PetPulse!**