"use client";
import { useState, useRef } from "react";

export default function RecordVoice() {
  const [transcript, setTranscript] = useState("");
  const [summary, setSummary] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  const startRecording = async () => {
    const ws = new WebSocket("ws://localhost:8000/ws/audio");
    wsRef.current = ws;

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const audioCtx = new AudioContext();
    const source = audioCtx.createMediaStreamSource(stream);
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);

    processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      const int16 = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) int16[i] = input[i] * 32767;
      if (ws.readyState === WebSocket.OPEN) ws.send(int16.buffer);
    };

    source.connect(processor);
    processor.connect(audioCtx.destination);

    ws.onmessage = (e) => {
      const msg = e.data;
      if (msg.startsWith("SUMMARY:")) {
        setSummary(msg.replace("SUMMARY:", ""));
      } else {
        setTranscript(msg);
      }
    };
  };

  return (
    <div>
      <button onClick={startRecording}>🎙️ Start Recording</button>
      <p><strong>Transcript:</strong> {transcript}</p>
      <p><strong>Summary:</strong> {summary}</p>
    </div>
  );
}
