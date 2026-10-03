// public/js/pets.js: pet list (GET /api/me/pets), the pet selector and the add-pet form
// (POST /api/pets). The backend takes the owner from the token.
import { apiFetch, asList, describeError } from "./api.js";
import { el, setStatus, showNotification, validateFormField, updateFormProgress, debounce } from "./dom.js";
import { state, selectedPetName } from "./state.js";
import { showSection, activeSection, refreshSection } from "./nav.js";
import { resetAssistantState, showQuickQuestions, hideQuickQuestions } from "./chat.js";

const SELECTED_KEY = "petpulse.selectedPet";

export async function loadPets(preferId) {
  const select = document.getElementById("pet-select");
  let pets = [];
  try {
    pets = asList(await apiFetch("/api/me/pets"));
  } catch (err) {
    showNotification(`Could not load your pets: ${describeError(err)}`, "error");
  }
  state.pets = pets;
  select.replaceChildren();

  if (pets.length === 0) {
    select.appendChild(el("option", { value: "", text: "No pets added yet" }));
    state.selectedPet = "";
    hideQuickQuestions();
    setTimeout(() => showSection("add-pet"), 100);
    return pets;
  }

  for (const pet of pets) {
    const label = pet.animal_type ? `${pet.name || pet.id} (${pet.animal_type})` : pet.name || pet.id;
    select.appendChild(el("option", { value: pet.id, text: label }));
  }
  const remembered = preferId || sessionStorage.getItem(SELECTED_KEY);
  state.selectedPet = pets.some((p) => p.id === remembered) ? remembered : pets[0].id;
  select.value = state.selectedPet;
  showQuickQuestions();
  return pets;
}

function onPetChange(e) {
  state.selectedPet = e.target.value;
  sessionStorage.setItem(SELECTED_KEY, state.selectedPet);
  resetAssistantState();
  if (!state.selectedPet) {
    hideQuickQuestions();
    return;
  }
  showQuickQuestions();
  const section = activeSection();
  if (section === "analytics" || section === "tracking") {
    showNotification(`Loading data for ${selectedPetName()}…`, "info", 2000);
  }
  refreshSection(section);
}

/** Only send fields the user filled in; PetCreate forbids unknown keys and validates ranges. */
function readPetForm() {
  const val = (id) => document.getElementById(id).value.trim();
  const pet = { name: val("pet-name"), animal_type: val("animal-type") };
  if (val("pet-breed")) pet.breed = val("pet-breed");
  if (val("pet-age") !== "") pet.age = Number(val("pet-age")); // PetCreate: integer 0-40
  if (val("pet-weight") !== "") pet.weight = Number(val("pet-weight"));
  if (val("pet-gender")) pet.gender = val("pet-gender");
  return pet;
}

async function handleAddPetForm(event) {
  event.preventDefault();
  const form = document.getElementById("add-pet-form");
  const status = document.getElementById("add-pet-status");
  const button = document.getElementById("create-pet-btn");
  const pet = readPetForm();

  if (!pet.name) return setStatus(status, "Please enter a pet name", "status-message error");
  if (!pet.animal_type) return setStatus(status, "Please select an animal type", "status-message error");
  if (pet.age !== undefined && !(Number.isInteger(pet.age) && pet.age >= 0 && pet.age <= 40)) {
    return setStatus(status, "Age must be a whole number of years (0-40)", "status-message error");
  }
  if (pet.weight !== undefined && !(Number.isFinite(pet.weight) && pet.weight >= 0 && pet.weight <= 500)) {
    return setStatus(status, "Weight must be a number between 0 and 500", "status-message error");
  }

  button.disabled = true;
  setStatus(status, "Creating pet profile…", "status-message");
  try {
    const created = await apiFetch("/api/pets", { json: pet });
    setStatus(status, `${created.name || pet.name} has been added successfully!`, "status-message success");
    form.reset();
    updateFormProgress();
    sessionStorage.setItem(SELECTED_KEY, created.id);
    await loadPets(created.id);
    resetAssistantState();
    setTimeout(() => {
      showSection("assistant");
      showNotification(`Welcome ${created.name || pet.name}! You can now start using the health assistant.`, "success");
    }, 1200);
  } catch (err) {
    setStatus(status, `Error: ${describeError(err)}`, "status-message error");
  } finally {
    button.disabled = false;
  }
}

export function initPets() {
  document.getElementById("pet-select").addEventListener("change", onPetChange);
  const form = document.getElementById("add-pet-form");
  form.addEventListener("submit", handleAddPetForm);
  form.querySelectorAll("input, select").forEach((field) => {
    field.addEventListener("input", debounce(updateFormProgress, 300));
    field.addEventListener("change", updateFormProgress);
  });
  document.getElementById("pet-name").addEventListener("blur", () =>
    validateFormField("pet-name", (v) => v.trim().length >= 1, "Please enter a pet name")
  );
  document.getElementById("animal-type").addEventListener("change", () =>
    validateFormField("animal-type", (v) => v !== "", "Please select an animal type")
  );
}
