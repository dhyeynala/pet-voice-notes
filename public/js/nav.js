// public/js/nav.js: Section navigation (sidebar tabs + URL hash).
import { loadMarkdown } from "./notes.js";
import { loadDashboard, loadRecentEntries } from "./analytics.js";
import { updateCharts } from "./charts.js";

// Navigation functionality
window.showSection = function(sectionName) {
  // Update nav items
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.remove('active');
  });
  
  // Find and activate the correct nav item
  const navItems = document.querySelectorAll('.nav-item');
  navItems.forEach(item => {
    if ((sectionName === 'add-pet' && item.textContent.includes('Add a Pet')) ||
        (sectionName === 'assistant' && item.textContent.includes('Pet Health Assistant')) ||
        (sectionName === 'recording' && item.textContent.includes('Voice Recording')) ||
        (sectionName === 'notes' && item.textContent.includes('Notes & Files')) ||
        (sectionName === 'analytics' && item.textContent.includes('Analytics')) ||
        (sectionName === 'tracking' && item.textContent.includes('Tracking'))) {
      item.classList.add('active');
    }
  });

  // Show/hide pet selector card based on section
  const petSelectorCard = document.getElementById('pet-selector-card');
  if (sectionName === 'add-pet') {
    petSelectorCard.style.display = 'none';
  } else {
    petSelectorCard.style.display = 'block';
  }

  // Update sections
  document.querySelectorAll('.section').forEach(section => {
    section.classList.remove('active');
  });

  if (sectionName === 'add-pet') {
    document.getElementById('add-pet-section').classList.add('active');
    window.location.hash = 'add-pet';
  } else if (sectionName === 'recording') {
    document.getElementById('recording-section').classList.add('active');
    window.location.hash = 'recording';
  } else if (sectionName === 'notes') {
    document.getElementById('notes-section').classList.add('active');
    loadMarkdown(); // Load notes when switching to notes section
    window.location.hash = 'notes';
  } else if (sectionName === 'analytics') {
    document.getElementById('analytics-section').classList.add('active');
    loadDashboard(); // Load dashboard when switching to analytics
    updateCharts(); // Update charts when switching to analytics
    generateDailyHeadlines(); // Generate today's headlines
    window.location.hash = 'analytics';
  } else if (sectionName === 'tracking') {
    document.getElementById('tracking-section').classList.add('active');
    loadRecentEntries(); // Load recent entries for tracking
    window.location.hash = 'tracking';
  } else if (sectionName === 'assistant') {
    document.getElementById('assistant-section').classList.add('active');
    // Don't load assistant data automatically - only when user interacts
    window.location.hash = 'assistant';
  }
};

// Handle URL hash navigation
function handleHashNavigation() {
  const hash = window.location.hash.substring(1);
  if (hash === 'add-pet') {
    showSection('add-pet');
  } else if (hash === 'notes') {
    showSection('notes');
  } else if (hash === 'analytics') {
    showSection('analytics');
  } else if (hash === 'tracking') {
    showSection('tracking');
  } else if (hash === 'recording') {
    showSection('recording');
  } else {
    showSection('assistant'); // Default to assistant
  }
}

// Listen for hash changes
window.addEventListener('hashchange', handleHashNavigation);

export { handleHashNavigation };
