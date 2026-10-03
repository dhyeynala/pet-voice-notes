// public/js/insights.js: GET /api/pets/{id}/insights?tz= -> {facts, alerts, headline, mode}.
// Facts and alerts are computed by code on the backend; there is no "health score".
import { apiFetch, apiPath, browserTimeZone, describeError } from "./api.js";
import { el, icon, replaceChildren } from "./dom.js";
import { state, selectedPetName } from "./state.js";
import { responseModeTag } from "./banner.js";

function itemText(item) {
  if (item === null || item === undefined) return "";
  if (typeof item === "string") return item;
  return item.text || item.message || item.title || item.fact || item.alert || JSON.stringify(item);
}

function itemLevel(item) {
  return (item && typeof item === "object" && (item.level || item.severity)) || "";
}

export function renderInsights(data, { compact = false } = {}) {
  const facts = Array.isArray(data.facts) ? data.facts : [];
  const alerts = Array.isArray(data.alerts) ? data.alerts : [];
  const wrap = el("div", { class: "insights" });
  wrap.appendChild(
    el(
      "div",
      { class: "insights-header" },
      el("span", { class: "insights-headline", text: data.headline || `No headline for ${selectedPetName()} yet.` }),
      responseModeTag(data.mode)
    )
  );
  if (alerts.length) {
    wrap.appendChild(
      el(
        "ul",
        { class: "insights-alerts" },
        alerts.map((a) => el("li", { class: `alert-${itemLevel(a) || "info"}` }, icon("fas fa-exclamation-triangle"), ` ${itemText(a)}`))
      )
    );
  }
  if (facts.length) {
    wrap.appendChild(el("ul", { class: "insights-facts" }, facts.slice(0, compact ? 4 : facts.length).map((f) => el("li", { text: itemText(f) }))));
  }
  if (!alerts.length && !facts.length) wrap.appendChild(el("div", { class: "insights-empty", text: "Not enough data yet. Add notes or tracking entries to see insights." }));
  return wrap;
}

async function fetchInsights() {
  return apiFetch(apiPath("pets", state.selectedPet, "insights"), { query: { tz: browserTimeZone() } });
}

/** Assistant section card. */
export async function loadInsights() {
  const box = document.getElementById("ai-health-summary");
  if (!box || !state.selectedPet) return;
  state.insightsLoaded = true;
  replaceChildren(box, el("div", { style: "text-align:center;" }, icon("fas fa-spinner fa-spin"), " Loading insights…"));
  try {
    replaceChildren(box, renderInsights((await fetchInsights()) || {}));
  } catch (err) {
    state.insightsLoaded = false;
    replaceChildren(box, el("div", { text: `Insights are unavailable: ${describeError(err)}` }));
  }
}

/** Analytics section "Today's highlights" card. */
export async function loadHighlights() {
  const box = document.getElementById("daily-headlines");
  if (!box || !state.selectedPet) return;
  replaceChildren(box, el("div", { style: "text-align:center; color: rgba(255,255,255,0.85);" }, icon("fas fa-spinner fa-spin"), " Loading highlights…"));
  try {
    replaceChildren(box, renderInsights((await fetchInsights()) || {}, { compact: true }));
  } catch (err) {
    replaceChildren(box, el("div", { style: "text-align:center;" }, icon("fas fa-exclamation-triangle"), ` Could not load highlights: ${describeError(err)}`));
  }
}

export function initInsights() {
  const refresh = document.getElementById("refresh-insights-btn");
  if (refresh) refresh.addEventListener("click", loadInsights);
  const highlights = document.getElementById("refresh-highlights-btn");
  if (highlights) highlights.addEventListener("click", loadHighlights);
}
