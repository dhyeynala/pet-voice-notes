// public/js/auth.js: the session on main.html (token in sessionStorage), the user menu with
// log out, and (demo sessions only) quick "switch user" and "reset demo data". A Firebase session
// keeps its stored ID token fresh and signs out of Firebase on log out.
import { apiFetch, asList, clearSession, getAuthMethod, getToken, getUser, setSession, describeError } from "./api.js";
import { el, icon, replaceChildren, showNotification } from "./dom.js";
import { state } from "./state.js";

/** Redirect to the login page unless a token is present. Returns the stored user. */
export function requireSession() {
  if (!getToken()) {
    window.location.replace("/");
    return null;
  }
  state.user = getUser();
  return state.user;
}

/** Confirm the token with the backend (refreshes the stored user name). */
export async function refreshMe() {
  const me = await apiFetch("/api/me");
  state.user = me;
  setSession(getToken(), me, getAuthMethod());
  return me;
}

export async function logout() {
  const firebase = getAuthMethod() === "firebase";
  clearSession();
  if (firebase) {
    try {
      await (await import("./firebase.js")).signOutFirebase();
    } catch (err) {
      console.warn("Firebase sign-out failed:", err);
    }
  }
  window.location.replace("/");
}

/** Firebase sessions: store each rotated ID token so API calls never send an expired one. */
export async function keepTokenFresh() {
  if (getAuthMethod() !== "firebase") return;
  try {
    const { watchIdToken } = await import("./firebase.js");
    await watchIdToken((token) => {
      if (getToken()) setSession(token, getUser(), "firebase");
    });
  } catch (err) {
    console.warn("Could not start Firebase token refresh:", err);
  }
}

export async function switchUser(uid) {
  try {
    const res = await apiFetch("/api/demo/login", { json: { uid }, auth: false });
    setSession(res.token, res.user, "demo");
    window.location.replace("/main.html");
  } catch (err) {
    showNotification(`Could not switch user: ${describeError(err)}`, "error");
  }
}

async function resetDemo() {
  if (!window.confirm("Reset all demo data to the original seed? Your changes in this demo will be lost.")) return;
  try {
    await apiFetch("/api/demo/reset", { method: "POST" });
    showNotification("Demo data reset.", "success");
    setTimeout(() => window.location.reload(), 600);
  } catch (err) {
    showNotification(`Reset failed: ${describeError(err)}`, "error");
  }
}

/** Render "Signed in as X", the switch-user dropdown and the log-out button into #user-menu. */
export async function renderUserMenu() {
  const container = document.getElementById("user-menu");
  if (!container) return;
  const user = state.user || {};
  const list = el("div", { class: "user-switch-list", hidden: true, attrs: { role: "menu" } });
  const toggle = el(
    "button",
    {
      class: "user-switch-btn",
      type: "button",
      title: "Account",
      attrs: { "aria-haspopup": "true", "aria-expanded": "false" },
      on: {
        click: (e) => {
          e.stopPropagation();
          list.hidden = !list.hidden;
          toggle.setAttribute("aria-expanded", String(!list.hidden));
        },
      },
    },
    icon("fas fa-user-circle"),
    el("span", { class: "user-name", text: user.name || user.uid || "Demo user" }),
    icon("fas fa-caret-down")
  );
  document.addEventListener("click", () => {
    list.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  });

  replaceChildren(
    container,
    el("div", { class: "user-switch" }, toggle, list),
    el("button", { class: "logout-btn", type: "button", id: "logout-btn", on: { click: logout } }, icon("fas fa-sign-out-alt"), " Log out")
  );

  if (getAuthMethod() !== "demo") {
    // Switching users and resetting data are demo-only; other sign-in methods just log out.
    list.appendChild(
      el("button", { type: "button", class: "user-switch-item", attrs: { role: "menuitem" }, on: { click: logout } }, icon("fas fa-sign-out-alt"), " Log out")
    );
    return;
  }
  list.appendChild(el("div", { class: "user-switch-heading", text: "Switch user" }));
  try {
    const users = await apiFetch("/api/demo/users", { auth: false });
    for (const u of asList(users)) {
      const current = u.uid === user.uid;
      list.appendChild(
        el(
          "button",
          {
            type: "button",
            class: `user-switch-item${current ? " current" : ""}`,
            disabled: current,
            attrs: { role: "menuitem" },
            on: { click: () => switchUser(u.uid) },
          },
          icon("fas fa-user"),
          ` ${u.name || u.uid}${current ? " (you)" : ""}`
        )
      );
    }
  } catch (err) {
    list.appendChild(el("div", { class: "user-switch-heading", text: `Could not load users: ${describeError(err)}` }));
  }
  list.appendChild(el("hr"));
  list.appendChild(
    el("button", { type: "button", class: "user-switch-item", attrs: { role: "menuitem" }, on: { click: resetDemo } }, icon("fas fa-undo"), " Reset demo data")
  );
  list.appendChild(
    el("button", { type: "button", class: "user-switch-item", attrs: { role: "menuitem" }, on: { click: logout } }, icon("fas fa-sign-out-alt"), " Log out")
  );
}
