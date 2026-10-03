// Firebase sign-in helpers, the token refresh on 401, and the vendored SDK's integrity.
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const store = new Map();
globalThis.sessionStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};
const redirects = [];
globalThis.window = { location: { pathname: "/main.html", replace: (url) => redirects.push(url) } };

const { apiFetch, authModes, getToken, setSession, tokenRefreshers } = await import("../../public/js/api.js");
const { firebaseErrorMessage, isCancelled } = await import("../../public/js/firebase-errors.js");

const VENDOR = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "public", "vendor");

/** fetch stub: 200 {ok, token} for the accepted bearer token, 401 otherwise. */
function serverAccepting(validToken, calls) {
  return async (url, init) => {
    const auth = init.headers.Authorization || "";
    calls.push(auth);
    const ok = auth === `Bearer ${validToken}`;
    return new Response(JSON.stringify(ok ? { ok: true } : { detail: "invalid or expired token" }), {
      status: ok ? 200 : 401,
      headers: { "content-type": "application/json" },
    });
  };
}

beforeEach(() => {
  store.clear();
  redirects.length = 0;
});

test("authModes reads the backend's string auth field", () => {
  assert.deepEqual(authModes({ auth: "firebase", mode: "demo" }), ["firebase"]);
  assert.deepEqual(authModes({ auth: "demo" }), ["demo"]);
  assert.deepEqual(authModes({ auth: "" }), ["demo"]);
});

test("a Firebase session refreshes its ID token once on 401 and retries", async () => {
  const calls = [];
  globalThis.fetch = serverAccepting("fresh", calls);
  let refreshes = 0;
  tokenRefreshers.firebase = async () => {
    refreshes += 1;
    return "fresh";
  };
  setSession("stale", { uid: "u1", name: "U" }, "firebase");
  assert.deepEqual(await apiFetch("/api/me"), { ok: true });
  assert.deepEqual(calls, ["Bearer stale", "Bearer fresh"]);
  assert.equal(refreshes, 1);
  assert.equal(getToken(), "fresh");
  assert.deepEqual(redirects, []);
});

test("concurrent 401s share one refresh", async () => {
  const calls = [];
  globalThis.fetch = serverAccepting("fresh", calls);
  let refreshes = 0;
  tokenRefreshers.firebase = async () => {
    refreshes += 1;
    await new Promise((r) => setTimeout(r, 5));
    return "fresh";
  };
  setSession("stale", null, "firebase");
  await Promise.all([apiFetch("/api/a"), apiFetch("/api/b"), apiFetch("/api/c")]);
  assert.equal(refreshes, 1);
});

// Runs before any other redirect: api.js navigates at most once per page.
test("a failed refresh ends the session and goes back to the login page", async () => {
  const calls = [];
  globalThis.fetch = serverAccepting("never", calls);
  tokenRefreshers.firebase = async () => {
    throw new Error("user signed out");
  };
  setSession("stale", null, "firebase");
  await assert.rejects(apiFetch("/api/me"), (err) => err.status === 401);
  assert.equal(calls.length, 1); // no retry without a new token
  assert.equal(getToken(), null);
  assert.deepEqual(redirects, ["/?expired=1"]);
});

test("demo sessions never try to refresh", async () => {
  globalThis.fetch = serverAccepting("nope", []);
  tokenRefreshers.firebase = async () => assert.fail("must not refresh a demo session");
  setSession("demo-token", null, "demo");
  await assert.rejects(apiFetch("/api/me"), (err) => err.status === 401);
  assert.equal(getToken(), null);
});

test("Firebase error codes become readable messages", () => {
  assert.equal(firebaseErrorMessage({ code: "auth/invalid-credential" }), "Wrong email or password.");
  assert.match(firebaseErrorMessage("auth/popup-blocked"), /pop-ups/);
  assert.equal(firebaseErrorMessage({ code: "auth/unknown", message: "Firebase: Error (auth/unknown)." }), "Sign-in failed. Please try again.");
  assert.equal(firebaseErrorMessage({ message: "Firebase sign-in is not enabled on this server." }), "Firebase sign-in is not enabled on this server.");
  assert.equal(isCancelled({ code: "auth/popup-closed-by-user" }), true);
  assert.equal(isCancelled({ code: "auth/invalid-credential" }), false);
});

test("vendored files match the sha256 list in public/vendor/README.md", () => {
  const readme = readFileSync(join(VENDOR, "README.md"), "utf8");
  const block = readme.split("## sha256")[1].split("```")[1];
  const entries = block.trim().split("\n").map((line) => line.trim().split(/\s+/));
  assert.ok(entries.some(([, file]) => file.startsWith("firebase-")), "Firebase SDK is listed");
  for (const [hash, file] of entries) {
    const actual = createHash("sha256").update(readFileSync(join(VENDOR, file))).digest("hex");
    assert.equal(actual, hash, `${file} does not match README.md`);
  }
});

test("the vendored Firebase SDK imports nothing remote", () => {
  for (const file of ["firebase-app.js", "firebase-auth.js"]) {
    const src = readFileSync(join(VENDOR, "firebase-12.19.0", file), "utf8");
    assert.doesNotMatch(src, /\bfrom\s*["']https?:/, `${file} imports a remote module`);
    assert.doesNotMatch(src, /sourceMappingURL=/, `${file} points at an unvendored source map`);
  }
  const auth = readFileSync(join(VENDOR, "firebase-12.19.0", "firebase-auth.js"), "utf8");
  assert.match(auth, /\bfrom\s*"\.\/firebase-app\.js"/);
});
