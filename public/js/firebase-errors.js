// public/js/firebase-errors.js: readable messages for Firebase Auth error codes (pure, unit-tested).

const MESSAGES = {
  "auth/invalid-credential": "Wrong email or password.",
  "auth/invalid-login-credentials": "Wrong email or password.", // pragma: allowlist secret
  "auth/wrong-password": "Wrong email or password.", // pragma: allowlist secret
  "auth/user-not-found": "Wrong email or password.",
  "auth/invalid-email": "That email address is not valid.",
  "auth/missing-password": "Enter your password.", // pragma: allowlist secret
  "auth/email-already-in-use": "An account with this email already exists. Sign in instead.",
  "auth/weak-password": "Choose a stronger password (at least 6 characters).", // pragma: allowlist secret
  "auth/user-disabled": "This account has been disabled.",
  "auth/too-many-requests": "Too many attempts. Wait a moment and try again.",
  "auth/popup-closed-by-user": "The sign-in window was closed before finishing.",
  "auth/cancelled-popup-request": "The sign-in window was closed before finishing.",
  "auth/popup-blocked": "Your browser blocked the sign-in window. Allow pop-ups for this site and try again.",
  "auth/operation-not-allowed": "This sign-in method is not enabled for the Firebase project.",
  "auth/unauthorized-domain": "This site's domain is not authorised in the Firebase project (Authentication > Settings).",
  "auth/network-request-failed": "Could not reach Firebase. Check your connection.",
  "auth/invalid-api-key": "The server's Firebase web config is invalid (FIREBASE_WEB_API_KEY).",
};

/** Error (or code string) from the Firebase SDK -> one sentence for the login page. */
export function firebaseErrorMessage(err) {
  const code = typeof err === "string" ? err : err && err.code;
  if (code && MESSAGES[code]) return MESSAGES[code];
  if (err && err.message && !String(err.message).startsWith("Firebase:")) return err.message;
  return "Sign-in failed. Please try again.";
}

/** True for errors where the user simply backed out (no red error needed). */
export function isCancelled(err) {
  const code = err && err.code;
  return code === "auth/popup-closed-by-user" || code === "auth/cancelled-popup-request";
}
