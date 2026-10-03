// Dates in the UI (live-test regression): chat "Sources" showed every cited note one day early
// in America/New_York. A citation date is a calendar day the backend computed in the request's
// tz ("2026-10-03"); `new Date("2026-10-03")` is UTC midnight, which is Oct 2 west of UTC.
// node --test runs each file in its own process, so setting TZ here is local to this file.
import { test } from "node:test";
import assert from "node:assert/strict";
import { formatDate, formatDateTime, formatDay, parseTimestamp } from "../../public/js/dom.js";

const US = { locale: "en-US" };

function inZone(tz, fn) {
  const saved = process.env.TZ;
  process.env.TZ = tz;
  try {
    fn();
  } finally {
    process.env.TZ = saved;
  }
}

test("a citation date shows that exact calendar day in every browser zone", () => {
  for (const tz of ["America/New_York", "America/Los_Angeles", "Pacific/Honolulu", "UTC", "Asia/Tokyo", "Pacific/Kiritimati"]) {
    inZone(tz, () => {
      assert.equal(formatDate("2026-10-03", US), "Oct 3, 2026", tz);
      assert.equal(parseTimestamp("2026-10-03").getDate(), 3, tz);
      assert.equal(formatDateTime("2026-10-03", US), "Oct 3, 2026", tz);
    });
  }
});

test("the citation and the notes list agree for a note recorded in the evening (ET)", () => {
  inZone("America/New_York", () => {
    // 4:32 PM ET on Oct 3 (the user's recording) and 9:30 PM ET (already Oct 4 in UTC).
    for (const createdAt of ["2026-10-03T20:32:00+00:00", "2026-10-04T01:30:00Z"]) {
      const noteList = formatDateTime(createdAt, US); // notes list
      const source = formatDate("2026-10-03", US); // chat Sources: backend local date in America/New_York
      assert.ok(noteList.startsWith(`${source} `), `${noteList} vs ${source}`);
      assert.equal(formatDate(createdAt, US), source);
    }
    assert.equal(formatDateTime("2026-10-03T20:32:00+00:00", US), "Oct 3, 2026 04:32 PM");
  });
});

test("dates never use an ambiguous numeric day/month order", () => {
  inZone("Europe/London", () => {
    assert.equal(formatDate("2026-10-02", { locale: "en-GB" }), "2 Oct 2026");
    assert.equal(formatDate("2026-10-02", US), "Oct 2, 2026");
    assert.doesNotMatch(formatDateTime("2026-10-02T09:00:00Z", { locale: "en-GB" }), /\d{1,2}\/\d{1,2}\/\d{4}/);
    assert.equal(formatDay(new Date(2026, 9, 2), US), "Oct 2");
  });
});

test("timestamps keep their UTC meaning; junk is passed through or empty", () => {
  inZone("America/New_York", () => {
    assert.equal(parseTimestamp("2026-10-03 12:00:00").toISOString(), "2026-10-03T12:00:00.000Z");
    assert.equal(formatDate("not a date"), "not a date");
    assert.equal(formatDate(""), "");
    assert.equal(formatDateTime(null), "");
  });
});
