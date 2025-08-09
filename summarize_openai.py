# summarize_openai.py
import os
from openai import OpenAI
from dotenv import load_dotenv
import time

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def summarize_text(text, max_retries=3):
    """
    Summarize text using OpenAI GPT-4o with intelligent context detection
    Handles MEDICAL concerns, DAILY ACTIVITIES, and MIXED content
    """
    if not text or len(text.strip()) == 0:
        return "No content to summarize"

    # Enhanced system prompt for comprehensive pet care tracking
    system_prompt = """You are an intelligent pet care assistant AI that analyzes ALL aspects of pet life - both medical concerns and daily activities.

    Your task is to summarize pet-related voice notes or text input with intelligent context detection and appropriate tone.
    
    **For MEDICAL content, focus on:**
    - Key symptoms or health observations
    - Behavioral changes indicating potential health issues
    - Medical concerns, injuries, or pain indicators
    - Treatment mentions, medications, or therapy
    - Veterinary visit notes and follow-up care
    - Health alerts requiring attention
    - Changes in appetite, energy, or normal behavior
    
    **For DAILY ACTIVITY content, focus on:**
    - Exercise and physical activity (walks, runs, play sessions)
    - Diet and feeding patterns (meals, treats, appetite)
    - Sleep and rest periods (duration, quality, location)
    - Mood and energy levels throughout the day
    - Grooming and hygiene activities
    - Training progress and behavioral milestones
    - Social interactions with humans and other pets
    - Environmental enrichment and mental stimulation
    - Routine activities and daily habits
    - Special moments, achievements, or fun experiences
    
    **For MIXED content:**
    - Clearly separate medical observations from daily activities
    - Prioritize any health concerns while acknowledging positive activities
    - Note correlations between activities and health/mood
    
    **Output Guidelines:**
    - **Tone**: Use encouraging, positive tone for daily activities; professional, caring tone for medical concerns
    - **Length**: 2-4 sentences, concise but informative
    - **Actionability**: Include relevant timestamps, frequencies, or next steps when mentioned
    - **Categories**: Identify primary content type (MEDICAL, DAILY_ACTIVITY, or MIXED)
    - **Insights**: Add helpful observations about patterns or behaviors
    
    **Examples:**
    - **Medical**: "Pet showing limping behavior on left hind leg since morning. Recommend veterinary evaluation for potential injury. Monitor for worsening symptoms."
    - **Daily**: "Had an energetic 30-minute walk at Central Park today! Showed great social skills with other dogs and maintained excellent leash behavior. Very happy and well-exercised."
    - **Mixed**: "Normal eating and enthusiastic play session in the yard, but owner noticed slight coughing during activity. Monitor respiratory symptoms and consider limiting strenuous exercise until assessed."
    - **Training**: "Successfully learned 'sit' and 'stay' commands during today's 15-minute training session. Responds well to positive reinforcement with treats. Ready to progress to more complex commands."
    - **Routine**: "Perfect morning routine: ate breakfast enthusiastically, enjoyed 20-minute walk, now relaxing in favorite sunny spot. Energy level appears normal and mood is content."
    
    Always provide helpful, accurate summaries that celebrate positive moments while taking health concerns seriously."""

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Please analyze and summarize this pet note. Determine if it's medical, daily activity, or mixed content:\n\n{text[:4000]}",
                    },
                ],
                temperature=0.3,
                max_tokens=200,
            )

            summary = response.choices[0].message.content.strip()
            print(f"✅ Summary generated: {summary[:100]}...")
            return summary

        except Exception as e:
            print(f"❌ OpenAI API error (attempt {attempt + 1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                # Exponential backoff
                wait_time = 2**attempt
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
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Please analyze and summarize this veterinary medical document:\n\n{truncated_text}",
                    },
                ],
                temperature=0.2,
                max_tokens=500,
            )

            summary = response.choices[0].message.content.strip()
            print(f"✅ PDF Summary generated: {summary[:100]}...")
            return summary

        except Exception as e:
            print(f"❌ OpenAI API error for PDF (attempt {attempt + 1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                wait_time = 2**attempt
                print(f"⏳ Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                return f"Unable to generate AI summary for PDF due to API error. Document contains medical information that should be reviewed manually."

    return "PDF summary generation failed after multiple attempts."


def classify_pet_content(text, max_retries=3):
    """
    Classify pet content as MEDICAL, DAILY_ACTIVITY, or MIXED
    Returns classification and confidence score
    """
    if not text or len(text.strip()) == 0:
        return {
            "classification": "UNKNOWN",
            "confidence": 0.0,
            "keywords": [],
            "reasoning": "Empty input",
            "primary_activities": [],
        }

    classification_prompt = """You are a comprehensive pet content classifier. Analyze the following text and classify it accurately:

    **MEDICAL**: Health concerns, symptoms, injuries, veterinary visits, medications, illness, pain, behavioral changes indicating health issues, appetite loss, lethargy due to illness, emergency situations

    **DAILY_ACTIVITY**: Normal daily life including exercise, regular meals, play, sleep, grooming, training, social interactions, routine behaviors, energy levels, mood changes due to activities, environmental enrichment, achievements, fun experiences

    **MIXED**: Contains both medical concerns AND daily activities, or daily activities with health implications

    **Classification Guidelines:**
    - Prioritize MEDICAL if any health concerns are mentioned
    - Choose DAILY_ACTIVITY for normal, healthy pet behaviors and activities
    - Use MIXED when health and activities are both significantly present
    - Consider context: "tired after play" = DAILY_ACTIVITY, "lethargic without cause" = MEDICAL
    
    **Keywords to help classify:**
    - Medical: symptoms, vet, medication, pain, injury, sick, illness, emergency, limping, vomiting, diarrhea, loss of appetite, concerning behavior
    - Daily: walk, play, eat/meal, sleep, training, grooming, bath, park, exercise, happy, energetic, social, learn, achieve, routine, fun
    
    Respond in JSON format:
    {
        "classification": "MEDICAL" | "DAILY_ACTIVITY" | "MIXED",
        "confidence": 0.0-1.0,
        "keywords": ["key", "words", "found"],
        "reasoning": "brief explanation of classification decision",
        "primary_activities": ["main activities or concerns mentioned"]
    }"""

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": classification_prompt},
                    {"role": "user", "content": f"Classify this pet content:\n\n{text[:2000]}"},
                ],
                temperature=0.1,  # Lower temperature for more consistent JSON output
                max_tokens=200,  # Increased token limit
                response_format={"type": "json_object"},  # Force JSON response format
            )

            import json

            response_content = response.choices[0].message.content.strip()
            print(f"🔍 Raw classification response: {response_content[:100]}...")

            # Try to parse JSON
            try:
                result = json.loads(response_content)
            except json.JSONDecodeError:
                # Fallback: try to extract classification from text
                print("⚠️ JSON parsing failed, attempting text extraction...")
                result = extract_classification_from_text(response_content, text)

            # Validate required fields
            if not result.get("classification"):
                result["classification"] = "MIXED"
            if not isinstance(result.get("confidence"), (int, float)):
                result["confidence"] = 0.5
            if not result.get("keywords"):
                result["keywords"] = []
            if not result.get("reasoning"):
                result["reasoning"] = "Classification completed"
            if not result.get("primary_activities"):
                result["primary_activities"] = []

            print(
                f"📊 Content classified as: {result.get('classification', 'UNKNOWN')} (confidence: {result.get('confidence', 0.0)})"
            )
            return result

        except Exception as e:
            print(f"❌ Classification error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                wait_time = 2**attempt
                print(f"⏳ Retrying classification in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print("🔄 Using fallback classification...")
                return fallback_classification(text)

    return fallback_classification(text)


def extract_classification_from_text(response_text, original_text):
    """
    Fallback function to extract classification from non-JSON response
    """
    response_lower = response_text.lower()
    original_lower = original_text.lower()

    # Determine classification based on content analysis
    medical_keywords = [
        'symptom',
        'vet',
        'medication',
        'pain',
        'injury',
        'sick',
        'illness',
        'emergency',
        'limp',
        'vomit',
        'diarrhea',
        'appetite',
        'concerning',
        'treatment',
        'diagnosis',
        'health',
        'doctor',
    ]

    daily_keywords = [
        'walk',
        'play',
        'eat',
        'meal',
        'sleep',
        'train',
        'groom',
        'bath',
        'park',
        'exercise',
        'happy',
        'energetic',
        'social',
        'learn',
        'achieve',
        'routine',
        'fun',
        'good',
        'great',
        'enjoy',
    ]

    medical_score = sum(1 for keyword in medical_keywords if keyword in original_lower)
    daily_score = sum(1 for keyword in daily_keywords if keyword in original_lower)

    if medical_score > daily_score and medical_score > 0:
        classification = "MEDICAL"
        confidence = min(0.9, 0.6 + (medical_score * 0.1))
    elif daily_score > medical_score and daily_score > 0:
        classification = "DAILY_ACTIVITY"
        confidence = min(0.9, 0.6 + (daily_score * 0.1))
    elif medical_score > 0 and daily_score > 0:
        classification = "MIXED"
        confidence = 0.7
    else:
        classification = "MIXED"
        confidence = 0.5

    return {
        "classification": classification,
        "confidence": confidence,
        "keywords": [kw for kw in medical_keywords + daily_keywords if kw in original_lower][:5],
        "reasoning": f"Extracted from text analysis: {medical_score} medical, {daily_score} daily keywords",
        "primary_activities": ["text_analysis_fallback"],
    }


def fallback_classification(text):
    """
    Final fallback classification when all else fails
    """
    return {
        "classification": "DAILY_ACTIVITY",  # Default to positive assumption
        "confidence": 0.5,
        "keywords": [],
        "reasoning": "Fallback classification due to API issues",
        "primary_activities": ["general_pet_activity"],
    }
