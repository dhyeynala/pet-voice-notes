// public/js/dom.js: shared DOM helpers. Rule of thumb for this codebase: dynamic data goes in
// with textContent (or el()), never innerHTML. innerHTML is only used for static markup or for
// strings that went through escapeHtml() first (see markdown.js).
// Nothing here touches `document` at import time, so the pure helpers can be unit-tested in node.

const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Escape a value for safe interpolation into HTML text or a quoted attribute. */
export function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch]);
}

/**
 * Create an element. props: {class, text, style, title, dataset, attrs, on: {click: fn}}.
 * Children may be nodes, strings (added as text nodes) or null/false (skipped).
 */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null) continue;
    if (key === "class" || key === "className") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "style") node.style.cssText = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "attrs") for (const [a, v] of Object.entries(value)) node.setAttribute(a, v);
    else if (key === "on") for (const [ev, fn] of Object.entries(value)) node.addEventListener(ev, fn);
    else node[key] = value;
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.appendChild(typeof child === "string" || typeof child === "number" ? document.createTextNode(String(child)) : child);
  }
  return node;
}

/** Font Awesome icon element (class names are static strings from our own code). */
export function icon(classes) {
  return el("i", { class: classes, attrs: { "aria-hidden": "true" } });
}

/** Replace all children of `node` with `children`. */
export function replaceChildren(node, ...children) {
  if (!node) return;
  node.replaceChildren();
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
}

/** Set a status line: text plus a CSS class (e.g. "status-message error"). */
export function setStatus(node, text, className, autoHideMs = 0) {
  if (!node) return;
  node.textContent = text;
  node.className = className;
  node.style.display = "block";
  if (autoHideMs) setTimeout(() => (node.style.display = "none"), autoHideMs);
}

/** Toast notification. The message is always rendered as text. */
export function showNotification(message, type = "info", duration = 4000) {
  const iconChar = type === "success" ? "✓" : type === "error" ? "✕" : type === "warning" ? "⚠" : "ℹ";
  const toast = el(
    "div",
    { class: `notification-toast ${type}`, attrs: { role: type === "error" ? "alert" : "status" } },
    el("span", { style: "font-size: 16px;", text: iconChar }),
    el("span", { text: String(message) })
  );
  document.body.appendChild(toast);
  setTimeout(() => toast.classList.add("show"), 100);
  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 400);
  }, duration);
}

/** Put a button into a loading state; the original children are restored by hideLoadingState. */
export function showLoadingState(element, message = "Loading") {
  if (!element || element.dataset.loading) return;
  element.dataset.loading = "1";
  element._originalChildren = Array.from(element.childNodes);
  replaceChildren(element, el("span", { class: "loading-dots", text: message }));
  element.disabled = true;
  element.classList.add("loading-shimmer");
}

export function hideLoadingState(element) {
  if (!element) return;
  if (element._originalChildren) {
    replaceChildren(element, element._originalChildren);
    delete element._originalChildren;
  }
  delete element.dataset.loading;
  element.disabled = false;
  element.classList.remove("loading-shimmer");
}

export function showOverlay(show) {
  const overlay = document.getElementById("loading-overlay");
  if (overlay) overlay.style.display = show ? "flex" : "none";
}

export function updateCharacterCount(textareaId, countId, maxLength) {
  const textarea = document.getElementById(textareaId);
  const counter = document.getElementById(countId);
  if (textarea && counter) {
    const count = textarea.value.length;
    counter.textContent = count;
    counter.style.color = count > maxLength * 0.9 ? "#e53e3e" : "#7f8c8d";
  }
}

export function debounce(func, wait) {
  let timeout;
  return function debounced(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}

export function validateFormField(fieldId, validationFn, errorMessage) {
  const field = document.getElementById(fieldId);
  if (!field) return true;
  const formGroup = field.closest(".form-group");
  const errorDiv = document.getElementById(fieldId + "-error");
  const isValid = validationFn(field.value);
  if (formGroup) {
    formGroup.classList.remove("error", "success");
    formGroup.classList.add(isValid ? "success" : "error");
  }
  if (errorDiv) {
    errorDiv.textContent = isValid ? "" : errorMessage;
    errorDiv.classList.toggle("show", !isValid);
  }
  return isValid;
}

export function updateFormProgress() {
  const form = document.getElementById("add-pet-form");
  const progressFill = document.getElementById("form-progress");
  if (!form || !progressFill) return;
  const fields = form.querySelectorAll("input[required], select[required]");
  const filled = Array.from(fields).filter((f) => f.value.trim() !== "");
  progressFill.style.width = `${fields.length ? (filled.length / fields.length) * 100 : 0}%`;
}

/** Parse a backend timestamp. Values without an offset are treated as UTC (the backend stores UTC). */
export function parseTimestamp(value) {
  if (!value) return null;
  const s = String(value);
  const hasZone = /[zZ]$|[+-]\d\d:?\d\d$/.test(s);
  const d = new Date(hasZone || !s.includes("T") ? s : s + "Z");
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDateTime(value) {
  const d = parseTimestamp(value);
  if (!d) return "";
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

export function formatDate(value) {
  const d = parseTimestamp(value);
  return d ? d.toLocaleDateString() : String(value || "");
}
