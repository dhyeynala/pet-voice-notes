// public/js/auth.js: Authentication.

import { app } from "../firebase-config.js";
import {
  getAuth,
  onAuthStateChanged,
  signOut
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

export const auth = getAuth(app);
export { onAuthStateChanged };

window.logout = async function () {
  await signOut(auth);
  window.location.href = "/index.html";
};
