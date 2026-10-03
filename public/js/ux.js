// public/js/ux.js: small progressive UX enhancements: inline validation hints, the contextual
// help button and keyboard shortcuts. (The old fake "auto-saved to cloud" indicator, the search
// "suggestions" built with innerHTML, the global window.fetch override and the cache badge were
// removed: they were misleading or unsafe and apiFetch now owns error reporting.)
import { el, icon, showNotification } from "./dom.js";
import { activeSection } from "./nav.js";
import { sendChatMessage } from "./chat.js";

function validateField(input) {
  const hint = input.parentElement.querySelector(".validation-message");
  if (!hint) return true;
  const invalid = input.required && !input.value.trim();
  hint.textContent = invalid ? "This field is required" : "";
  hint.classList.toggle("show", invalid);
  hint.classList.remove("success");
  input.classList.toggle("error", invalid);
  return !invalid;
}

function setupSmartValidation() {
  document.querySelectorAll("form input[required], form select[required], form textarea[required]").forEach((input) => {
    if (input.dataset.validationSetup) return;
    input.dataset.validationSetup = "true";
    if (!input.parentElement.querySelector(".validation-message")) {
      input.parentElement.style.position = "relative";
      input.parentElement.appendChild(el("div", { class: "validation-message" }));
    }
    input.addEventListener("blur", () => validateField(input));
    input.addEventListener("input", () => input.classList.contains("error") && validateField(input));
  });
}

const HELP = {
  "add-pet": "Fill out your pet's basic information. Name and animal type are required.",
  assistant: "Ask questions about your pet. Answers cite the notes and records they come from, and say so when the answer isn't in your records.",
  recording: "Record a voice note (up to 60 seconds) or use a sample recording. The transcript is analyzed like a typed note.",
  notes: "Add typed notes and upload PDF vet records. Urgent notes are flagged with a red banner.",
  tracking: "Log meals, exercise, medication and more. Entries feed the analytics charts.",
  analytics: "Charts and highlights computed from your tracking entries and notes.",
};

function showContextualHelp() {
  showNotification(HELP[activeSection()] || "Use the menu to move between sections. Press Ctrl+/ for help.", "info", 6000);
}

function setupContextualHelp() {
  if (document.querySelector(".contextual-help")) return;
  const button = el(
    "button",
    { type: "button", class: "contextual-help", attrs: { "aria-label": "Help for this page" } },
    icon("fas fa-question"),
    el("div", { class: "help-tooltip", text: "Get help with this page" })
  );
  button.addEventListener("click", showContextualHelp);
  document.body.appendChild(button);
}

function setupKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && document.activeElement && document.activeElement.id === "chat-input") {
      e.preventDefault();
      sendChatMessage();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === "/") {
      e.preventDefault();
      showContextualHelp();
    }
    if (e.key === "Escape") {
      document.querySelectorAll(".notification-toast").forEach((n) => n.classList.remove("show"));
    }
  });
}

export function initializeUXEnhancements() {
  setupSmartValidation();
  setupContextualHelp();
  setupKeyboardShortcuts();
}
