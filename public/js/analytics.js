// public/js/analytics.js: tracking forms (POST /api/pets/{id}/analytics/{category}, one typed
// body per category), dashboard metrics and the recent-entries list (GET .../analytics?days=).
import { apiFetch, apiPath, asList, describeError } from "./api.js";
import { el, icon, replaceChildren, showNotification, formatDateTime, parseTimestamp } from "./dom.js";
import { state } from "./state.js";
import { updateCharts } from "./charts.js";

const ICONS = {
  diet: "🍽️",
  exercise: "🏃",
  medication: "💊",
  grooming: "✨",
  energy_levels: "⚡",
  bowel_movements: "💩",
  exit_events: "🚪",
  weight: "⚖️",
  sleep: "😴",
  mood: "😊",
  daily_activity: "📝",
  medical_notes: "🏥",
  mixed_notes: "📋",
};

/** Entry fields may be top-level or nested under data/fields depending on the backend version. */
export function entryFields(entry) {
  return { ...(entry.data || {}), ...(entry.fields || {}), ...entry };
}

export function entryTime(entry) {
  return entry.timestamp || entry.created_at || entry.at || entry.logged_at || null;
}

const val = (id) => document.getElementById(id).value.trim();
const selected = (id) => Array.from(document.getElementById(id).selectedOptions).map((o) => o.value);
const int = (id) => (val(id) === "" ? undefined : Number.parseInt(val(id), 10));
const num = (id) => (val(id) === "" ? undefined : Number(val(id)));

/** Drop empty optional values so the typed schemas (extra="forbid") only see what was entered. */
export function compact(obj) {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined || v === null || v === "") continue;
    if (typeof v === "number" && !Number.isFinite(v)) continue;
    out[k] = v;
  }
  return out;
}

/** form id -> [category, builder]. Field names match the backend's per-category schemas. */
const FORMS = {
  "diet-form": ["diet", () => ({ food: val("diet-food"), quantity: val("diet-quantity"), time: val("diet-time"), type: val("diet-type"), notes: val("diet-notes") })],
  "exercise-form": [
    "exercise",
    () => ({ type: val("exercise-type"), duration: int("exercise-duration"), intensity: val("exercise-intensity"), location: val("exercise-location"), notes: val("exercise-notes") }),
  ],
  "medication-form": [
    "medication",
    () => ({ name: val("medication-name"), dosage: val("medication-dosage"), time: val("medication-time"), frequency: val("medication-frequency"), purpose: val("medication-purpose") }),
  ],
  "grooming-form": ["grooming", () => ({ types: selected("grooming-type"), duration: int("grooming-duration"), products: val("grooming-products"), notes: val("grooming-notes") })],
  "energy-form": ["energy_levels", () => ({ level: int("energy-level"), notes: val("energy-notes") })],
  "bowel-form": ["bowel_movements", () => ({ consistency: val("bowel-consistency"), time: val("bowel-time"), notes: val("bowel-notes") })],
  "exit-form": ["exit_events", () => ({ type: val("exit-type"), duration: int("exit-duration"), destination: val("exit-destination") })],
  "weight-form": ["weight", () => ({ value: num("weight-value"), unit: val("weight-unit"), method: val("weight-method"), time: val("weight-time"), notes: val("weight-notes") })],
  "sleep-form": [
    "sleep",
    () => ({ duration: num("sleep-duration"), quality: val("sleep-quality"), location: val("sleep-location"), interruptions: int("sleep-interruptions"), notes: val("sleep-notes") }),
  ],
  "mood-form": ["mood", () => ({ level: int("mood-level"), triggers: selected("mood-triggers"), behavior: selected("mood-behavior"), time: val("mood-time"), notes: val("mood-notes") })],
};

function setDefaultTimes() {
  const now = new Date().toTimeString().slice(0, 5);
  for (const id of ["diet-time", "medication-time", "bowel-time", "weight-time", "mood-time"]) {
    const input = document.getElementById(id);
    if (input && !input.value) input.value = now;
  }
}

export async function submitAnalyticsForm(data, category) {
  if (!state.selectedPet) {
    showNotification("Please select a pet first", "error");
    return false;
  }
  try {
    await apiFetch(apiPath("pets", state.selectedPet, "analytics", category), { json: data });
    showNotification(`${category.replace(/_/g, " ")} entry saved`, "success");
    loadDashboard();
    loadRecentEntries();
    updateCharts();
    return true;
  } catch (err) {
    showNotification(`Could not save ${category.replace(/_/g, " ")}: ${describeError(err)}`, "error", 6000);
    return false;
  }
}

export function setupAnalyticsFormHandlers() {
  setDefaultTimes();
  for (const [formId, [category, build]] of Object.entries(FORMS)) {
    const form = document.getElementById(formId);
    if (!form) continue;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      if (button) button.disabled = true;
      const ok = await submitAnalyticsForm(compact(build()), category);
      if (button) button.disabled = false;
      if (ok) {
        form.reset();
        setDefaultTimes();
      }
    });
  }
  document.querySelectorAll(".tab-btn[data-tab]").forEach((btn) => btn.addEventListener("click", () => showTab(btn.dataset.tab, btn)));
}

export function showTab(tabName, button) {
  document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
  document.getElementById(`${tabName}-tab`).classList.add("active");
  if (button) button.classList.add("active");
}

async function fetchEntries(days, category) {
  return asList(await apiFetch(apiPath("pets", state.selectedPet, "analytics"), { query: { days, category } }));
}

/** Dashboard metric cards: analytics entries (30 days) plus note kinds from the notes list. */
export async function loadDashboard() {
  if (!state.selectedPet) return;
  const cards = document.querySelectorAll(".metric-card");
  cards.forEach((card) => replaceChildren(card.querySelector(".metric-value"), icon("fas fa-spinner fa-spin")));
  const [entriesRes, notesRes] = await Promise.allSettled([fetchEntries(30), apiFetch(apiPath("pets", state.selectedPet, "notes"), { query: { limit: 200 } })]);
  const entries = entriesRes.status === "fulfilled" ? entriesRes.value.map(entryFields) : [];
  const since = Date.now() - 30 * 86400000;
  const notes = notesRes.status === "fulfilled" ? asList(notesRes.value).filter((n) => (parseTimestamp(n.created_at) || new Date()).getTime() >= since) : [];
  if (entriesRes.status === "rejected") showNotification(`Could not load analytics: ${describeError(entriesRes.reason)}`, "error");

  const count = (cat) => entries.filter((e) => e.category === cat).length;
  const energy = entries.filter((e) => e.category === "energy_levels" && Number.isFinite(Number(e.level))).map((e) => Number(e.level));
  const values = {
    diet: count("diet"),
    exercise: count("exercise"),
    medication: count("medication"),
    daily_activity: notes.filter((n) => n.kind === "DAILY_ACTIVITY" || n.kind === "MIXED").length,
    medical_notes: notes.filter((n) => n.kind === "MEDICAL" || n.kind === "MIXED").length,
    energy_levels: energy.length ? (energy.reduce((a, b) => a + b, 0) / energy.length).toFixed(1) : "–",
  };
  cards.forEach((card) => {
    const v = values[card.dataset.category];
    card.querySelector(".metric-value").textContent = v === undefined ? "–" : String(v);
  });
}

export function getEntryDescription(entry) {
  const e = entryFields(entry);
  const join = (a) => (Array.isArray(a) && a.length ? a.join(", ") : "");
  switch (e.category) {
    case "diet":
      return `${e.food || "Food"} - ${e.type || "meal"}`;
    case "exercise":
      return `${e.type || "Exercise"}${e.duration ? ` for ${e.duration} minutes` : ""}`;
    case "medication":
      return `${e.name || "Medication"}${e.dosage ? ` - ${e.dosage}` : ""}`;
    case "grooming":
      return join(e.types) || "Grooming";
    case "energy_levels":
      return e.level ? `Energy level: ${e.level}/5` : "Energy logged";
    case "bowel_movements":
      return `${e.consistency || "Normal"} consistency`;
    case "exit_events":
      return `${e.type || "Exit"}${e.destination ? ` - ${e.destination}` : ""}`;
    case "weight":
      return e.value ? `Weight: ${e.value} ${e.unit || "lbs"}` : "Weight logged";
    case "sleep":
      return `Sleep${e.duration ? `: ${e.duration} hours` : ""}${e.quality ? ` - ${e.quality} quality` : ""}`;
    case "mood":
      return `Mood${e.level ? ` level: ${e.level}/5` : ""}${join(e.behavior) ? ` - ${join(e.behavior)}` : ""}`;
    default:
      return e.summary || e.text || e.notes || "Activity logged";
  }
}

export async function loadRecentEntries() {
  if (!state.selectedPet) return;
  const container = document.getElementById("recent-entries");
  try {
    const entries = (await fetchEntries(7)).map(entryFields);
    if (entries.length === 0) {
      replaceChildren(
        container,
        el("div", { style: "text-align: center; color: #7f8c8d; padding: 40px;" }, icon("fas fa-clock"), el("p", { text: "No entries in the last 7 days. Start tracking above!" }))
      );
      return;
    }
    entries.sort((a, b) => (parseTimestamp(entryTime(b)) || 0) - (parseTimestamp(entryTime(a)) || 0));
    replaceChildren(
      container,
      entries.slice(0, 10).map((entry) =>
        el(
          "div",
          { class: "recent-entry" },
          el(
            "div",
            { class: "entry-content" },
            el("div", { class: "entry-category", text: String(entry.category || "entry").replace(/_/g, " ") }),
            el("div", { class: "entry-description", text: getEntryDescription(entry) }),
            el("div", { class: "entry-time", text: formatDateTime(entryTime(entry)) })
          ),
          el("div", { class: "entry-icon", text: ICONS[entry.category] || "📝" })
        )
      )
    );
  } catch (err) {
    replaceChildren(container, el("div", { class: "status-message error", style: "display:block", text: `Could not load entries: ${describeError(err)}` }));
  }
}
