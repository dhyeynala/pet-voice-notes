// public/js/main.js: Entry point for main.html: wires modules together and boots the app.
import { state } from "./state.js";
import { handleHashNavigation } from "./nav.js";
import { loadPets } from "./pets.js";
import { setupAnalyticsFormHandlers } from "./analytics.js";
import { auth, onAuthStateChanged } from "./auth.js";
import "./markdown.js";
import "./knowledge.js";
import "./recorder.js";
import "./notes.js";
import "./chat.js";
import "./ux.js";
import "./cache.js";

// Enable Enter key for chat input and form handlers
document.addEventListener('DOMContentLoaded', function() {
  const chatInput = document.getElementById('chat-input');
  const knowledgeSearch = document.getElementById('knowledge-search');
  const addPetForm = document.getElementById('add-pet-form');
  
  if (chatInput) {
    chatInput.addEventListener('keypress', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });
  }
  
  if (knowledgeSearch) {
    knowledgeSearch.addEventListener('keypress', function(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        searchKnowledge();
      }
    });
  }
  
  if (addPetForm) {
    addPetForm.addEventListener('submit', handleAddPetForm);
  }
});

// Authentication
onAuthStateChanged(auth, user => {
  if (!user) {
    window.location.href = "/index.html";
  } else {
    state.currentUser = user;
    loadPets().then(() => {
      // After pets are loaded, handle navigation
      handleHashNavigation();
      // Assistant data will be loaded on-demand when user interacts
    });
    setupAnalyticsFormHandlers();
  }
});
