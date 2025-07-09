#!/bin/bash

# setup.sh - Security-focused setup script for PetPages

echo "🔐 PetPages Security Setup"
echo "=========================="

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "📄 Creating .env file from template..."
    cp .env.example .env
    echo "✅ .env file created!"
    echo ""
    echo "⚠️  IMPORTANT: Please edit .env file and add your actual API keys:"
    echo "   - OPENAI_API_KEY"
    echo "   - Google Cloud credentials"
    echo ""
else
    echo "✅ .env file already exists"
fi

# Check if gcloud-key.json exists
if [ ! -f "gcloud-key.json" ]; then
    echo "⚠️  Google Cloud service account key not found!"
    echo "   Please download your service account JSON key from:"
    echo "   https://console.cloud.google.com/iam-admin/serviceaccounts"
    echo "   And save it as 'gcloud-key.json' in this directory"
    echo ""
else
    echo "✅ Google Cloud service account key found"
fi

# Run security audit
echo "🔍 Running security audit..."
python security_audit.py

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 Setup complete! Your project is secure and ready to run."
    echo ""
    echo "📋 Next steps:"
    echo "1. Edit .env with your actual API keys"
    echo "2. Ensure gcloud-key.json is in place"
    echo "3. Run: pip install -r requirements.txt"
    echo "4. Run: python -m uvicorn api_server:app --reload"
else
    echo ""
    echo "🚨 Security issues detected. Please fix them before proceeding."
fi
