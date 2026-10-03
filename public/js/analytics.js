// public/js/analytics.js: Tracking forms, dashboard metrics, recent entries and daily headlines.
import { state } from "./state.js";
import { setupPdfForm } from "./records.js";
import { updateCharts } from "./charts.js";
import { showNotification } from "./dom.js";

// Analytics form handlers
function setupAnalyticsFormHandlers() {
  console.log("Setting up analytics form handlers...");
  
  setupPdfForm();

  
  // Set default times for forms
  const now = new Date();
  document.getElementById("diet-time").value = now.toTimeString().slice(0, 5);
  document.getElementById("medication-time").value = now.toTimeString().slice(0, 5);
  document.getElementById("bowel-time").value = now.toTimeString().slice(0, 5);
  
  // Diet form
  const dietForm = document.getElementById("diet-form");
  if (dietForm) {
    dietForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = {
        food: document.getElementById("diet-food").value,
        quantity: document.getElementById("diet-quantity").value,
        time: document.getElementById("diet-time").value,
        type: document.getElementById("diet-type").value,
        notes: document.getElementById("diet-notes").value
      };
      await submitAnalyticsForm(formData, "diet");
      dietForm.reset();
    });
  }

  // Exercise form
  const exerciseForm = document.getElementById("exercise-form");
  if (exerciseForm) {
    exerciseForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = {
        type: document.getElementById("exercise-type").value,
        duration: parseInt(document.getElementById("exercise-duration").value),
        intensity: document.getElementById("exercise-intensity").value,
        location: document.getElementById("exercise-location").value,
        notes: document.getElementById("exercise-notes").value
      };
      await submitAnalyticsForm(formData, "exercise");
      exerciseForm.reset();
    });
  }

  // Medication form
  const medicationForm = document.getElementById("medication-form");
  if (medicationForm) {
    medicationForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = {
        name: document.getElementById("medication-name").value,
        dosage: document.getElementById("medication-dosage").value,
        time: document.getElementById("medication-time").value,
        frequency: document.getElementById("medication-frequency").value,
        purpose: document.getElementById("medication-purpose").value
      };
      await submitAnalyticsForm(formData, "medication");
      medicationForm.reset();
    });
  }

  // Grooming form
  const groomingForm = document.getElementById("grooming-form");
  if (groomingForm) {
    groomingForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const selectedTypes = Array.from(document.getElementById("grooming-type").selectedOptions)
        .map(option => option.value);
      const formData = {
        types: selectedTypes,
        duration: parseInt(document.getElementById("grooming-duration").value) || 0,
        products: document.getElementById("grooming-products").value,
        notes: document.getElementById("grooming-notes").value
      };
      await submitAnalyticsForm(formData, "grooming");
      groomingForm.reset();
    });
  }

  // Energy form
  const energyForm = document.getElementById("energy-form");
  if (energyForm) {
    energyForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = {
        level: parseInt(document.getElementById("energy-level").value),
        notes: document.getElementById("energy-notes").value
      };
      await submitAnalyticsForm(formData, "energy_levels");
      energyForm.reset();
    });
  }

  // Bowel form
  const bowelForm = document.getElementById("bowel-form");
  if (bowelForm) {
    bowelForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = {
        consistency: document.getElementById("bowel-consistency").value,
        time: document.getElementById("bowel-time").value,
        notes: document.getElementById("bowel-notes").value
      };
      await submitAnalyticsForm(formData, "bowel_movements");
      bowelForm.reset();
    });
  }

  // Exit form
  const exitForm = document.getElementById("exit-form");
  if (exitForm) {
    exitForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = {
        type: document.getElementById("exit-type").value,
        duration: parseInt(document.getElementById("exit-duration").value) || 0,
        destination: document.getElementById("exit-destination").value
      };
      await submitAnalyticsForm(formData, "exit_events");
      exitForm.reset();
    });
  }

  // Weight form
  const weightForm = document.getElementById("weight-form");
  if (weightForm) {
    weightForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = {
        value: parseFloat(document.getElementById("weight-value").value),
        unit: document.getElementById("weight-unit").value,
        method: document.getElementById("weight-method").value,
        time: document.getElementById("weight-time").value,
        notes: document.getElementById("weight-notes").value
      };
      await submitAnalyticsForm(formData, "weight");
      weightForm.reset();
    });
  }

  // Sleep form
  const sleepForm = document.getElementById("sleep-form");
  if (sleepForm) {
    sleepForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = {
        duration: parseFloat(document.getElementById("sleep-duration").value),
        quality: document.getElementById("sleep-quality").value,
        location: document.getElementById("sleep-location").value,
        interruptions: parseInt(document.getElementById("sleep-interruptions").value) || 0,
        notes: document.getElementById("sleep-notes").value
      };
      await submitAnalyticsForm(formData, "sleep");
      sleepForm.reset();
    });
  }

  // Mood form
  const moodForm = document.getElementById("mood-form");
  if (moodForm) {
    moodForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const selectedTriggers = Array.from(document.getElementById("mood-triggers").selectedOptions)
        .map(option => option.value);
      const selectedBehaviors = Array.from(document.getElementById("mood-behavior").selectedOptions)
        .map(option => option.value);
      const formData = {
        level: parseInt(document.getElementById("mood-level").value),
        triggers: selectedTriggers,
        behavior: selectedBehaviors,
        time: document.getElementById("mood-time").value,
        notes: document.getElementById("mood-notes").value
      };
      await submitAnalyticsForm(formData, "mood");
      moodForm.reset();
    });
  }
}

// Tab functionality
window.showTab = function(tabName) {
  // Hide all tab contents
  const tabContents = document.querySelectorAll('.tab-content');
  tabContents.forEach(content => content.classList.remove('active'));
  
  // Remove active class from all tab buttons
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => btn.classList.remove('active'));
  
  // Show selected tab content
  document.getElementById(`${tabName}-tab`).classList.add('active');
  
  // Add active class to clicked button
  event.target.classList.add('active');
};

// Submit analytics form data
async function submitAnalyticsForm(formData, category) {
  if (!state.selectedPet) {
    showNotification("Please select a pet first", 'error');
    return;
  }

  try {
    const response = await fetch(`/api/pets/${state.selectedPet}/analytics/${category}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },

      body: JSON.stringify(formData)
    });

    if (response.ok) {
      showNotification(`${category.replace('_', ' ')} data saved successfully!`, 'success');
      await loadDashboard();
      await loadRecentEntries();
      await updateCharts();
    } else {
      showNotification('Failed to save data', 'error');
    }
  } catch (error) {
    console.error('Error submitting form:', error);
    showNotification('Error saving data', 'error');
  }
}

// Load analytics dashboard
async function loadDashboard() {
  if (!state.selectedPet) return;

  // Show loading state on metric cards
  const metricCards = document.querySelectorAll('.metric-card');
  metricCards.forEach(card => {
    const valueElement = card.querySelector('.metric-value');
    if (valueElement) {
      valueElement.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    }
  });

  try {
    const response = await fetch(`/api/pets/${state.selectedPet}/analytics/summary`);
    const data = await response.json();
    const summary = data.summary || {};
    
    // Update metric cards
    metricCards.forEach(card => {
      const category = card.dataset.category;
      const categoryData = summary[category] || { total: 0, this_week: 0, avg_daily: 0 };
      
      if (category === 'energy_levels') {
        // Calculate average energy level
        const recentEntries = categoryData.recent_entries || [];
        const avgEnergy = recentEntries.length > 0 
          ? recentEntries.reduce((sum, entry) => sum + (entry.level || 3), 0) / recentEntries.length
          : 0;
        card.querySelector('.metric-value').textContent = avgEnergy.toFixed(1);
      } else {
        card.querySelector('.metric-value').textContent = categoryData.total;
      }
    });
    
  } catch (error) {
    console.error('Error loading dashboard:', error);
    // Reset loading states on error
    const metricCards = document.querySelectorAll('.metric-card');
    metricCards.forEach(card => {
      const valueElement = card.querySelector('.metric-value');
      if (valueElement && valueElement.innerHTML.includes('fa-spinner')) {
        valueElement.textContent = '0';
      }
    });
  }
}

// Load recent entries
async function loadRecentEntries() {
  if (!state.selectedPet) return;

  try {
    const response = await fetch(`/api/pets/${state.selectedPet}/analytics?days=7`);
    const data = await response.json();
    const entries = data.data || [];
    
    const container = document.getElementById('recent-entries');
    
    if (entries.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; color: #7f8c8d; padding: 40px;">
          <i class="fas fa-clock"></i>
          <p>No recent entries. Start tracking your pet's activities above!</p>
        </div>
      `;
      return;
    }

    // Sort by timestamp (most recent first)
    entries.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    const html = entries.slice(0, 10).map(entry => {
      const date = new Date(entry.timestamp);
      const timeStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
      
      const icons = {
        diet: '🍽️',
        exercise: '🏃',
        medication: '💊',
        grooming: '✨',
        energy_levels: '⚡',
        bowel_movements: '💩',
        exit_events: '🚪',
        weight: '⚖️',
        sleep: '😴',
        mood: '😊',
        daily_activity: '📝',
        medical_notes: '🏥',
        mixed_notes: '📋'
      };
      
      const description = getEntryDescription(entry);
      
      return `
        <div class="recent-entry">
          <div class="entry-content">
            <div class="entry-category">${entry.category.replace('_', ' ')}</div>
            <div class="entry-description">${description}</div>
            <div class="entry-time">${timeStr}</div>
          </div>
          <div class="entry-icon">${icons[entry.category] || '📝'}</div>
        </div>
      `;
    }).join('');
    
    container.innerHTML = html;
    
  } catch (error) {
    console.error('Error loading recent entries:', error);
  }
}

function getEntryDescription(entry) {
  switch (entry.category) {
    case 'diet':
      return `${entry.food || 'Food'} - ${entry.type || 'meal'}`;
    case 'exercise':
      return `${entry.type || 'Exercise'} for ${entry.duration || 0} minutes`;
    case 'medication':
      return `${entry.name || 'Medication'} - ${entry.dosage || ''}`;
    case 'grooming':
      return `${Array.isArray(entry.types) ? entry.types.join(', ') : 'Grooming'}`;
    case 'energy_levels':
      return `Energy level: ${entry.level || 3}/5`;
    case 'bowel_movements':
      return `${entry.consistency || 'Normal'} consistency`;
    case 'exit_events':
      return `${entry.type || 'Exit'} - ${entry.destination || ''}`;
    case 'weight':
      return `Weight: ${entry.value || 0} ${entry.unit || 'lbs'}`;
    case 'sleep':
      return `Sleep: ${entry.duration || 0} hours - ${entry.quality || 'good'} quality`;
    case 'mood':
      return `Mood level: ${entry.level || 3}/5 - ${Array.isArray(entry.behavior) ? entry.behavior.join(', ') : 'mood logged'}`;
    case 'daily_activity':
      // Handle voice notes and daily activities
      if (entry.source === 'voice_note') {
        return `Voice note: ${entry.summary || entry.transcript || 'Daily activity recorded'}`;
      } else if (entry.source === 'text_input') {
        return `Text note: ${entry.summary || entry.input || 'Daily activity logged'}`;
      }
      return entry.summary || entry.notes || 'Daily activity logged';
    case 'medical_notes':
      // Handle medical notes from text input
      if (entry.source === 'text_input') {
        return `Medical note: ${entry.summary || entry.input || 'Medical information recorded'}`;
      }
      return entry.summary || entry.notes || 'Medical note logged';
    case 'mixed_notes':
      // Handle mixed content notes
      if (entry.source === 'text_input') {
        return `Mixed note: ${entry.summary || entry.input || 'Mixed content recorded'}`;
      }
      return entry.summary || entry.notes || 'Mixed content logged';
    default:
      return entry.summary || entry.notes || 'Activity logged';
  }
}

window.generateDailyHeadlines = async function() {
  if (!state.selectedPet) {
    showNotification("Please select a pet first", 'error');
    return;
  }

  const headlinesContainer = document.getElementById('daily-headlines');
  headlinesContainer.innerHTML = `
    <div style="text-align: center; color: rgba(255,255,255,0.8);">
      <i class="fas fa-spinner fa-spin"></i> Generating AI headlines...
    </div>
  `;

  try {
    const today = new Date().toISOString().split('T')[0];
    const response = await fetch(`/api/pets/${state.selectedPet}/daily_routine`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: today })
    });

    if (response.ok) {
      const data = await response.json();
      const headlines = data.headlines || [];
      
      if (headlines.length === 0) {
        headlinesContainer.innerHTML = `
          <div style="text-align: center; color: rgba(255,255,255,0.8);">
            No activities recorded for today. Start tracking to see AI-generated headlines!
          </div>
        `;
        return;
      }
      
      const headlinesHtml = headlines.map(headline => `
        <div class="daily-headline">
          ${headline}
        </div>
      `).join('');
      
      headlinesContainer.innerHTML = headlinesHtml;
      
    } else {
      throw new Error('Failed to generate headlines');
    }
  } catch (error) {
    console.error('Error generating headlines:', error);
    headlinesContainer.innerHTML = `
      <div style="text-align: center; color: rgba(255,255,255,0.8);">
        <i class="fas fa-exclamation-triangle"></i> Error generating headlines
      </div>
    `;
  }
};

export { setupAnalyticsFormHandlers, submitAnalyticsForm, loadDashboard, loadRecentEntries, getEntryDescription };
