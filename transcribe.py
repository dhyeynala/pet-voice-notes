# transcribe.py
"""Legacy server-microphone recording (review finding C5).

Kept only so the existing routes keep their shape until the voice track replaces them with
browser MediaRecorder uploads and deletes this module. PyAudio is no longer a dependency:
without it, recording reports a clear error instead of breaking imports. Transcription goes
through the configured ``STTProvider`` (fake by default).
"""

import io
import queue
import threading
import time
import wave

from petpulse.deps import get_stt

# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms chunks
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit PCM (pyaudio.paInt16)

MIC_UNAVAILABLE = (
    "Server-side microphone recording is unavailable: PyAudio is not installed. "
    "Use text input; browser recording arrives with the voice track."
)

# Global state for recording
recording_state = {"is_recording": False, "audio_data": [], "transcript": "", "audio_queue": queue.Queue()}


def _pyaudio():
    """Import PyAudio lazily; ``None`` when it is not installed (the default)."""
    try:
        import pyaudio  # type: ignore[import-not-found]
    except ImportError:
        return None
    return pyaudio


def _pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(RATE)
        wav.writeframes(pcm)
    return buf.getvalue()


def transcribe_audio(duration_seconds=10):
    """Simple transcription for a fixed duration"""
    pyaudio = _pyaudio()
    if pyaudio is None:
        return f"Error: {MIC_UNAVAILABLE}"

    audio = pyaudio.PyAudio()
    stream = audio.open(format=pyaudio.paInt16, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

    print(f"Recording for {duration_seconds} seconds...")
    frames = []

    for _ in range(0, int(RATE / CHUNK * duration_seconds)):
        data = stream.read(CHUNK)
        frames.append(data)

    print("Recording finished. Processing...")

    stream.stop_stream()
    stream.close()
    audio.terminate()

    return _transcribe_audio_data(b''.join(frames))


def start_recording():
    """Start recording audio"""

    if _pyaudio() is None:
        return {"status": "error", "message": MIC_UNAVAILABLE}

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

    print(f"Stop recording called. Current state: {recording_state['is_recording']}")

    if not recording_state["is_recording"]:
        print("Not currently recording")
        return {"status": "error", "message": "Not recording"}

    print("Stopping recording...")
    recording_state["is_recording"] = False

    # Wait a moment for recording to finish
    time.sleep(0.5)

    # Process the recorded audio
    if recording_state["audio_data"]:
        print(f"Processing {len(recording_state['audio_data'])} audio chunks")
        audio_data = b''.join(recording_state["audio_data"])
        print(f"Total audio data size: {len(audio_data)} bytes")

        transcript = _transcribe_audio_data(audio_data)
        recording_state["transcript"] = transcript

        print(f"Recording stopped successfully. Transcript: '{transcript[:100]}...'")
        return {"status": "stopped", "transcript": transcript, "message": "Recording stopped and transcribed"}
    else:
        print("No audio data recorded")
        return {"status": "error", "message": "No audio data recorded"}


def get_recording_status():
    """Get current recording status"""
    return {"is_recording": recording_state["is_recording"], "transcript": recording_state["transcript"]}


def _record_audio():
    """Internal function to record audio in background"""

    pyaudio = _pyaudio()
    if pyaudio is None:
        recording_state["is_recording"] = False
        return

    audio = pyaudio.PyAudio()

    stream = audio.open(format=pyaudio.paInt16, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

    print("Recording started...")

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

    print("Recording stopped")


def _transcribe_audio_data(audio_data):
    """Transcribe 16 kHz mono PCM through the configured STT provider.

    Keeps the legacy string contract ("No speech detected" / "Error: ...") on purpose;
    the voice track replaces it with typed ``Transcription`` handling (review H2).
    """
    result = get_stt().transcribe(_pcm_to_wav(audio_data), "audio/wav")
    if result.status == "ok":
        print(f"Transcript: {result.text}")
        return result.text
    if result.status == "no_speech":
        return "No speech detected"
    print(f"Transcription error: {result.error}")
    return f"Error: {result.error}"
