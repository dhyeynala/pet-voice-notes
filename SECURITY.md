# 🔐 Security Setup Instructions

## ⚠️ IMPORTANT: API Keys and Credentials

This project uses sensitive API keys and credentials that **MUST NOT** be committed to version control.

### 🛡️ Protected Files

The following files contain sensitive information and are protected by `.gitignore`:

- `.env` - Environment variables with API keys
- `gcloud-key.json` - Google Cloud service account credentials
- Any files ending in `-key.json` or containing credentials

### 🚀 Initial Setup

1. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Add your actual API keys to `.env`:**
   - Get your OpenAI API key from: https://platform.openai.com/api-keys
   - Get your Google Cloud credentials from: https://console.cloud.google.com/
   - Update the `.env` file with your actual values

3. **Place your Google Cloud service account key:**
   - Download your service account JSON key from Google Cloud Console
   - Save it as `gcloud-key.json` in the project root
   - Make sure this filename matches `GOOGLE_APPLICATION_CREDENTIALS` in your `.env`

### 🔒 Security Checklist

- [ ] `.env` file is in `.gitignore`
- [ ] `gcloud-key.json` is in `.gitignore`
- [ ] No API keys are hardcoded in source files
- [ ] Environment variables are used for all sensitive data
- [ ] `.env.example` shows required variables without actual values

### 🚨 If You Accidentally Commit Secrets

If you accidentally commit API keys or credentials:

1. **Immediately rotate/regenerate** all exposed keys
2. **Remove the file from git history:**
   ```bash
   git filter-branch --force --index-filter 'git rm --cached --ignore-unmatch path/to/secret/file' --prune-empty --tag-name-filter cat -- --all
   ```
3. **Force push** to overwrite the remote history
4. **Notify team members** to re-clone the repository

### 📋 Required Environment Variables

```bash
# OpenAI API for AI insights and summaries
OPENAI_API_KEY=sk-proj-your_key_here

# Google Cloud & Firebase configuration
GOOGLE_CLOUD_PROJECT=your_project_id
GOOGLE_APPLICATION_CREDENTIALS=./gcloud-key.json
FIREBASE_STORAGE_BUCKET=your_project.appspot.com

# Firebase Client Configuration (these can be public)
FIREBASE_API_KEY=your_firebase_web_api_key
FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
FIREBASE_DATABASE_URL=https://your_project.firebaseio.com
FIREBASE_PROJECT_ID=your_project_id
FIREBASE_STORAGE_BUCKET=your_project.appspot.com
FIREBASE_MESSAGING_SENDER_ID=your_sender_id
FIREBASE_APP_ID=your_app_id
FIREBASE_MEASUREMENT_ID=your_measurement_id
```

### 🔍 Firebase Client API Key - Security Note

The Firebase Web API key in `firebase-config.js` is **designed to be public** and is not a security risk when properly configured. This key:

- ✅ Is meant to be included in client-side code
- ✅ Only identifies your Firebase project
- ✅ Security is enforced by Firebase Security Rules, not by hiding the API key

However, ensure your Firebase Security Rules are properly configured to restrict access.

### 🔧 Development vs Production

- **Development**: Use `.env` file for local development
- **Production**: Set environment variables directly in your hosting platform
- **Never** include actual credentials in Docker images or deployment scripts

---

## 🚀 Running the Application

After setting up your credentials:

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
python -m uvicorn api_server:app --reload
```

The application will read credentials from your `.env` file automatically.
