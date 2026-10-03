// public/js/banner.js: demo/live mode banner and the per-feature Demo/Live badges, driven by
// GET /api/health -> {mode: "demo"|"live"|"mixed", llm, stt, features: {name: {provider, mode}}}.
import { apiFetch } from "./api.js";
import { el } from "./dom.js";
import { state } from "./state.js";

export const FEATURE_LABELS = {
  notes: "Notes",
  chat: "Assistant",
  pdf_summary: "PDF summaries",
  insights: "Insights",
  voice: "Voice transcription",
};

export async function loadHealth() {
  try {
    state.health = await apiFetch("/api/health", { auth: false });
  } catch (err) {
    console.warn("Could not load /api/health:", err);
    state.health = null;
  }
  return state.health;
}

function feature(name) {
  const f = state.health && state.health.features && state.health.features[name];
  if (!f) return null;
  return typeof f === "string" ? { mode: f, provider: f === "demo" ? "fake" : "live" } : f;
}

/** "demo" | "live" | null for one feature. */
export function featureMode(name) {
  const f = feature(name);
  return f ? f.mode : null;
}

function liveProviders(health) {
  const names = new Set();
  for (const f of Object.values(health.features || {})) {
    if (f && f.mode === "live" && f.provider) names.add(f.provider);
  }
  if (!names.size) {
    if (health.llm && health.llm !== "fake") names.add(health.llm);
    if (health.stt && health.stt !== "fake") names.add(health.stt);
  }
  return Array.from(names).join(", ") || "live provider";
}

export function bannerText(health) {
  if (!health) return null;
  if (health.mode === "demo") return "Demo mode: AI responses are simulated (fake provider). No data leaves this machine.";
  if (health.mode === "live") return `Live AI: ${liveProviders(health)} (calls are billed)`;
  const demoFeatures = Object.entries(health.features || {})
    .filter(([, f]) => f && f.mode === "demo")
    .map(([k]) => FEATURE_LABELS[k] || k);
  return `Live AI: ${liveProviders(health)} (calls are billed). Simulated: ${demoFeatures.join(", ") || "none"}.`;
}

/** Insert (or update) the banner at the top of <body>. */
export function renderBanner(health = state.health) {
  const text = bannerText(health);
  let banner = document.getElementById("demo-banner");
  if (!text) {
    if (banner) banner.remove();
    return;
  }
  if (!banner) {
    banner = el("div", { id: "demo-banner", attrs: { role: "status" } });
    document.body.prepend(banner);
  }
  banner.className = `demo-banner mode-${health.mode}`;
  banner.textContent = text;
}

/** Fill every <span class="mode-badge" data-feature="..."> with Demo / Live. */
export function applyModeBadges(root = document) {
  root.querySelectorAll("[data-feature]").forEach((node) => {
    const f = feature(node.dataset.feature);
    if (!f) {
      node.hidden = true;
      return;
    }
    node.hidden = false;
    node.className = `mode-badge ${f.mode === "live" ? "live" : "demo"}`;
    node.textContent = f.mode === "live" ? `Live · ${f.provider}` : "Demo";
    node.title =
      f.mode === "live"
        ? `${FEATURE_LABELS[node.dataset.feature] || node.dataset.feature}: real AI provider (${f.provider}), calls are billed`
        : `${FEATURE_LABELS[node.dataset.feature] || node.dataset.feature}: simulated by the deterministic fake provider`;
  });
}

/** Small tag for one AI response, from its own `mode` field. */
export function responseModeTag(mode) {
  if (mode !== "demo" && mode !== "live") return null;
  return el("span", {
    class: `mode-badge ${mode}`,
    text: mode === "live" ? "Live AI" : "Simulated",
    title: mode === "live" ? "Produced by a real AI provider" : "Produced by the deterministic fake provider (demo mode)",
  });
}

export async function initBanner() {
  const health = await loadHealth();
  renderBanner(health);
  applyModeBadges();
  return health;
}
