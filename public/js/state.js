// public/js/state.js: mutable app state shared by the modules.
export const state = {
  user: null, // {uid, name} of the demo user (from the session)
  pets: [], // [Pet] owned by the user
  selectedPet: "", // pet id
  health: null, // GET /api/health payload (for Demo/Live badges)
  insightsLoaded: false, // assistant insights panel loaded for the selected pet
};

export function selectedPetObj() {
  return state.pets.find((p) => p.id === state.selectedPet) || null;
}

export function selectedPetName() {
  const pet = selectedPetObj();
  return pet ? pet.name : "your pet";
}
