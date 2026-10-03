// public/js/pets.js: Pet list, pet selector and the add-pet form.
import { state } from "./state.js";
import { loadDashboard, loadRecentEntries } from "./analytics.js";
import { updateCharts } from "./charts.js";
import { resetAssistantState } from "./chat.js";
import { preloadPetData } from "./cache.js";
import { showNotification } from "./dom.js";

// Pet management functions
async function loadPets() {
  try {
    const res = await fetch(`/api/user-pets/${state.currentUser.uid}`);
    const pets = await res.json();
    const select = document.getElementById("pet-select");
    select.innerHTML = "";

    if (pets.length === 0) {
      // No pets found - add a placeholder option and show add-pet section
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No pets added yet";
      select.appendChild(option);
      
      console.log('No pets found - redirecting to add-pet section');
      hideQuickQuestions();
      
      // Auto-navigate to add-pet section if no pets exist
      setTimeout(() => showSection('add-pet'), 100);
      return;
    }

    pets.forEach(pet => {
      const option = document.createElement("option");
      option.value = pet.id;
      option.textContent = pet.name || pet.id;
      select.appendChild(option);
    });

    if (pets.length > 0) {
      state.selectedPet = pets[0].id;
      select.value = state.selectedPet;
      console.log('First pet selected:', state.selectedPet);
      
      // Show quick questions now that we have a pet selected
      showQuickQuestions();
    } else {
      console.log('No pets found');
      hideQuickQuestions();
    }
  } catch (error) {
    console.error('Error loading pets:', error);
  }
}

document.getElementById("pet-select").addEventListener("change", async (e) => {
  state.selectedPet = e.target.value;
  console.log('Pet selection changed to:', state.selectedPet);
  
  // Reset all assistant/chat/insight UI and state when pet changes
  resetAssistantState();
  
  if (state.selectedPet) {
    showQuickQuestions();
    
    // Preload pet data for faster chat responses
    await preloadPetData(state.selectedPet);
  } else {
    hideQuickQuestions();
  }
  
  // Get pet name for notification
  const petSelect = document.getElementById("pet-select");
  const petName = petSelect.options[petSelect.selectedIndex].text;
  console.log('Pet name:', petName);
  
  // Refresh analytics data immediately when pet changes
  const currentSection = document.querySelector('.section.active');
  if (currentSection && currentSection.id === 'analytics-section') {
    // Show notification that data is being loaded
    showNotification(`Loading analytics for ${petName}...`, 'info', 2000);
    
    // Update analytics section components
    loadDashboard(); // Load dashboard metrics
    updateCharts(); // Update visualization charts
    generateDailyHeadlines(); // Generate today's headlines for new pet
  }
  
  // Also refresh tracking section if it's active
  if (currentSection && currentSection.id === 'tracking-section') {
    showNotification(`Loading tracking data for ${petName}...`, 'info', 2000);
    loadRecentEntries(); // Load recent entries for new pet
  }
});

// Enhanced Pet Creation Function
window.handleAddPetForm = async function(event) {
  event.preventDefault();
  
  if (!state.currentUser) {
    showNotification("Please log in first", 'error');
    return;
  }

  const form = document.getElementById('add-pet-form');
  const statusElement = document.getElementById('add-pet-status');
  
  // Get form data
  const formData = new FormData(form);
  const petData = {
    name: document.getElementById('pet-name').value.trim(),
    animal_type: document.getElementById('animal-type').value,
    breed: document.getElementById('pet-breed').value.trim(),
    age: document.getElementById('pet-age').value ? parseInt(document.getElementById('pet-age').value) : null,
    weight: document.getElementById('pet-weight').value ? parseFloat(document.getElementById('pet-weight').value) : null,
    gender: document.getElementById('pet-gender').value
  };

  // Validation
  if (!petData.name) {
    statusElement.textContent = "Please enter a pet name";
    statusElement.className = "status-message error";
    return;
  }

  if (!petData.animal_type) {
    statusElement.textContent = "Please select an animal type";
    statusElement.className = "status-message error";
    return;
  }

  try {
    statusElement.textContent = "Creating pet profile...";
    statusElement.className = "status-message";
    statusElement.style.display = "block";

    const response = await fetch(`/api/pets/${state.currentUser.uid}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(petData)
    });

    const result = await response.json();

    if (response.ok) {
      statusElement.textContent = `${petData.name} has been added successfully!`;
      statusElement.className = "status-message success";
      
      // Reset form
      form.reset();
      
      // Reload pets list
      await loadPets();
      
      // Navigate to assistant page with the new pet
      setTimeout(() => {
        showSection('assistant');
        showNotification(`Welcome ${petData.name}! You can now start using the health assistant.`, 'success');
      }, 1500);
      
    } else {
      throw new Error(result.error || 'Failed to create pet');
    }

  } catch (error) {
    console.error('Error creating pet:', error);
    statusElement.textContent = `Error: ${error.message}`;
    statusElement.className = "status-message error";
  }
};

export { loadPets };
