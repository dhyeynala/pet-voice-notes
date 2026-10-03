// public/js/main.js: entry point for main.html. Requires a demo session, renders the banner and
// user menu, wires every module's event handlers, then loads the user's pets.
import { requireSession, refreshMe, renderUserMenu } from "./auth.js";
import { initBanner } from "./banner.js";
import { initNav, handleHashNavigation } from "./nav.js";
import { initPets, loadPets } from "./pets.js";
import { initChat, resetAssistantState } from "./chat.js";
import { initNotes } from "./notes.js";
import { initRecords } from "./records.js";
import { initRecorder } from "./recorder.js";
import { setupAnalyticsFormHandlers } from "./analytics.js";
import { initInsights } from "./insights.js";
import { initKnowledge } from "./knowledge.js";
import { initializeUXEnhancements } from "./ux.js";
import { describeError } from "./api.js";
import { showNotification, updateCharacterCount } from "./dom.js";

async function boot() {
  if (!requireSession()) return;

  initNav();
  initPets();
  initChat();
  initNotes();
  initRecords();
  initRecorder();
  setupAnalyticsFormHandlers();
  initInsights();
  initKnowledge();
  initializeUXEnhancements();
  document.getElementById("pet-input-text").addEventListener("input", () => updateCharacterCount("pet-input-text", "text-char-count", 2000));
  resetAssistantState();

  const healthReady = initBanner();
  try {
    await refreshMe(); // validates the token (a 401 sends us back to the login page)
  } catch (err) {
    if (err.status !== 401) showNotification(`Could not verify your session: ${describeError(err)}`, "error");
    if (err.status === 401) return;
  }
  renderUserMenu();
  await healthReady;
  await loadPets();
  handleHashNavigation();
}

boot();
