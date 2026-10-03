// public/js/notes.js: Typed smart notes and page notes.
import { state } from "./state.js";
import { loadDashboard } from "./analytics.js";
import { updateCharts } from "./charts.js";
import { showNotification } from "./dom.js";

// Smart Text Input Function with Classification
window.submitPetText = async function() {
  if (!state.currentUser) return alert("User not authenticated");
  const petId = document.getElementById("pet-select").value;
  if (!petId) return alert("Please select a pet first");

  const textInput = document.getElementById("pet-input-text");
  const inputText = textInput.value.trim();
  const statusElement = document.getElementById("pet-input-status");
  const loadingOverlay = document.getElementById("loading-overlay");

  if (!inputText) {
    statusElement.textContent = "⚠️ Please enter some text first";
    statusElement.className = "status-message error";
    setTimeout(() => statusElement.style.display = "none", 3000);
    return;
  }

  try {
    // Show processing state
    statusElement.textContent = "🔄 Processing your note with AI...";
    statusElement.className = "status-message processing";
    statusElement.style.display = "block";
    loadingOverlay.style.display = "flex";

    const response = await fetch(`/api/pets/${petId}/textinput`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input: inputText })
    });

    const data = await response.json();
    loadingOverlay.style.display = "none";

    if (data.status === "success") {
      // Display the input text and AI analysis in the output area
      const outputElement = document.getElementById("pet-text-output");
      const textContentElement = document.getElementById("pet-text-content");
      const textSummaryElement = document.getElementById("pet-text-summary");
      const textTypeBadge = document.getElementById("pet-text-type-badge");
      
      if (textContentElement && textSummaryElement && textTypeBadge) {
        textContentElement.textContent = inputText;
        textSummaryElement.textContent = data.summary;
        
        // Show content type badge with enhanced styling
        const contentType = data.content_type || "MIXED";
        const confidence = ((data.confidence || 0.5) * 100).toFixed(0);
        const keywords = data.keywords || [];
        
        let badgeClass = "badge-mixed";
        let badgeIcon = "fas fa-brain";
        let badgeText = contentType;
        
        if (contentType === "MEDICAL") {
          badgeClass = "badge-medical";
          badgeIcon = "fas fa-heartbeat";
          badgeText = "Health & Medical";
        } else if (contentType === "DAILY_ACTIVITY") {
          badgeClass = "badge-activity";
          badgeIcon = "fas fa-heart";
          badgeText = "Daily Life & Activities";
        } else {
          badgeText = "Mixed Content";
        }
        
        textTypeBadge.innerHTML = `
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
            <span class="content-type-badge ${badgeClass}">
              <i class="${badgeIcon}"></i> ${badgeText}
            </span>
            <small style="color: #666; font-size: 0.85em;">Confidence: ${confidence}%</small>
          </div>
          ${keywords.length > 0 ? `<div style="font-size: 0.85em; color: #666;"><strong>Keywords:</strong> ${keywords.join(', ')}</div>` : ''}
        `;
        textTypeBadge.style.display = "block";
        
        // Show the output area
        if (outputElement) {
          outputElement.classList.add("has-content");
        }
      }
      
      // Clear the input
      textInput.value = "";
      
      // Show success message
      statusElement.textContent = `${badgeText} processed successfully!`;
      statusElement.className = "status-message success";
      statusElement.style.display = "block";
      
      // Auto-hide status after 5 seconds
      setTimeout(() => {
        statusElement.style.display = "none";
      }, 5000);

      // Show notification
      showNotification(`📝 ${badgeText} note added successfully!`, 'success', 3000);

      // If we're in analytics section, refresh the dashboard
      const currentSection = document.querySelector('.section.active');
      if (currentSection && currentSection.id === 'analytics-section') {
        setTimeout(() => {
          loadDashboard();
          updateCharts();
        }, 1000);
      }

    } else {
      statusElement.textContent = `Error: ${data.message || "Failed to process note"}`;
      statusElement.className = "status-message error";
      statusElement.style.display = "block";
      setTimeout(() => statusElement.style.display = "none", 5000);
    }

  } catch (error) {
    console.error('Error submitting text:', error);
    loadingOverlay.style.display = "none";
    statusElement.textContent = "Network error. Please try again.";
    statusElement.className = "status-message error";
    statusElement.style.display = "block";
    setTimeout(() => statusElement.style.display = "none", 5000);
  }
};

// Notes functions  
async function loadMarkdown() {
  if (!state.selectedPet) return;
  
  try {
    const response = await fetch('/api/markdown');
    const data = await response.json();
    
    if (data.content) {
      document.getElementById('markdown-content').innerHTML = data.content;
    }
  } catch (error) {
    console.error('Error loading notes:', error);
  }
}

export { loadMarkdown };
