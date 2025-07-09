#!/usr/bin/env python3
"""
Security audit script to check for exposed credentials in the codebase.
Run this before committing to ensure no sensitive data is exposed.
"""

import os
import re
import sys
from pathlib import Path

def check_file_for_secrets(file_path):
    """Check a single file for potential secrets"""
    secrets_found = []
    
    # Skip Firebase client config (API keys are public by design)
    if 'firebase-config.js' in file_path:
        return secrets_found
    
    # Patterns to look for
    patterns = {
        'OpenAI API Key': r'sk-[a-zA-Z0-9]{20,}',
        'Google API Key': r'AIza[a-zA-Z0-9]{35}',
        'Private Key': r'-----BEGIN [A-Z ]+PRIVATE KEY-----',
        'Hardcoded Password': r'password["\s]*[:=]["\s]*[^"\s]{3,}',
        'API Key Pattern': r'api[_-]?key["\s]*[:=]["\s]*["\'][a-zA-Z0-9]{10,}["\']',
        'Secret Pattern': r'secret["\s]*[:=]["\s]*["\'][a-zA-Z0-9]{10,}["\']',
        'Token Pattern': r'token["\s]*[:=]["\s]*["\'][a-zA-Z0-9]{10,}["\']',
    }
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        for pattern_name, pattern in patterns.items():
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                for match in matches:
                    # Skip obvious examples or placeholders
                    if any(placeholder in match.lower() for placeholder in 
                          ['your_', 'example', 'placeholder', 'xxxx', 'yyyy', 'demo']):
                        continue
                    secrets_found.append({
                        'file': file_path,
                        'type': pattern_name,
                        'match': match[:50] + '...' if len(match) > 50 else match
                    })
    
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    
    return secrets_found

def audit_codebase():
    """Audit the entire codebase for exposed secrets"""
    print("🔍 Security Audit: Scanning for exposed credentials...")
    print("=" * 60)
    
    # Files to check
    extensions_to_check = ['.py', '.js', '.html', '.json', '.md', '.env', '.txt']
    
    # Files/folders to skip
    skip_patterns = [
        '.venv/', 'venv/', '__pycache__/', '.git/', 'node_modules/',
        '.env.example', 'SECURITY.md', 'security_audit.py'
    ]
    
    all_secrets = []
    files_checked = 0
    
    for root, dirs, files in os.walk('.'):
        # Skip certain directories
        dirs[:] = [d for d in dirs if not any(skip in os.path.join(root, d) for skip in skip_patterns)]
        
        for file in files:
            file_path = os.path.join(root, file)
            
            # Skip certain files
            if any(skip in file_path for skip in skip_patterns):
                continue
                
            # Check file extension
            if any(file.endswith(ext) for ext in extensions_to_check):
                files_checked += 1
                secrets = check_file_for_secrets(file_path)
                all_secrets.extend(secrets)
    
    print(f"📁 Files checked: {files_checked}")
    print(f"🚨 Potential secrets found: {len(all_secrets)}")
    print()
    
    if all_secrets:
        print("⚠️  SECURITY ISSUES FOUND:")
        print("-" * 40)
        
        for secret in all_secrets:
            print(f"File: {secret['file']}")
            print(f"Type: {secret['type']}")
            print(f"Match: {secret['match']}")
            print("-" * 40)
        
        print()
        print("🛡️  RECOMMENDATIONS:")
        print("1. Move sensitive data to .env files")
        print("2. Use environment variables in code")
        print("3. Add sensitive files to .gitignore")
        print("4. Regenerate any exposed API keys")
        
        return False
    else:
        print("✅ No obvious secrets found in codebase!")
        print("📋 Security checklist:")
        print("  ✓ No hardcoded API keys detected")
        print("  ✓ No exposed credentials found")
        print("  ✓ Environment variables appear to be used correctly")
        return True

def check_gitignore():
    """Check if .gitignore exists and contains necessary entries"""
    print("\n🔒 Checking .gitignore configuration...")
    
    required_entries = [
        '.env',
        'gcloud-key.json',
        '*-key.json',
        '__pycache__/',
        '.venv/'
    ]
    
    if not os.path.exists('.gitignore'):
        print("❌ .gitignore file not found!")
        return False
    
    with open('.gitignore', 'r') as f:
        gitignore_content = f.read()
    
    missing_entries = []
    for entry in required_entries:
        if entry not in gitignore_content:
            missing_entries.append(entry)
    
    if missing_entries:
        print(f"⚠️  Missing entries in .gitignore: {missing_entries}")
        return False
    else:
        print("✅ .gitignore is properly configured!")
        return True

def main():
    """Main security audit function"""
    print("🔐 PetPages Security Audit")
    print("=" * 40)
    
    # Change to script directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Run checks
    secrets_check = audit_codebase()
    gitignore_check = check_gitignore()
    
    print("\n" + "=" * 60)
    
    if secrets_check and gitignore_check:
        print("🎉 SECURITY AUDIT PASSED!")
        print("✅ Your codebase appears to be secure for commit.")
        return 0
    else:
        print("🚨 SECURITY AUDIT FAILED!")
        print("❌ Please fix the issues above before committing.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
