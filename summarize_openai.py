# summarize_openai.py
import os
from openai import OpenAI
from dotenv import load_dotenv
import time

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def summarize_text(text, max_retries=3):
    """
    Summarize text using OpenAI GPT-4o with retry logic
    """
    if not text or len(text.strip()) == 0:
        return "No content to summarize"
    
    system_prompt = """You are a veterinary assistant AI. 

    Your task is to summarize pet health-related voice notes or text input. 
    
    Focus on:
    - Key symptoms or observations
    - Behavioral changes
    - Medical concerns
    - Treatment mentions
    - Important dates or events
    - Action items or follow-ups needed
    
    Keep the summary:
    - Concise but informative (2-4 sentences)
    - Medical terminology when appropriate
    - Actionable for pet owners and veterinarians
    - Formatted clearly
    
    If the text is not pet health related, still provide a brief summary but note that it may not be relevant to pet care."""
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user", 
                        "content": f"Please summarize this pet health note:\n\n{text[:4000]}"  # Limit to prevent token overflow
                    }
                ],
                temperature=0.3,
                max_tokens=200
            )
            
            summary = response.choices[0].message.content.strip()
            print(f"✅ Summary generated: {summary[:100]}...")
            return summary
            
        except Exception as e:
            print(f"❌ OpenAI API error (attempt {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                # Exponential backoff
                wait_time = 2 ** attempt
                print(f"⏳ Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                # Final fallback
                return f"Unable to generate AI summary due to API error. Original text: {text[:200]}..."
    
    return "Summary generation failed after multiple attempts."

def summarize_pdf_text(pdf_text, max_retries=3):
    """
    Summarize PDF medical document text using OpenAI GPT-4o
    """
    if not pdf_text or len(pdf_text.strip()) == 0:
        return "No PDF content to summarize"
    
    system_prompt = """You are a veterinary assistant AI specializing in medical document analysis.

    Your task is to summarize veterinary medical documents (lab results, exam notes, treatment plans, etc.).
    
    Extract and organize:
    - Patient (pet) information if mentioned
    - Key findings or diagnoses
    - Test results (normal/abnormal)
    - Medications prescribed
    - Treatment recommendations
    - Follow-up instructions
    - Important dates
    - Veterinarian notes or observations
    
    Format the summary as:
    - Clear, professional medical summary
    - Bullet points for key findings
    - Highlight any concerning results
    - Include specific values when relevant
    - Note any recommended actions
    
    Keep it comprehensive but readable for pet owners."""
    
    for attempt in range(max_retries):
        try:
            # Truncate very long PDF text to prevent token limits
            truncated_text = pdf_text[:12000] if len(pdf_text) > 12000 else pdf_text
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": f"Please analyze and summarize this veterinary medical document:\n\n{truncated_text}"
                    }
                ],
                temperature=0.2,
                max_tokens=500
            )
            
            summary = response.choices[0].message.content.strip()
            print(f"✅ PDF Summary generated: {summary[:100]}...")
            return summary
            
        except Exception as e:
            print(f"❌ OpenAI API error for PDF (attempt {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"⏳ Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                return f"Unable to generate AI summary for PDF due to API error. Document contains medical information that should be reviewed manually."
    
    return "PDF summary generation failed after multiple attempts."
