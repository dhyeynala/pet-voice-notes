# transcribe.py 

import os
import queue
import pyaudio
import threading
import time
from dotenv import load_dotenv
from google.cloud import speech

# Load credentials
load_dotenv()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "gcloud-key.json")

# Audio settings
RATE = 16000
CHUNK = int(RATE / 10) 
audio_queue = queue.Queue()

# Callback to capture audio from mic
def callback(in_data, frame_count, time_info, status):
    audio_queue.put(in_data)
    return (None, pyaudio.paContinue)

# Generator for streaming audio to Google API
def audio_generator():
    while True:
        data = audio_queue.get()
        if data is None:
            break
        yield data

# Automatically stop recording after N seconds
def stop_recording_after(seconds, stream):
    time.sleep(seconds)
    print(f"Auto-stopping after {seconds} seconds.")
    stream.stop_stream()
    stream.close()
    audio_queue.put(None)

# Transcribe audio from mic using Google Cloud Speech
def transcribe_audio(duration_seconds=10):
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

    print(f"Recording for {duration_seconds} seconds...")

    # Start streaming and launch stop timer
    stream.start_stream()
    threading.Thread(target=stop_recording_after, args=(duration_seconds, stream), daemon=True).start()

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

    except Exception as e:
        print(f"Error during transcription: {e}")

    finally:
        mic.terminate()

    return transcript.strip()
