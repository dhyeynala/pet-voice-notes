// public/js/login.js: demo login on index.html. Lists GET /api/demo/users, logs in with
// POST /api/demo/login {uid}, keeps the token in sessionStorage and opens main.html.
import { apiFetch, asList, clearSession, describeError, getToken, setSession } from "./api.js";
import { el, icon, replaceChildren } from "./dom.js";
import { initBanner } from "./banner.js";

const params = new URLSearchParams(window.location.search);
const listNode = document.getElementById("demo-users");
const statusNode = document.getElementById("login-status");

function setStatus(text, isError = false) {
  statusNode.textContent = text;
  statusNode.className = `login-status${isError ? " error" : ""}`;
  statusNode.hidden = !text;
}

/** body is exactly one of {uid} (existing user) or {name} (creates a new demo user with no pets). */
async function login(body, button) {
  button.disabled = true;
  setStatus("Signing in…");
  try {
    const res = await apiFetch("/api/demo/login", { json: body, auth: false });
    setSession(res.token, res.user);
    window.location.replace("/main.html");
  } catch (err) {
    button.disabled = false;
    setStatus(`Login failed: ${describeError(err)}`, true);
  }
}

async function renderUsers() {
  replaceChildren(listNode, el("div", { class: "login-loading" }, icon("fas fa-spinner fa-spin"), " Loading demo users…"));
  try {
    const users = asList(await apiFetch("/api/demo/users", { auth: false }));
    if (!users || users.length === 0) {
      replaceChildren(listNode, el("p", { text: "No demo users are configured on the server." }));
      return;
    }
    replaceChildren(
      listNode,
      users.map((u) => {
        const btn = el(
          "button",
          { type: "button", class: "google-btn user-btn", dataset: { uid: u.uid } },
          icon("fas fa-user-circle"),
          el("span", { text: `Continue as ${u.name || u.uid}` })
        );
        btn.addEventListener("click", () => login({ uid: u.uid }, btn));
        return btn;
      })
    );
  } catch (err) {
    const msg = err.status === 404 ? "Demo login is turned off on this server (DEMO_MODE=false)." : `Could not load demo users: ${describeError(err)}`;
    replaceChildren(listNode, el("p", { class: "login-status error", text: msg }));
    document.getElementById("new-user-form").hidden = true;
  }
}

function initNewUserForm() {
  const form = document.getElementById("new-user-form");
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const name = document.getElementById("new-user-name").value.trim();
    if (!name) return setStatus("Enter a display name for the new demo user.", true);
    login({ name }, form.querySelector("button"));
  });
}

async function init() {
  initBanner();
  if (params.get("expired")) setStatus("Your session expired. Please choose a user again.", true);
  if (params.get("switch") || params.get("expired")) clearSession();

  if (getToken()) {
    // Already signed in: confirm the token is still valid, then go straight to the app.
    try {
      await apiFetch("/api/me");
      window.location.replace("/main.html");
      return;
    } catch {
      clearSession();
    }
  }
  initNewUserForm();
  renderUsers();
}

init();
