// Unit tests for pure frontend helpers (api.js / recorder.js / dom.js). These modules do not touch
// the DOM at import time, so they load directly in node.
import { test } from "node:test";
import assert from "node:assert/strict";
import { errorDetail, asList, apiPath, describeError, ApiError } from "../../public/js/api.js";
import { pickMimeType, extensionFor, voiceErrorMessage, micErrorMessage, MIME_CANDIDATES } from "../../public/js/recorder.js";
import { parseTimestamp } from "../../public/js/dom.js";

test("pickMimeType returns the first supported candidate", () => {
  assert.equal(pickMimeType(() => true), MIME_CANDIDATES[0]);
  assert.equal(pickMimeType((t) => t.startsWith("audio/ogg")), "audio/ogg;codecs=opus");
  assert.equal(pickMimeType((t) => t === "audio/mp4"), "audio/mp4"); // Safari
  assert.equal(pickMimeType(() => false), "");
  assert.equal(pickMimeType(undefined), "");
  assert.equal(pickMimeType(() => { throw new Error("boom"); }), "");
});

test("extensionFor maps mime types to upload file extensions", () => {
  assert.equal(extensionFor("audio/webm;codecs=opus"), "webm");
  assert.equal(extensionFor("audio/ogg"), "ogg");
  assert.equal(extensionFor("audio/mp4"), "m4a");
  assert.equal(extensionFor(""), "webm");
});

test("voiceErrorMessage explains contract status codes", () => {
  assert.match(voiceErrorMessage({ status: 422 }), /No speech was detected.*nothing was saved/);
  assert.match(voiceErrorMessage({ status: 502 }), /speech-to-text service failed.*nothing was saved/);
  assert.match(voiceErrorMessage({ status: 415 }, "audio/ogg"), /audio format \(audio\/ogg\)/);
  assert.match(voiceErrorMessage({ status: 413 }), /too large or too long/);
  assert.match(voiceErrorMessage(new ApiError(400, "unknown sample", "r2", null)), /rejected: unknown sample \(request r2\)/);
  assert.match(voiceErrorMessage(new ApiError(500, "kaput", "req-1", null)), /kaput \(request req-1\)/);
});

test("micErrorMessage covers getUserMedia failures", () => {
  assert.match(micErrorMessage({ name: "NotAllowedError" }), /blocked/);
  assert.match(micErrorMessage({ name: "NotFoundError" }), /No microphone/);
  assert.match(micErrorMessage({ name: "NotSupportedError" }), /HTTPS or localhost/);
  assert.equal(typeof micErrorMessage({ name: "NotReadableError" }), "string");
});

test("errorDetail reads the contract error body", () => {
  assert.equal(errorDetail({ detail: "pet not found", request_id: "r1" }, 404), "pet not found");
  assert.equal(errorDetail(null, 500), "Request failed (500)");
  assert.equal(errorDetail({}, 503), "Request failed (503)");
  // FastAPI default validation shape
  assert.equal(
    errorDetail({ detail: [{ loc: ["body", "age"], msg: "must be an integer" }] }, 422),
    "age: must be an integer",
  );
  // Contract 422 whose detail already contains the messages: not duplicated
  const dup = errorDetail({ detail: "validation failed: age: must be an integer", errors: [{ loc: ["body", "age"], msg: "must be an integer" }] }, 422);
  assert.equal(dup, "validation failed: age: must be an integer");
  // Contract 422 with a generic detail: messages appended
  const gen = errorDetail({ detail: "validation failed", errors: [{ loc: ["body", "age"], msg: "too big" }] }, 422);
  assert.equal(gen, "validation failed: age: too big");
  assert.equal(errorDetail({ detail: { message: "nope" } }, 400), "nope");
});

test("asList accepts bare arrays and legacy wrappers", () => {
  assert.deepEqual(asList([1, 2]), [1, 2]);
  assert.deepEqual(asList({ data: [3] }), [3]);
  assert.deepEqual(asList({ items: [4] }), [4]);
  assert.deepEqual(asList({ status: "ok" }), []);
  assert.deepEqual(asList(null), []);
  assert.deepEqual(asList("x"), []);
});

test("apiPath encodes path segments", () => {
  assert.equal(apiPath("pets", "a/b?c", "notes"), "/api/pets/a%2Fb%3Fc/notes");
});

test("describeError appends the request id", () => {
  assert.equal(describeError(new ApiError(404, "pet not found", "req-9", null)), "pet not found (request req-9)");
  assert.equal(describeError(new Error("plain")), "plain");
  assert.equal(describeError(null), "Unknown error");
});

test("parseTimestamp treats naive backend timestamps as UTC", () => {
  assert.equal(parseTimestamp("2026-10-03T12:00:00").toISOString(), "2026-10-03T12:00:00.000Z");
  assert.equal(parseTimestamp("2026-10-03T12:00:00+02:00").toISOString(), "2026-10-03T10:00:00.000Z");
  assert.equal(parseTimestamp("2026-10-03T12:00:00Z").toISOString(), "2026-10-03T12:00:00.000Z");
  assert.equal(parseTimestamp("garbage"), null);
  assert.equal(parseTimestamp(""), null);
});
