// public/js/knowledge.js: search the selected pet's own records. Uses the grounded chat route
// (POST /api/pets/{id}/chat {message, tz}); the old static "veterinary knowledge base"
// (/knowledge_search) is gone. Results are the cited records, rendered as text.
import { apiFetch, apiPath, browserTimeZone, describeError } from "./api.js";
import { el, icon, formatDate, replaceChildren, showNotification } from "./dom.js";
import { state } from "./state.js";

const EMPTY_HINT = {
  not_in_records: "Nothing in your pet's records matches this.",
  out_of_scope: "This is outside what the records can answer. For medical advice or dosing, ask your veterinarian.",
};

function renderCitation(c) {
  const meta = [formatDate(c.date), c.source].filter(Boolean).join(" · ");
  return el(
    "div",
    { class: "knowledge-result" },
    el("h4", { text: meta || "Record" }),
    el("p", { text: c.snippet || "" })
  );
}

/** Result nodes for a chat reply {answer, status, citations}. */
export function knowledgeResults(reply, query) {
  const citations = (reply && Array.isArray(reply.citations) && reply.citations) || [];
  const status = (reply && reply.status) || "not_in_records";
  if (status === "answered" && citations.length) {
    return [el("p", { class: "knowledge-answer", text: reply.answer || "" }), ...citations.map(renderCitation)];
  }
  const hint = EMPTY_HINT[status] || `No results for "${query}".`;
  return [el("div", { style: "text-align:center; color:#7f8c8d;" }, icon("fas fa-search"), el("p", { text: hint }))];
}

export async function searchKnowledge() {
  const query = document.getElementById("knowledge-search").value.trim();
  const results = document.getElementById("knowledge-results");
  if (!query) return showNotification("Please enter a search query", "error");
  if (!state.selectedPet) return showNotification("Please select a pet first", "error");
  replaceChildren(results, el("div", { style: "text-align:center; color:#667eea;" }, icon("fas fa-spinner fa-spin"), el("p", { text: "Searching your pet's records…" })));
  try {
    const reply = await apiFetch(apiPath("pets", state.selectedPet, "chat"), { json: { message: query, tz: browserTimeZone() } });
    replaceChildren(results, knowledgeResults(reply, query));
  } catch (err) {
    replaceChildren(results, el("div", { style: "text-align:center; color:#e53e3e;" }, icon("fas fa-exclamation-triangle"), el("p", { text: `Search is unavailable: ${describeError(err)}` })));
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
