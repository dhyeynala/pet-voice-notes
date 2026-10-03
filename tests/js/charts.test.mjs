// Charts are computed in the browser from typed analytics entries (no server chart builder).
import { test } from "node:test";
import assert from "node:assert/strict";
import { prepareChartData } from "../../public/js/charts.js";

const NOW = new Date(2026, 9, 3, 14, 0); // local time
const at = (daysAgo, hour = 12) => {
  const d = new Date(NOW);
  d.setDate(d.getDate() - daysAgo);
  d.setHours(hour, 0, 0, 0);
  return d.toISOString();
};

test("activity, energy, diet and overview come from the entries", () => {
  const entries = [
    { category: "exercise", duration: 30, timestamp: at(0) },
    { category: "exercise", duration: 50, timestamp: at(1) },
    { category: "energy_levels", level: 4, timestamp: at(0) },
    { category: "energy_levels", level: "n/a", timestamp: at(0) },
    { category: "diet", type: "breakfast", timestamp: at(0) },
  ];
  const c = prepareChartData(entries, NOW);
  assert.deepEqual(c.activity.data, [0, 0, 0, 0, 0, 1, 1]);
  assert.deepEqual(c.energy, [4]);
  assert.deepEqual(c.diet, { labels: ["breakfast"], data: [1] });
  assert.deepEqual(c.overview.data.labels, ["exercise", "energy levels", "diet"]);
});

test("exercise histogram counts only sessions with a stated duration", () => {
  const entries = [
    { category: "exercise", duration: 10, timestamp: at(0) },
    { category: "exercise", duration: 35, timestamp: at(0) },
    { category: "exercise", timestamp: at(0) },
    { category: "exercise", duration: 120, timestamp: at(2) },
  ];
  const { exercise } = prepareChartData(entries, NOW);
  assert.deepEqual(exercise.data.datasets[0].data, [1, 0, 1, 0, 0, 1]);
  assert.equal(prepareChartData([], NOW).exercise, null);
});

test("medication doses per day over 14 days and the hour heatmap", () => {
  const entries = [
    { category: "medication", name: "Apoquel", timestamp: at(0, 9) },
    { category: "medication", name: "Apoquel", timestamp: at(0, 21) },
    { category: "medication", name: "Apoquel", timestamp: at(20, 9) },
  ];
  const c = prepareChartData(entries, NOW);
  const doses = c.medication.data.datasets[0].data;
  assert.equal(doses.length, 14);
  assert.equal(doses.at(-1), 2);
  assert.equal(doses.reduce((a, b) => a + b, 0), 2);
  assert.equal(c.heatmap.activities[9], 2);
  assert.equal(c.heatmap.activities[21], 1);
  assert.equal(c.heatmap.max_activity, 2);
});
