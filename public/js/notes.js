// public/js/notes.js: typed notes (POST /api/pets/{id}/notes {text, tz}), the recent-notes list
// (GET /api/pets/{id}/notes?limit=) and the shared Note renderer (also used for voice notes).
import { apiFetch, apiPath, asList, browserTimeZone, describeError } from "./api.js";
import { el, icon, replaceChildren, setStatus, showNotification, showOverlay, formatDateTime } from "./dom.js";
import { state } from "./state.js";
import { responseModeTag } from "./banner.js";

const KIND_BADGES = {
  MEDICAL: { cls: "badge-medical", icon: "fas fa-heartbeat", text: "Health & Medical" },
  DAILY_ACTIVITY: { cls: "badge-activity", icon: "fas fa-heart", text: "Daily Life & Activities" },
  MIXED: { cls: "badge-mixed", icon: "fas fa-brain", text: "Mixed Content" },
  OTHER: { cls: "badge-mixed", icon: "fas fa-sticky-note", text: "Other" },
  UNKNOWN: { cls: "badge-unknown", icon: "fas fa-question-circle", text: "Unknown" },
};
const SOURCE_ICONS = { text: "fas fa-keyboard", voice: "fas fa-microphone", pdf: "fas fa-file-pdf" };

export function kindBadge(kind) {
  const b = KIND_BADGES[kind] || KIND_BADGES.UNKNOWN;
  return el("span", { class: `content-type-badge ${b.cls}` }, el("i", { class: b.icon }), ` ${KIND_BADGES[kind] ? b.text : kind || b.text}`);
}

function describeItem(item) {
  if (item === null || item === undefined) return "";
  if (typeof item === "string") return item;
  const label = item.category || item.flag || item.type || "";
  const text = item.text || item.summary || item.value || "";
  return label && text ? `${label}: ${text}` : label || text || JSON.stringify(item);
}

function sentenceRefs(sentences) {
  if (!Array.isArray(sentences) || sentences.length === 0) return "";
  return ` [${sentences.map((s) => (typeof s === "number" ? `S${s}` : String(s))).join(", ")}]`;
}

/** Render one Note as a card. Every value is inserted as text. */
export function renderNote(note, { showText = true } = {}) {
  const flags = Array.isArray(note.red_flags) ? note.red_flags : [];
  const observations = Array.isArray(note.observations) ? note.observations : [];
  const card = el("div", { class: `note-card${note.urgent ? " urgent" : ""}`, dataset: { noteId: note.id || "" } });

  card.appendChild(
    el(
      "div",
      { class: "note-card-header" },
      kindBadge(note.kind),
      el("span", { class: "note-source", title: `Source: ${note.source || "text"}` }, el("i", { class: SOURCE_ICONS[note.source] || "fas fa-sticky-note" }), ` ${note.source || "text"}`),
      note.needs_review ? el("span", { class: "pill pill-review", text: "Needs review" }) : null,
      note.status && note.status !== "processed" && note.status !== "ok" ? el("span", { class: "pill pill-status", text: note.status }) : null,
      responseModeTag(note.mode),
      el("span", { class: "note-date", text: formatDateTime(note.created_at) })
    )
  );

  if (note.urgent) {
    card.appendChild(
      el(
        "div",
        { class: "urgent-banner", attrs: { role: "alert" } },
        icon("fas fa-exclamation-triangle"),
        ` Contact your vet: possible red flag${note.mode === "demo" ? " (simulated)" : ""}.`
      )
    );
  }
  if (note.status === "unprocessed") {
    card.appendChild(el("div", { class: "note-warning", text: "AI processing failed. The note was saved unprocessed and marked for review." }));
  }
  if (showText && note.text) card.appendChild(el("blockquote", { class: "note-text", text: note.text }));
  if (note.summary) card.appendChild(el("div", { class: "note-summary" }, el("strong", { text: "Summary: " }), note.summary));

  const presentFlags = flags.filter((f) => f && f.flag);
  if (presentFlags.length) {
    card.appendChild(
      el(
        "ul",
        { class: "note-flags" },
        presentFlags.map((f) =>
          el("li", { class: `flag-${f.status || "unknown"}`, text: `${f.flag.replace(/_/g, " ")} (${f.status || "unknown"})${sentenceRefs(f.sentences)}` })
        )
      )
    );
  }
  if (observations.length) {
    card.appendChild(
      el(
        "details",
        { class: "note-observations" },
        el("summary", { text: `${observations.length} observation${observations.length === 1 ? "" : "s"}` }),
        el("ul", {}, observations.map((o) => el("li", { text: describeItem(o) + sentenceRefs(o && o.sentences) })))
      )
    );
  }
  return card;
}

/** Load the latest notes into a container (default: the Notes section list). */
export async function loadNotes({ targetId = "notes-list", limit = 20 } = {}) {
  const container = document.getElementById(targetId);
  if (!container || !state.selectedPet) return;
  replaceChildren(container, el("div", { class: "muted" }, icon("fas fa-spinner fa-spin"), " Loading notes…"));
  try {
    const notes = asList(await apiFetch(apiPath("pets", state.selectedPet, "notes"), { query: { limit } }));
    if (notes.length === 0) {
      replaceChildren(container, el("div", { class: "muted", text: "No notes yet. Add one above or record a voice note." }));
      return;
    }
    replaceChildren(container, notes.map((n) => renderNote(n)));
  } catch (err) {
    replaceChildren(container, el("div", { class: "status-message error", style: "display:block", text: `Could not load notes: ${describeError(err)}` }));
  }
}

async function submitPetText() {
  const status = document.getElementById("pet-input-status");
  if (!state.selectedPet) return setStatus(status, "Please select a pet first", "status-message error", 3000);
  const input = document.getElementById("pet-input-text");
  const text = input.value.trim();
  if (!text) return setStatus(status, "⚠️ Please enter some text first", "status-message error", 3000);

  const button = document.getElementById("submit-note-btn");
  button.disabled = true;
  setStatus(status, "🔄 Processing your note…", "status-message processing");
  showOverlay(true);
  try {
    const note = await apiFetch(apiPath("pets", state.selectedPet, "notes"), { json: { text, tz: browserTimeZone() } });
    const output = document.getElementById("pet-text-output");
    replaceChildren(document.getElementById("pet-text-result"), renderNote(note));
    output.classList.add("has-content");
    input.value = "";
    document.getElementById("text-char-count").textContent = "0";
    setStatus(status, note.urgent ? "Note saved. It contains a possible red flag." : "Note saved.", "status-message success", 5000);
    showNotification(note.urgent ? "Note saved: possible red flag, see the note." : "📝 Note added", note.urgent ? "warning" : "success", 3000);
    loadNotes();
  } catch (err) {
    setStatus(status, `Error: ${describeError(err)}`, "status-message error");
  } finally {
    showOverlay(false);
    button.disabled = false;
  }
}

export function initNotes() {
  document.getElementById("submit-note-btn").addEventListener("click", submitPetText);
  document.getElementById("refresh-notes-btn").addEventListener("click", () => loadNotes());
}
