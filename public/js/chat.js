// public/js/chat.js: assistant chat. POST /api/pets/{id}/chat {message, tz} ->
// {answer, status: answered|not_in_records|out_of_scope, citations: [{id, date, source, snippet}],
//  chart: null|{type, title, data}, mode}. Answers are rendered through parseMarkdown (which
// escapes first); citations and everything else are inserted as text.
import { apiFetch, apiPath, browserTimeZone, describeError } from "./api.js";
import { el, icon, replaceChildren, showNotification, showLoadingState, hideLoadingState, updateCharacterCount, formatDate } from "./dom.js";
import { parseMarkdown } from "./markdown.js";
import { state } from "./state.js";
import { responseModeTag } from "./banner.js";
import { renderChatChart } from "./charts.js";
import { loadInsights } from "./insights.js";

const STATUS_LABELS = {
  answered: null,
  not_in_records: { text: "Not in your records", cls: "pill-warning", hint: "I couldn't find this in your pet's notes, records or tracking data." },
  out_of_scope: { text: "Out of scope", cls: "pill-muted", hint: "This question is outside what the assistant can answer from your pet's records." },
};

function container() {
  return document.getElementById("chat-container");
}

function scrollToEnd() {
  const c = container();
  c.scrollTop = c.scrollHeight;
}

function avatar(emoji, bg) {
  return el("div", { class: "chat-avatar", style: `background: ${bg};`, text: emoji });
}

/** Append a chat bubble. User text is plain text; assistant text goes through parseMarkdown. */
export function addChatMessage(message, sender, { loading = false } = {}) {
  const bubble = el("div", { class: `chat-bubble ${sender}${loading ? " loading" : ""}` });
  if (sender === "assistant" && !loading) bubble.innerHTML = parseMarkdown(message);
  else bubble.textContent = message;
  if (loading) bubble.prepend(icon("fas fa-spinner fa-spin"), " ");

  const row =
    sender === "user"
      ? el("div", { class: "chat-row user" }, bubble, avatar("👤", "#667eea"))
      : el("div", { class: "chat-row assistant" }, avatar("🤖", "linear-gradient(135deg, #667eea, #764ba2)"), bubble);
  if (loading) row.classList.add("loading-message");
  container().appendChild(row);
  scrollToEnd();
  return bubble;
}

export function removeLoadingMessage() {
  const loading = container().querySelector(".loading-message");
  if (loading) loading.remove();
}

function renderCitations(citations) {
  if (!Array.isArray(citations) || citations.length === 0) return null;
  return el(
    "div",
    { class: "chat-citations" },
    el("div", { class: "chat-citations-title" }, icon("fas fa-book"), " Sources"),
    el(
      "ol",
      {},
      citations.map((c) =>
        el(
          "li",
          { title: c.id ? `Record ${c.id}` : "" },
          el("span", { class: "citation-meta", text: [formatDate(c.date), c.source].filter(Boolean).join(" · ") }),
          c.snippet ? el("span", { class: "citation-snippet", text: ` “${c.snippet}”` }) : null
        )
      )
    )
  );
}

/** Render a full chat response (answer + status + citations + optional chart + mode). */
export function renderChatResponse(data) {
  const bubble = addChatMessage(data.answer || "", "assistant");
  const status = STATUS_LABELS[data.status];
  const meta = el("div", { class: "chat-meta" }, status ? el("span", { class: `pill ${status.cls}`, text: status.text, title: status.hint }) : null, responseModeTag(data.mode));
  if (meta.childNodes.length) bubble.prepend(meta);
  const cites = renderCitations(data.citations);
  if (cites) bubble.appendChild(cites);
  if (data.chart) {
    const chartBox = el("div", { class: "chat-chart" });
    bubble.appendChild(chartBox);
    if (!renderChatChart(chartBox, data.chart)) chartBox.replaceWith(el("div", { class: "muted", text: "No chartable data for this question." }));
  }
  scrollToEnd();
}

export async function sendChatMessage() {
  const input = document.getElementById("chat-input");
  const sendButton = document.getElementById("send-chat");
  const message = input.value.trim();
  if (!message) {
    showNotification("Please enter a message first", "warning");
    input.focus();
    return;
  }
  if (!state.selectedPet) {
    showNotification("Please select a pet first", "warning");
    return;
  }

  showLoadingState(sendButton, "Sending");
  input.disabled = true;
  addChatMessage(message, "user");
  input.value = "";
  updateCharacterCount("chat-input", "char-count", 1000);
  addChatMessage("Looking through your pet's records…", "assistant", { loading: true });

  try {
    const data = await apiFetch(apiPath("pets", state.selectedPet, "chat"), { json: { message, tz: browserTimeZone() } });
    removeLoadingMessage();
    renderChatResponse(data || {});
    if (!state.insightsLoaded) loadInsights();
  } catch (err) {
    removeLoadingMessage();
    const why = err && err.status === 503 ? "the assistant is unavailable right now. Please try again in a moment" : describeError(err);
    addChatMessage(`Sorry, I couldn't answer that: ${why}`, "assistant");
  } finally {
    hideLoadingState(sendButton);
    input.disabled = false;
    input.focus();
  }
}

export function showQuickQuestions() {
  const loading = document.getElementById("quick-questions-loading");
  const buttons = document.getElementById("quick-questions-buttons");
  if (loading) loading.style.display = "none";
  if (buttons) buttons.style.display = "block";
}

export function hideQuickQuestions() {
  const loading = document.getElementById("quick-questions-loading");
  const buttons = document.getElementById("quick-questions-buttons");
  if (buttons) buttons.style.display = "none";
  if (loading) {
    replaceChildren(loading, icon("fas fa-info-circle"), " Please add a pet first to use quick questions");
    loading.style.display = "block";
  }
}

export function askQuickQuestion(question) {
  if (!state.selectedPet) {
    showNotification("Please select a pet first", "error");
    return;
  }
  document.getElementById("chat-input").value = question;
  sendChatMessage();
}

/** Reset the chat, insights and search panels when the selected pet changes. */
export function resetAssistantState() {
  state.insightsLoaded = false;
  const welcome = document.getElementById("chat-welcome");
  replaceChildren(container(), welcome ? welcome.content.cloneNode(true) : null);
  const chatInput = document.getElementById("chat-input");
  if (chatInput) chatInput.value = "";
  updateCharacterCount("chat-input", "char-count", 1000);
  const summary = document.getElementById("ai-health-summary");
  const placeholder = document.getElementById("insights-placeholder");
  if (summary && placeholder) replaceChildren(summary, placeholder.content.cloneNode(true));
  const search = document.getElementById("knowledge-search");
  if (search) search.value = "";
  const results = document.getElementById("knowledge-results");
  const resultsPlaceholder = document.getElementById("knowledge-placeholder");
  if (results && resultsPlaceholder) replaceChildren(results, resultsPlaceholder.content.cloneNode(true));
}

export function initChat() {
  const input = document.getElementById("chat-input");
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage();
    }
  });
  input.addEventListener("input", () => updateCharacterCount("chat-input", "char-count", 1000));
  document.getElementById("send-chat").addEventListener("click", sendChatMessage);
  document.querySelectorAll(".quick-question-btn[data-question]").forEach((btn) => btn.addEventListener("click", () => askQuickQuestion(btn.dataset.question)));
}
