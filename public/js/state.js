// public/js/state.js: mutable app state shared by the modules.
export const pageId = "default-page";

export const state = {
  currentUser: null,
  selectedPet: "",
  isRecording: false,
  assistantDataLoaded: false, // Track if assistant data has been loaded
};
