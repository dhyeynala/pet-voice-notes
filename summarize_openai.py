# summarize_openai.py

import os
import time
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def summarize_text(text: str, max_retries: int = 3) -> str:
    if not text.strip():
        return " No input text to summarize."

    print("\n Summarizing with GPT-4o...")

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": "You are a helpful assistant that summarizes medical or pet health notes."},
        {"role": "user", "content": f"Summarize this text: {text}"}
    ]

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.3,
                max_tokens=200
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f" Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
            else:
                return f" OpenAI API error after {max_retries} attempts: {e}"
