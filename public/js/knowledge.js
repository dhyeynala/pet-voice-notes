// public/js/knowledge.js: veterinary knowledge-base search (legacy POST
// /api/pets/{id}/knowledge_search, kept while the backend still serves it). Results are rendered
// as text, and the old "Confidence %" (a raw keyword score, review M8) is no longer shown.
import { apiFetch, apiPath, describeError } from "./api.js";
import { el, icon, replaceChildren, showNotification } from "./dom.js";
import { state } from "./state.js";

function renderResult(r) {
  const meta = [r.category ? `Category: ${r.category}` : null, r.severity ? `Severity: ${r.severity}` : null].filter(Boolean).join(" | ");
  return el(
    "div",
    { class: "knowledge-result" },
    el("h4", { text: r.title || "Untitled" }),
    el("p", { text: r.content || "" }),
    meta ? el("div", { class: "knowledge-meta", text: meta }) : null,
    Array.isArray(r.symptoms) && r.symptoms.length ? el("div", { class: "knowledge-symptoms", text: `Related symptoms: ${r.symptoms.join(", ")}` }) : null
  );
}

export async function searchKnowledge() {
  const query = document.getElementById("knowledge-search").value.trim();
  const results = document.getElementById("knowledge-results");
  if (!query) return showNotification("Please enter a search query", "error");
  if (!state.selectedPet) return showNotification("Please select a pet first", "error");
  replaceChildren(results, el("div", { style: "text-align:center; color:#667eea;" }, icon("fas fa-spinner fa-spin"), el("p", { text: "Searching the knowledge base…" })));
  try {
    const data = await apiFetch(apiPath("pets", state.selectedPet, "knowledge_search"), { json: { query } });
    const list = (data && (data.results || (Array.isArray(data) ? data : null))) || [];
    replaceChildren(
      results,
      list.length ? list.map(renderResult) : el("div", { style: "text-align:center; color:#7f8c8d;" }, icon("fas fa-search"), el("p", { text: `No results for "${query}".` }))
    );
  } catch (err) {
    replaceChildren(results, el("div", { style: "text-align:center; color:#e53e3e;" }, icon("fas fa-exclamation-triangle"), el("p", { text: `Knowledge search is unavailable: ${describeError(err)}` })));
  }
}

export function initKnowledge() {
  const input = document.getElementById("knowledge-search");
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      searchKnowledge();
    }
  });
  document.getElementById("knowledge-search-btn").addEventListener("click", searchKnowledge);
}
