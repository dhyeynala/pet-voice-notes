# Security Guidelines for PetPulse

## Important Security Notice

This project uses sensitive API keys and credentials that must be protected.

### API Keys Used

#### OpenAI API Key
- **Purpose**: Note extraction, chat answers, PDF summaries, voice note transcription
- **Used in**: `petpulse/providers/llm.py` (via `petpulse/llm/client.py`), `petpulse/providers/stt.py` (`OpenAISTT`)
- **Environment Variable**: `OPENAI_API_KEY`

#### Google Cloud Credentials
- **Purpose**: Speech-to-Text (optional, `STT_PROVIDER=google`); optional Firebase mode (Firestore, Cloud Storage, sign-in)
- **Used in**: `petpulse/providers/stt.py` (`GoogleSTT`, via `GOOGLE_APPLICATION_CREDENTIALS`), `petpulse/core/firebase.py` and `petpulse/store/firestore.py` (via `FIREBASE_CREDENTIALS_JSON`, see [docs/firebase.md](docs/firebase.md))
- **Files**: `gcloud-key.json`, environment variables

### Security Measures Implemented

1. **Environment Variables**: All sensitive keys are stored in `.env` file
2. **Git Ignore**: `.env` and `gcloud-key.json` are excluded from version control
3. **Template File**: `.env.example` provides setup instructions without exposing keys
4. **Documentation**: This file documents security practices

### Key Rotation Recommendations

#### For OpenAI API Key:
1. Visit [OpenAI API Keys Dashboard](https://platform.openai.com/api-keys)
2. Create a new API key
3. Update your `.env` file with the new key
4. Delete the old key from OpenAI dashboard

#### For Google Cloud Service Account:
1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Go to IAM & Admin > Service Accounts
3. Create new key for existing service account
4. Replace `gcloud-key.json` with new file
5. Delete old key from console

### Production Deployment

For production environments:
- Use environment variables instead of `.env` files
- Use secret management services (AWS Secrets Manager, Azure Key Vault, etc.)
- Enable API key restrictions and rate limiting
- Monitor API usage for unusual activity

### Setup Checklist

- [ ] `.env` file is not committed to git
- [ ] `gcloud-key.json` is not committed to git
- [ ] All API keys are valid and working
- [ ] Team members have their own API keys (don't share)
- [ ] API keys have appropriate permissions only

### If Keys Are Compromised

1. **Immediately rotate all exposed keys**
2. **Check API usage logs for unauthorized activity**
3. **Update all deployment environments**
4. **Review git history to ensure keys weren't committed**
