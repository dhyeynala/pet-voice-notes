# transcribe.py

import os
import queue
import pyaudio
from dotenv import load_dotenv
from google.cloud import speech

# Load credentials
load_dotenv()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "gcloud-key.json")

# Audio settings
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms
audio_queue = queue.Queue()

def callback(in_data, frame_count, time_info, status):
    audio_queue.put(in_data)
    return (None, pyaudio.paContinue)

def audio_generator():
    while True:
        data = audio_queue.get()
        if data is None:
            break
        yield data

def transcribe_audio():
    client = speech.SpeechClient()

    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=RATE,
        language_code="en-US",
    )
    streaming_config = speech.StreamingRecognitionConfig(config=config)

    mic = pyaudio.PyAudio()
    stream = mic.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK,
        stream_callback=callback
    )

    print("🎤 Recording... Speak now (Press Ctrl+C to stop)")

    stream.start_stream()
    transcript = ""

    try:
        requests = (speech.StreamingRecognizeRequest(audio_content=chunk) for chunk in audio_generator())
        responses = client.streaming_recognize(streaming_config, requests)

        for response in responses:
            for result in response.results:
                if result.is_final:
                    text = result.alternatives[0].transcript
                    print(f">> {text}")
                    transcript += text + " "

    except KeyboardInterrupt:
        print("\n🛑 Recording stopped by user.")

    finally:
        stream.stop_stream()
        stream.close()
        mic.terminate()
        audio_queue.put(None)

    return transcript.strip()



