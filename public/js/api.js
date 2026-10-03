// public/js/api.js: the only way the frontend talks to the backend.
// apiFetch adds the demo Bearer token, sends the user back to the login page on 401, and throws
// ApiError (with the server's `detail`) on any non-2xx response. No uid ever goes in a URL: the
// backend takes the user from the token.

const TOKEN_KEY = "petpulse.token";
const USER_KEY = "petpulse.user";

export class ApiError extends Error {
  constructor(status, detail, requestId, body) {
    super(detail || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.requestId = requestId;
    this.body = body;
    this.code = body && typeof body === "object" ? body.code : undefined;
  }
}

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function getUser() {
  try {
    return JSON.parse(sessionStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

export function setSession(token, user) {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(user || null));
}

export function clearSession() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
}

/** The browser's IANA time zone, sent to the backend for day bucketing. */
export function browserTimeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

/** Build "/api/..." with URL-encoded path segments: apiPath("pets", id, "notes"). */
export function apiPath(...segments) {
  return "/api/" + segments.map((s) => encodeURIComponent(String(s))).join("/");
}

/** Turn a FastAPI/contract error body into one readable line. */
export function errorDetail(body, status) {
  if (!body) return `Request failed (${status})`;
  const d = body.detail ?? body.error ?? body.message;
  // Contract 422s: {"detail": str, "errors": [{loc, msg, type}]} (values are never echoed back)
  if (typeof d === "string" && Array.isArray(body.errors) && body.errors.length) {
    const first = body.errors[0] && body.errors[0].msg;
    if (!first || !d.includes(first)) return `${d}: ${errorDetail({ detail: body.errors }, status)}`;
  }
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    // FastAPI validation errors: [{loc: [...], msg: "..."}]
    return d.map((e) => (e && e.msg ? `${(e.loc || []).filter((p) => p !== "body").join(".")}: ${e.msg}` : String(e))).join("; ");
  }
  if (d && typeof d === "object") return d.message || d.code || JSON.stringify(d);
  return `Request failed (${status})`;
}

let redirecting = false;

function redirectToLogin() {
  clearSession();
  const here = window.location.pathname;
  if (redirecting || here === "/" || here === "/index.html") return;
  redirecting = true; // several requests can fail with 401 at once; navigate only once
  window.location.replace("/?expired=1");
}

/**
 * fetch() wrapper for every API call.
 * options: method, json (object -> JSON body), body (FormData etc.), query (object), raw (return the
 * Response instead of parsed JSON), auth (default true), signal.
 */
export async function apiFetch(path, options = {}) {
  const { method, json, body, query, raw = false, auth = true, signal } = options;
  const headers = { Accept: raw ? "*/*" : "application/json" };
  let payload = body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(json);
  }
  const token = getToken();
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let url = path;
  if (query) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== "") params.set(k, v);
    const qs = params.toString();
    if (qs) url += (url.includes("?") ? "&" : "?") + qs;
  }

  let response;
  try {
    response = await fetch(url, { method: method || (payload !== undefined ? "POST" : "GET"), headers, body: payload, signal });
  } catch (err) {
    if (err && err.name === "AbortError") throw err;
    throw new ApiError(0, "Network error: the server could not be reached.", null, null);
  }

  if (response.status === 401 && auth) {
    redirectToLogin();
    throw new ApiError(401, "Your session has expired. Please log in again.", null, null);
  }

  if (!response.ok) {
    let errBody = null;
    try {
      errBody = await response.json();
    } catch {
      errBody = null;
    }
    throw new ApiError(response.status, errorDetail(errBody, response.status), errBody && errBody.request_id, errBody);
  }

  if (raw) return response;
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError(response.status, "The server returned an unexpected (non-JSON) response.", null, text);
  }
}

/** Lists are bare arrays in the contract; tolerate legacy {data: [...]} wrappers during the switch-over. */
export function asList(payload) {
  if (Array.isArray(payload)) return payload;
  if (payload && typeof payload === "object") {
    for (const key of ["data", "items", "entries", "results", "notes", "records", "pets", "samples"]) {
      if (Array.isArray(payload[key])) return payload[key];
    }
  }
  return [];
}

/** Human-readable message for an error thrown by apiFetch (adds the request id when present). */
export function describeError(err) {
  if (!err) return "Unknown error";
  const msg = err.message || String(err);
  return err.requestId ? `${msg} (request ${err.requestId})` : msg;
}
