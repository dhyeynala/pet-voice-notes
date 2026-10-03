// public/js/recorder.js: voice notes recorded in the browser with MediaRecorder and uploaded to
// POST /api/pets/{id}/voice-notes (multipart: audio=<blob>, tz), or a bundled sample
// (sample_id from GET /api/voice/samples). Response: {transcription: {status, text, confidence}, note}.
// 422 = no speech, 502 = speech-to-text error (nothing stored in either case), 415 = unsupported type.
import { apiFetch, apiPath, asList, browserTimeZone, describeError } from "./api.js";
import { el, icon, replaceChildren, showNotification, showOverlay } from "./dom.js";
import { state } from "./state.js";
import { renderNote, loadNotes } from "./notes.js";

export const MAX_SECONDS = 60;
export const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg", "audio/mp4"];

/** First MediaRecorder mime type the browser supports, or "" to let the browser choose. */
export function pickMimeType(isTypeSupported) {
  if (typeof isTypeSupported !== "function") return "";
  for (const type of MIME_CANDIDATES) {
    try {
      if (isTypeSupported(type)) return type;
    } catch {
      /* ignore and try the next one */
    }
  }
  return "";
}

export function extensionFor(mime) {
  if (!mime) return "webm";
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("mp4") || mime.includes("aac")) return "m4a";
  if (mime.includes("wav")) return "wav";
  return "webm";
}

/** User-facing message for an upload error (contract status codes). */
export function voiceErrorMessage(err, mime) {
  switch (err && err.status) {
    case 422:
      return "No speech was detected in the recording, so nothing was saved. Try again a little closer to the microphone.";
    case 502:
      return "The speech-to-text service failed, so nothing was saved. Please try again in a moment.";
    case 415:
      return `The server can't read this audio format${mime ? ` (${mime})` : ""}. Try another browser, or use a sample recording.`;
    case 413:
      return "The recording is too large. Keep voice notes under a minute.";
    default:
      return `Voice note failed: ${describeError(err)}`;
  }
}

/** User-facing message for a getUserMedia / MediaRecorder failure. */
export function micErrorMessage(err) {
  const name = err && err.name;
  if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") {
    return "Microphone access was blocked. Allow the microphone for this site in your browser settings, or use a sample recording below.";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError" || name === "OverconstrainedError") {
    return "No microphone was found. Connect one, or use a sample recording below.";
  }
  if (name === "NotSupportedError" || name === "TypeError") {
    return "Recording isn't available in this browser context (it needs HTTPS or localhost). Use a sample recording below.";
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return "The microphone is in use by another application. Close it and try again, or use a sample recording.";
  }
  return `Could not start recording: ${(err && err.message) || name || "unknown error"}`;
}

let recorder = null;
let stream = null;
let chunks = [];
let timerId = null;
let capId = null;
let startedAt = 0;
let samplesLoaded = false;

const $ = (id) => document.getElementById(id);

function setStatus(text, cls) {
  const node = $("status");
  node.textContent = text;
  node.className = `status ${cls}`;
  node.style.display = text ? "block" : "none";
}

function setButton(mode) {
  const button = $("record-button");
  button.classList.toggle("recording", mode === "recording");
  button.disabled = mode === "busy";
  const label = mode === "recording" ? "Stop Recording" : mode === "busy" ? "Processing…" : "Start Recording";
  const iconCls = mode === "recording" ? "fas fa-stop" : mode === "busy" ? "fas fa-spinner fa-spin" : "fas fa-microphone";
  replaceChildren(button, icon(iconCls), " ", el("span", { id: "record-button-text", text: label }));
}

function fmt(seconds) {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

function cleanup() {
  clearInterval(timerId);
  clearTimeout(capId);
  timerId = capId = null;
  if (stream) stream.getTracks().forEach((t) => t.stop());
  stream = null;
}

function showResult(result) {
  const t = result.transcription || {};
  $("transcript-content").textContent = t.text || "(empty transcript)";
  replaceChildren($("summary-content"), result.note ? renderNote(result.note, { showText: false }) : el("div", { text: "No note was returned." }));
  $("output").classList.add("has-content");
}

function clearResult() {
  $("transcript-content").textContent = "";
  replaceChildren($("summary-content"));
  $("output").classList.remove("has-content");
}

async function upload(form, mimeForErrors) {
  if (!state.selectedPet) {
    showNotification("Please select a pet first", "warning");
    return;
  }
  form.append("tz", browserTimeZone());
  setButton("busy");
  setStatus("⏳ Transcribing and analyzing…", "processing");
  showOverlay(true);
  try {
    const result = await apiFetch(apiPath("pets", state.selectedPet, "voice-notes"), { body: form });
    showResult(result || {});
    const urgent = result && result.note && result.note.urgent;
    setStatus(urgent ? "Voice note saved. It contains a possible red flag." : "Voice note saved.", urgent ? "error" : "success");
    showNotification(urgent ? "Voice note saved: possible red flag" : "Voice note saved", urgent ? "warning" : "success");
    loadNotes({ targetId: "voice-recent-notes", limit: 5 });
  } catch (err) {
    clearResult(); // don't leave the previous note on screen next to the error
    setStatus(voiceErrorMessage(err, mimeForErrors), "error");
  } finally {
    showOverlay(false);
    setButton("idle");
  }
}

async function startRecording() {
  if (!state.selectedPet) {
    showNotification("Please select a pet first", "warning");
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === "undefined") {
    setStatus("This browser can't record audio here (recording needs a modern browser on HTTPS or localhost). Use a sample recording below.", "error");
    return;
  }
  setButton("busy");
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    cleanup();
    setButton("idle");
    setStatus(micErrorMessage(err), "error");
    return;
  }
  const mimeType = pickMimeType(MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported.bind(MediaRecorder));
  try {
    recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  } catch (err) {
    cleanup();
    setButton("idle");
    setStatus(micErrorMessage(err), "error");
    return;
  }
  chunks = [];
  recorder.addEventListener("dataavailable", (e) => {
    if (e.data && e.data.size) chunks.push(e.data);
  });
  recorder.addEventListener("stop", () => {
    const type = recorder.mimeType || mimeType || "audio/webm";
    const blob = new Blob(chunks, { type });
    cleanup();
    recorder = null;
    if (!blob.size) {
      setButton("idle");
      setStatus("The recording was empty. Please try again.", "error");
      return;
    }
    const form = new FormData();
    form.append("audio", blob, `voice-note.${extensionFor(type)}`);
    upload(form, type);
  });
  recorder.start(1000);
  startedAt = Date.now();
  setButton("recording");
  $("output").classList.remove("has-content");
  const tick = () => setStatus(`🎙️ Recording… ${fmt((Date.now() - startedAt) / 1000)} / ${fmt(MAX_SECONDS)}. Click Stop when finished.`, "recording");
  tick();
  timerId = setInterval(tick, 500);
  capId = setTimeout(() => {
    showNotification(`Recording stopped at the ${MAX_SECONDS}-second limit`, "info");
    stopRecording();
  }, MAX_SECONDS * 1000);
}

function stopRecording() {
  if (recorder && recorder.state !== "inactive") {
    setButton("busy");
    recorder.stop();
  }
}

export function toggleRecording() {
  if (recorder && recorder.state === "recording") stopRecording();
  else if (!recorder) startRecording();
}

/** Fill the "Use a sample recording" picker (once). */
export async function loadSamples() {
  if (samplesLoaded) return;
  const select = $("sample-select");
  const button = $("sample-button");
  if (!select) return;
  try {
    const samples = asList(await apiFetch("/api/voice/samples"));
    select.replaceChildren(el("option", { value: "", text: samples.length ? "Choose a sample…" : "No samples available" }));
    for (const s of samples) select.appendChild(el("option", { value: s.id, text: s.label || s.id }));
    button.disabled = !samples.length;
    samplesLoaded = true;
  } catch (err) {
    select.replaceChildren(el("option", { value: "", text: "Samples unavailable" }));
    button.disabled = true;
    console.warn("Could not load voice samples:", describeError(err));
  }
}

function useSample() {
  const id = $("sample-select").value;
  if (!id) {
    showNotification("Choose a sample first", "warning");
    return;
  }
  if (recorder) return;
  const form = new FormData();
  form.append("sample_id", id);
  $("output").classList.remove("has-content");
  upload(form, null);
}

export function initRecorder() {
  $("record-button").addEventListener("click", toggleRecording);
  $("sample-button").addEventListener("click", useSample);
  window.addEventListener("beforeunload", cleanup);
}
