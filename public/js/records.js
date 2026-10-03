// public/js/records.js: PDF vet records. Upload (POST /api/pets/{id}/records, multipart file),
// list (GET .../records) and owner-only download (GET .../records/{rid}/file, fetched with the
// Bearer token and handed to the browser as a blob, since a plain link can't send the header).
import { apiFetch, apiPath, asList, describeError } from "./api.js";
import { el, icon, replaceChildren, showNotification, formatDateTime } from "./dom.js";
import { state } from "./state.js";
import { featureMode } from "./banner.js";

const MAX_BYTES = 10 * 1024 * 1024;

const STATUS_LABELS = {
  summarized: "summarized",
  no_text: "no text layer",
  needs_ocr: "no text layer",
  summary_failed: "summary failed",
};

function noSummaryText(status) {
  if (status === "no_text" || status === "needs_ocr") return "No text layer found (scanned PDF), so there is no summary.";
  if (status === "summary_failed") return "The summary could not be generated. The PDF itself was saved and can be downloaded.";
  return "No summary available.";
}

function renderRecord(record) {
  const download = el("button", { type: "button", class: "btn btn-secondary btn-small" }, icon("fas fa-download"), " Download");
  download.addEventListener("click", () => downloadRecord(record, download));
  const meta = [record.pages ? `${record.pages} page${record.pages === 1 ? "" : "s"}` : null, STATUS_LABELS[record.status] || record.status, formatDateTime(record.created_at)]
    .filter(Boolean)
    .join(" · ");
  return el(
    "div",
    { class: "record-card", dataset: { recordId: record.id } },
    el("div", { class: "record-card-header" }, el("h4", {}, icon("fas fa-file-medical"), " ", el("span", { text: record.filename || "record.pdf" })), download),
    el("div", { class: "record-meta", text: meta }),
    record.summary
      ? el(
          "div",
          { class: "record-summary" },
          el("strong", { text: featureMode("pdf_summary") === "demo" ? "Summary (simulated): " : "Summary: " }),
          el("span", { text: record.summary })
        )
      : el("div", { class: "muted", text: noSummaryText(record.status) })
  );
}

export async function loadRecords() {
  const container = document.getElementById("records-list");
  if (!container || !state.selectedPet) return;
  replaceChildren(container, el("div", { class: "muted" }, icon("fas fa-spinner fa-spin"), " Loading records…"));
  try {
    const records = asList(await apiFetch(apiPath("pets", state.selectedPet, "records")));
    replaceChildren(container, records.length ? records.map(renderRecord) : el("div", { class: "muted", text: "No records uploaded yet." }));
  } catch (err) {
    replaceChildren(container, el("div", { class: "status-message error", style: "display:block", text: `Could not load records: ${describeError(err)}` }));
  }
}

async function downloadRecord(record, button) {
  button.disabled = true;
  try {
    const res = await apiFetch(apiPath("pets", state.selectedPet, "records", record.id, "file"), { raw: true });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: record.filename || "record.pdf" });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  } catch (err) {
    showNotification(`Download failed: ${describeError(err)}`, "error");
  } finally {
    button.disabled = false;
  }
}

async function onSubmit(e) {
  e.preventDefault();
  const resultBox = document.getElementById("pdf-result");
  const show = (...children) => {
    replaceChildren(resultBox, ...children);
    resultBox.classList.add("has-content");
  };
  if (!state.selectedPet) return showNotification("Please select a pet first", "warning");
  const fileInput = document.getElementById("pdf-file");
  const file = fileInput.files[0];
  if (!file) return showNotification("Please select a PDF file", "warning");
  if (file.type && file.type !== "application/pdf") return showNotification("Please select a PDF file", "warning");
  if (file.size > MAX_BYTES) return showNotification("File too large: the limit is 10 MB", "warning");

  show(el("div", { style: "text-align:center; padding: 20px;" }, icon("fas fa-spinner fa-spin"), " Uploading and analyzing PDF…"));
  const form = new FormData();
  form.append("file", file);
  try {
    const record = await apiFetch(apiPath("pets", state.selectedPet, "records"), { body: form });
    show(el("div", { class: "upload-ok" }, icon("fas fa-check-circle"), " PDF uploaded."), renderRecord(record));
    fileInput.value = "";
    document.getElementById("pdf-file-name").textContent = "";
    showNotification("PDF uploaded", "success");
    loadRecords();
  } catch (err) {
    const hint = err.status === 413 ? " (the file is too large)" : err.status === 415 ? " (the file is not a valid PDF)" : "";
    show(el("div", { class: "status-message error", style: "display:block" }, icon("fas fa-exclamation-triangle"), ` Upload failed: ${describeError(err)}${hint}`));
    showNotification("Error uploading PDF", "error");
  }
}

export function initRecords() {
  document.getElementById("pdf-form").addEventListener("submit", onSubmit);
  const fileInput = document.getElementById("pdf-file");
  const drop = document.getElementById("pdf-drop");
  drop.addEventListener("click", () => fileInput.click());
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });
  fileInput.addEventListener("click", (e) => e.stopPropagation());
  fileInput.addEventListener("change", () => {
    document.getElementById("pdf-file-name").textContent = fileInput.files[0] ? fileInput.files[0].name : "";
  });
  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("dragover");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("dragover"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("dragover");
    if (e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      fileInput.dispatchEvent(new Event("change"));
    }
  });
  document.getElementById("refresh-records-btn").addEventListener("click", loadRecords);
}
