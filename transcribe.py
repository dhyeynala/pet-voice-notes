# transcribe.py
import pyaudio
import queue
import threading
import time
from google.cloud import speech
import os
from dotenv import load_dotenv
from gcloud_auth import setup_google_cloud_auth

load_dotenv()

# Setup Google Cloud authentication
setup_google_cloud_auth()

# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms chunks
CHANNELS = 1
FORMAT = pyaudio.paInt16

# Global state for recording
recording_state = {
    "is_recording": False,
    "audio_data": [],
    "transcript": "",
    "audio_queue": queue.Queue()
}

def get_speech_client():
    """Create Speech client with proper project configuration"""
    try:
        # Create client with explicit project
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set")
        client = speech.SpeechClient()
        return client
    except Exception as e:
        print(f"❌ Error creating Speech client: {e}")
        return None

def transcribe_audio(duration_seconds=10):
    """Simple transcription for a fixed duration"""
    client = get_speech_client()
    if not client:
        return "Error: Could not initialize Speech client"
    
    # Set up audio recording
    audio = pyaudio.PyAudio()
    
    # Recording configuration
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=RATE,
        language_code="en-US",
    )
    
    # Start recording
    stream = audio.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )
    
    print(f"🎙️  Recording for {duration_seconds} seconds...")
    frames = []
    
    for _ in range(0, int(RATE / CHUNK * duration_seconds)):
        data = stream.read(CHUNK)
        frames.append(data)
    
    print("🔄 Recording finished. Processing...")
    
    # Stop recording
    stream.stop_stream()
    stream.close()
    audio.terminate()
    
    # Combine audio data
    audio_data = b''.join(frames)
    
    # Transcribe
    audio = speech.RecognitionAudio(content=audio_data)
    
    try:
        response = client.recognize(config=config, audio=audio)
        
        if response.results:
            transcript = response.results[0].alternatives[0].transcript
            print(f"📝 Transcript: {transcript}")
            return transcript
        else:
            return "No speech detected"
            
    except Exception as e:
        print(f"❌ Transcription error: {e}")
        return f"Error: {str(e)}"

def start_recording():
    """Start recording audio"""
    global recording_state
    
    if recording_state["is_recording"]:
        return {"status": "error", "message": "Already recording"}
    
    recording_state["is_recording"] = True
    recording_state["audio_data"] = []
    recording_state["transcript"] = ""
    recording_state["audio_queue"] = queue.Queue()
    
    # Start recording thread
    recording_thread = threading.Thread(target=_record_audio)
    recording_thread.daemon = True
    recording_thread.start()
    
    return {"status": "recording", "message": "Recording started"}

def stop_recording():
    """Stop recording and process audio"""
    global recording_state
    
    print(f"🛑 Stop recording called. Current state: {recording_state['is_recording']}")
    
    if not recording_state["is_recording"]:
        print("❌ Not currently recording")
        return {"status": "error", "message": "Not recording"}
    
    print("🔄 Stopping recording...")
    recording_state["is_recording"] = False
    
    # Wait a moment for recording to finish
    time.sleep(0.5)
    
    # Process the recorded audio
    if recording_state["audio_data"]:
        print(f"📊 Processing {len(recording_state['audio_data'])} audio chunks")
        audio_data = b''.join(recording_state["audio_data"])
        print(f"📊 Total audio data size: {len(audio_data)} bytes")
        
        transcript = _transcribe_audio_data(audio_data)
        recording_state["transcript"] = transcript
        
        print(f"✅ Recording stopped successfully. Transcript: '{transcript[:100]}...'")
        return {
            "status": "stopped",
            "transcript": transcript,
            "message": "Recording stopped and transcribed"
        }
    else:
        print("❌ No audio data recorded")
        return {"status": "error", "message": "No audio data recorded"}

def get_recording_status():
    """Get current recording status"""
    return {
        "is_recording": recording_state["is_recording"],
        "transcript": recording_state["transcript"]
    }

def _record_audio():
    """Internal function to record audio in background"""
    global recording_state
    
    audio = pyaudio.PyAudio()
    
    stream = audio.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )
    
    print("🎙️  Recording started...")
    
    while recording_state["is_recording"]:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            recording_state["audio_data"].append(data)
        except Exception as e:
            print(f"Error reading audio: {e}")
            break
    
    stream.stop_stream()
    stream.close()
    audio.terminate()
    
    print("🔄 Recording stopped")

def _transcribe_audio_data(audio_data):
    """Transcribe audio data using Google Cloud Speech-to-Text"""
    try:
        client = get_speech_client()
        if not client:
            return "Error: Could not initialize Speech client"
        
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=RATE,
            language_code="en-US",
        )
        
        audio = speech.RecognitionAudio(content=audio_data)
        print("🔄 Transcribing audio with Google Cloud Speech-to-Text...")
        response = client.recognize(config=config, audio=audio)
        
        if response.results:
            transcript = response.results[0].alternatives[0].transcript
            print(f"📝 Transcript: {transcript}")
            return transcript
        else:
            return "No speech detected"
            
    except Exception as e:
        print(f"❌ Transcription error: {e}")
        return f"Error: {str(e)}"
