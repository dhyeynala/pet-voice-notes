// public/js/nav.js: section navigation (header tabs + URL hash).
import { state } from "./state.js";
import { loadNotes } from "./notes.js";
import { loadRecords } from "./records.js";
import { loadDashboard, loadRecentEntries } from "./analytics.js";
import { updateCharts } from "./charts.js";
import { loadHighlights, loadInsights } from "./insights.js";
import { loadSamples } from "./recorder.js";

export const SECTIONS = ["add-pet", "assistant", "recording", "notes", "tracking", "analytics"];

export function activeSection() {
  const node = document.querySelector(".section.active");
  return node ? node.id.replace(/-section$/, "") : null;
}

/** Load the data a section shows for the selected pet. */
export function refreshSection(name = activeSection()) {
  if (!state.selectedPet) return;
  if (name === "notes") {
    loadNotes();
    loadRecords();
  } else if (name === "analytics") {
    loadDashboard();
    updateCharts();
    loadHighlights();
  } else if (name === "tracking") {
    loadRecentEntries();
  } else if (name === "assistant") {
    if (!state.insightsLoaded) loadInsights();
  } else if (name === "recording") {
    loadNotes({ targetId: "voice-recent-notes", limit: 5 });
  }
}

export function showSection(name) {
  if (!SECTIONS.includes(name)) name = "assistant";
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.section === name);
  });
  const petSelectorCard = document.getElementById("pet-selector-card");
  if (petSelectorCard) petSelectorCard.style.display = name === "add-pet" ? "none" : "block";
  document.querySelectorAll(".section").forEach((section) => section.classList.remove("active"));
  document.getElementById(`${name}-section`).classList.add("active");
  if (window.location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  if (name === "recording") loadSamples();
  refreshSection(name);
}

export function handleHashNavigation() {
  showSection(window.location.hash.substring(1) || "assistant");
}

export function initNav() {
  document.querySelectorAll(".nav-item[data-section]").forEach((item) => {
    item.addEventListener("click", () => showSection(item.dataset.section));
    item.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        showSection(item.dataset.section);
      }
    });
  });
  window.addEventListener("hashchange", handleHashNavigation);
}
