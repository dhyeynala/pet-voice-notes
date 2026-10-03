// public/js/firebase.js: optional Firebase sign-in. Loaded with import() only when the server
// reports auth "firebase" (GET /api/health), so demo mode never downloads the SDK.
// The web config comes from GET /api/auth/config; the SDK is vendored (public/vendor/README.md).
// Sessions use per-tab persistence, like the demo token in sessionStorage.
import { initializeApp } from "../vendor/firebase-12.19.0/firebase-app.js";
import {
  GoogleAuthProvider,
  browserSessionPersistence,
  connectAuthEmulator,
  createUserWithEmailAndPassword,
  getAuth,
  onIdTokenChanged,
  setPersistence,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
} from "../vendor/firebase-12.19.0/firebase-auth.js";
import { apiFetch } from "./api.js";

let authReady = null;

async function initAuth() {
  const cfg = await apiFetch("/api/auth/config", { auth: false });
  if (!cfg || cfg.provider !== "firebase" || !cfg.firebase || !cfg.firebase.apiKey) {
    throw new Error("Firebase sign-in is not enabled on this server.");
  }
  const { apiKey, authDomain, projectId, authEmulatorUrl } = cfg.firebase;
  const app = initializeApp({ apiKey, authDomain, projectId }, "petpulse");
  const auth = getAuth(app);
  // Only sent by the server for demo-* emulator projects (FIREBASE_AUTH_EMULATOR_HOST).
  if (authEmulatorUrl) connectAuthEmulator(auth, authEmulatorUrl, { disableWarnings: true });
  await setPersistence(auth, browserSessionPersistence);
  await auth.authStateReady();
  return auth;
}

/** The Firebase Auth instance (initialised once per page). */
export function firebaseAuth() {
  if (!authReady) {
    authReady = initAuth().catch((err) => {
      authReady = null; // allow a retry after e.g. a network error
      throw err;
    });
  }
  return authReady;
}

/** Google sign-in in a pop-up. Resolves to a Firebase ID token. */
export async function signInWithGoogle() {
  const auth = await firebaseAuth();
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
  const cred = await signInWithPopup(auth, provider);
  return cred.user.getIdToken();
}

/** Email + password sign-in (create = true registers a new account first). Resolves to an ID token. */
export async function signInWithEmail(email, password, create = false) {
  const auth = await firebaseAuth();
  const cred = create
    ? await createUserWithEmailAndPassword(auth, email, password)
    : await signInWithEmailAndPassword(auth, email, password);
  return cred.user.getIdToken();
}

/** A fresh ID token for the signed-in user, or null when nobody is signed in. */
export async function refreshIdToken() {
  const auth = await firebaseAuth();
  return auth.currentUser ? auth.currentUser.getIdToken(true) : null;
}

/** Call onToken(idToken) whenever Firebase rotates the token (it refreshes before the 1 h expiry). */
export async function watchIdToken(onToken) {
  const auth = await firebaseAuth();
  return onIdTokenChanged(auth, async (user) => {
    if (user) onToken(await user.getIdToken());
  });
}

export async function signOutFirebase() {
  try {
    await signOut(await firebaseAuth());
  } catch (err) {
    console.warn("Firebase sign-out failed:", err);
  }
}
