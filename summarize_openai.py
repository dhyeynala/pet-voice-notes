# summarize_openai.py
import math
import time

# The LLM is resolved per call (fake by default, OpenAI when OPENAI_API_KEY is set);
# no client is created at import time.
from petpulse.deps import get_llm
from petpulse.providers.llm import LegacyTask


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
            response = get_llm().legacy_chat(
                LegacyTask.NOTE_SUMMARY,
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
            print(f"Summary generated: {summary[:100]}...")
            return summary

        except Exception as e:
            print(f"OpenAI API error (attempt {attempt + 1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                # Exponential backoff
                wait_time = 2**attempt
                print(f"⏳ Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                # No summary rather than an error string posing as one (review H2).
                return None

    return None


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

            response = get_llm().legacy_chat(
                LegacyTask.PDF_SUMMARY,
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
            print(f"PDF Summary generated: {summary[:100]}...")
            return summary

        except Exception as e:
            print(f"OpenAI API error for PDF (attempt {attempt + 1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                wait_time = 2**attempt
                print(f"⏳ Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                return f"Unable to generate AI summary for PDF due to API error. Document contains medical information that should be reviewed manually."

    return "PDF summary generation failed after multiple attempts."


def classify_pet_content(text, max_retries=3):
    """
    Classify pet content as MEDICAL, DAILY_ACTIVITY, MIXED or OTHER.

    Returns classification and confidence score. The model output is validated: a label
    outside ``VALID_CLASSIFICATIONS``, a confidence outside 0..1, non-JSON or truncated output
    all become ``UNKNOWN`` with ``needs_review=True`` (review M1), as does an outage (H2).
    """
    if not text or len(text.strip()) == 0:
        return unknown_classification("Empty input")

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
            response = get_llm().legacy_chat(
                LegacyTask.NOTE_CLASSIFY,
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

            choice = response.choices[0]
            if getattr(choice, "finish_reason", "stop") == "length":
                print("⚠️ Classification output was truncated")
                return unknown_classification("Model output was truncated")

            response_content = (choice.message.content or "").strip()
            print(f"🔍 Raw classification response: {response_content[:100]}...")

            # Parse and validate; no keyword guessing when the output is not valid JSON
            try:
                raw = json.loads(response_content)
            except json.JSONDecodeError:
                print("⚠️ Classification output is not JSON")
                return unknown_classification("Model output was not valid JSON")
            result = validate_classification(raw)

            print(
                f"📊 Content classified as: {result.get('classification', 'UNKNOWN')} (confidence: {result.get('confidence', 0.0)})"
            )
            return result

        except Exception as e:
            print(f"Classification error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                wait_time = 2**attempt
                print(f"⏳ Retrying classification in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print("🔄 Using fallback classification...")
                return fallback_classification(text)

    return fallback_classification(text)


VALID_CLASSIFICATIONS = ("MEDICAL", "DAILY_ACTIVITY", "MIXED", "OTHER", "UNKNOWN")


def unknown_classification(reason):
    """The explicit "we don't know" result: never a guess, always flagged for review."""
    return {
        "classification": "UNKNOWN",
        "confidence": 0.0,
        "keywords": [],
        "reasoning": reason,
        "primary_activities": [],
        "needs_review": True,
    }


def _string_list(value, limit=10, max_len=60):
    if not isinstance(value, list):
        return []
    return [item.strip()[:max_len] for item in value if isinstance(item, str) and item.strip()][:limit]


def validate_classification(raw):
    """Validate model JSON against the classification schema (review M1).

    Off-enum labels, non-numeric or out-of-range confidence, or a non-object payload are
    rejected and become UNKNOWN with ``needs_review=True``.
    """
    if not isinstance(raw, dict):
        return unknown_classification("Model output was not a JSON object")
    label = raw.get("classification")
    confidence = raw.get("confidence")
    if label not in VALID_CLASSIFICATIONS:
        return unknown_classification(f"Model returned an invalid classification: {str(label)[:40]!r}")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not 0.0 <= confidence <= 1.0
    ):
        return unknown_classification(f"Model returned an invalid confidence: {str(confidence)[:40]!r}")
    reasoning = raw.get("reasoning")
    return {
        "classification": label,
        "confidence": float(confidence),
        "keywords": _string_list(raw.get("keywords")),
        "reasoning": reasoning.strip()[:500] if isinstance(reasoning, str) else "",
        "primary_activities": _string_list(raw.get("primary_activities")),
        "needs_review": label == "UNKNOWN",
    }


def fallback_classification(text):
    """
    Final fallback when the model is unavailable: UNKNOWN, never a positive assumption (review H2).
    """
    return unknown_classification("Classification unavailable (AI service error)")
