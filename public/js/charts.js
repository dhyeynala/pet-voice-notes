// public/js/charts.js: analytics charts (vendored Chart.js, global `Chart`), computed in the
// browser from the typed analytics entries, and the chart that a chat answer can carry
// ({type, title, data}).
import { apiFetch, apiPath, asList } from "./api.js";
import { el, icon, formatDay, parseTimestamp } from "./dom.js";
import { state } from "./state.js";
import { entryFields, entryTime } from "./analytics.js";

// Chart instances
let activityChart, energyChart, dietChart, overviewChart, exerciseHistogram, medicationChart;

const CHART_IDS = ["activityChart", "energyChart", "dietChart", "overviewChart", "exerciseHistogram", "medicationChart", "activityHeatmap"];

/**
 * Build every analytics chart from GET /api/pets/{id}/analytics?days=30 (the typed entries).
 * The old server-side chart builder (/visualizations) is gone; charts are computed here.
 */
export async function updateCharts() {
  if (!state.selectedPet) return;
  CHART_IDS.forEach(showChartLoading);
  try {
    const entries = asList(await apiFetch(apiPath("pets", state.selectedPet, "analytics"), { query: { days: 30 } })).map(entryFields);
    const chartData = prepareChartData(entries);
    updateActivityChart(chartData.activity);
    updateEnergyChart(chartData.energy);
    updateDietChart(chartData.diet);
    updateOverviewChart(chartData.overview);
    updateExerciseHistogram(chartData.exercise);
    updateMedicationChart(chartData.medication);
    updateActivityHeatmap(chartData.heatmap);
  } catch (error) {
    console.error("Error updating charts:", error);
  } finally {
    CHART_IDS.forEach(hideChartLoading);
  }
}

function localDateKey(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const finite = (v) => (v === null || v === undefined || v === "" || typeof v === "boolean" ? null : Number.isFinite(Number(v)) ? Number(v) : null);

const EXERCISE_BINS = [[0, 15], [15, 30], [30, 45], [45, 60], [60, 90], [90, Infinity]];

function barConfig(labels, data, label, color, extra = {}) {
  return {
    type: "bar",
    data: { labels, datasets: [{ label, data, backgroundColor: color }] },
    options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }, ...extra },
  };
}

/** Chart inputs from typed analytics entries. `now` is injectable for tests. */
export function prepareChartData(entries, now = new Date()) {
  const days = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    days.push(d);
  }
  const timeOf = (e) => parseTimestamp(entryTime(e));
  const keyOf = (e) => {
    const t = timeOf(e);
    return t ? localDateKey(t) : null;
  };
  const activity = days.map((d) => entries.filter((e) => (e.category === "exercise" || e.category === "daily_activity") && keyOf(e) === localDateKey(d)).length);
  const energy = entries.filter((e) => e.category === "energy_levels" && finite(e.level) !== null).map((e) => finite(e.level));
  const dietTypes = {};
  entries.filter((e) => e.category === "diet").forEach((e) => {
    const type = e.type || "meal";
    dietTypes[type] = (dietTypes[type] || 0) + 1;
  });
  const perCategory = {};
  entries.forEach((e) => {
    perCategory[e.category] = (perCategory[e.category] || 0) + 1;
  });

  // Exercise minutes per session; sessions without a stated duration are not counted (no imputing).
  const durations = entries.filter((e) => e.category === "exercise").map((e) => finite(e.duration)).filter((d) => d !== null && d > 0);
  const exerciseCounts = EXERCISE_BINS.map(([lo, hi]) => durations.filter((d) => d >= lo && d < hi).length);
  const exerciseLabels = EXERCISE_BINS.map(([lo, hi]) => (hi === Infinity ? `${lo}+ min` : `${lo}-${hi} min`));

  // Medication doses logged per day, last 14 days.
  const medDays = [];
  for (let i = 13; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    medDays.push(d);
  }
  const meds = entries.filter((e) => e.category === "medication");
  const medCounts = medDays.map((d) => meds.filter((e) => keyOf(e) === localDateKey(d)).length);

  // Entries by local hour of day.
  const hours = Array.from({ length: 24 }, (_, h) => h);
  const byHour = hours.map(() => 0);
  entries.forEach((e) => {
    const t = timeOf(e);
    if (t) byHour[t.getHours()] += 1;
  });

  return {
    activity: { labels: days.map((d) => formatDay(d)), data: activity },
    energy,
    diet: { labels: Object.keys(dietTypes), data: Object.values(dietTypes) },
    overview: barConfig(Object.keys(perCategory).map((c) => String(c).replace(/_/g, " ")), Object.values(perCategory), "Entries", "#667eea"),
    exercise: durations.length ? barConfig(exerciseLabels, exerciseCounts, "Sessions", "#4ecdc4") : null,
    medication: meds.length ? barConfig(medDays.map((d) => `${d.getMonth() + 1}/${d.getDate()}`), medCounts, "Doses logged", "#66bb6a") : null,
    heatmap: { hours, activities: byHour, max_activity: Math.max(0, ...byHour) },
  };
}

function showChartLoading(chartId) {
  const canvas = document.getElementById(chartId);
  if (!canvas) return;
  const container = canvas.parentElement;
  const existing = container.querySelector(".chart-loading");
  if (existing) existing.remove();
  container.style.position = "relative";
  container.appendChild(el("div", { class: "chart-loading" }, icon("fas fa-spinner fa-spin"), el("span", { text: "Loading chart…" })));
}

function hideChartLoading(chartId) {
  const canvas = document.getElementById(chartId);
  const loading = canvas && canvas.parentElement.querySelector(".chart-loading");
  if (loading) loading.remove();
}

// Enhanced chart update functions
export function updateActivityChart(input) {
  const ctx = document.getElementById('activityChart');
  if (!ctx) return;
  
  if (activityChart) activityChart.destroy();
  
  let chartConfig;
  
  // Handle both chartConfig object and raw data
  if (input && input.type && input.data) {
    // Input is already a chart configuration
    chartConfig = input;
  } else if (input && input.labels && input.data) {
    // Input is raw data, create chart config
    chartConfig = {
      type: 'line',
      data: {
        labels: input.labels,
        datasets: [{
          label: 'Exercise Sessions',
          data: input.data,
          borderColor: '#667eea',
          backgroundColor: 'rgba(102, 126, 234, 0.1)',
          borderWidth: 3,
          fill: true,
          tension: 0.4
        }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            display: false
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              stepSize: 1
            }
          }
        }
      }
    };
  }
  
  if (chartConfig) {
    activityChart = new Chart(ctx, chartConfig);
  }
}

export function updateEnergyChart(input) {
  const ctx = document.getElementById('energyChart');
  if (!ctx) return;
  
  if (energyChart) energyChart.destroy();
  
  let chartConfig;
  
  // Handle both chartConfig object and raw data array
  if (input && input.type && input.data) {
    // Input is already a chart configuration
    chartConfig = input;
  } else if (input && Array.isArray(input)) {
    // Input is raw data array, create histogram chart config
    const histogram = [0, 0, 0, 0, 0]; // for levels 1-5
    input.forEach(level => {
      if (level >= 1 && level <= 5) {
        histogram[level - 1]++;
      }
    });
    
    chartConfig = {
      type: 'bar',
      data: {
        labels: ['Very Low', 'Low', 'Medium', 'High', 'Very High'],
        datasets: [{
          label: 'Energy Level Frequency',
          data: histogram,
          backgroundColor: ['#ff6b6b', '#ffa726', '#ffcc02', '#66bb6a', '#42a5f5']
        }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            display: false
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              stepSize: 1
            }
          }
        }
      }
    };
  }
  
  if (chartConfig) {
    energyChart = new Chart(ctx, chartConfig);
  }
}

export function updateDietChart(input) {
  const ctx = document.getElementById('dietChart');
  if (!ctx) return;
  
  if (dietChart) dietChart.destroy();
  
  let chartConfig;
  
  // Handle both chartConfig object and raw data
  if (input && input.type && input.data) {
    // Input is already a chart configuration
    chartConfig = input;
  } else if (input && input.labels && input.data) {
    // Input is raw data, create chart config
    chartConfig = {
      type: 'doughnut',
      data: {
        labels: input.labels,
        datasets: [{
          data: input.data,
          backgroundColor: ['#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4', '#feca57', '#ff9ff3']
        }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            position: 'bottom'
          }
        }
      }
    };
  }
  
  if (chartConfig) {
    dietChart = new Chart(ctx, chartConfig);
  }
}

export function updateOverviewChart(input) {
  const ctx = document.getElementById('overviewChart');
  if (!ctx) return;
  
  if (overviewChart) overviewChart.destroy();
  
  let chartConfig;
  
  // Handle both chartConfig object and raw data
  if (input && input.type && input.data) {
    // Input is already a chart configuration
    chartConfig = input;
  } else if (input && input.labels && input.datasets) {
    // Input is raw data, create chart config
    chartConfig = {
      type: 'radar',
      data: {
        labels: input.labels,
        datasets: input.datasets
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            display: false
          }
        },
        scales: {
          r: {
            beginAtZero: true,
            max: 5
          }
        }
      }
    };
  }
  
  if (chartConfig) {
    overviewChart = new Chart(ctx, chartConfig);
  }
}

export function updateExerciseHistogram(chartConfig) {
  const ctx = document.getElementById('exerciseHistogram');
  if (!ctx) return;
  
  if (exerciseHistogram) exerciseHistogram.destroy();
  
  if (chartConfig && chartConfig.data) {
    exerciseHistogram = new Chart(ctx, chartConfig);
  }
}

export function updateMedicationChart(chartConfig) {
  const ctx = document.getElementById('medicationChart');
  if (!ctx) return;
  
  if (medicationChart) medicationChart.destroy();
  
  if (chartConfig && chartConfig.data) {
    medicationChart = new Chart(ctx, chartConfig);
  }
}

export function updateActivityHeatmap(heatmapData) {
  const container = document.getElementById('activityHeatmap');
  if (!container || !heatmapData) return;
  
  const { hours, activities, max_activity } = heatmapData;
  if (!Array.isArray(hours) || !Array.isArray(activities)) return;

  container.replaceChildren();
  
  hours.forEach((hour, index) => {
    const activity = activities[index] || 0;
    const intensity = max_activity > 0 ? Math.min(1, Math.max(0, Number(activity) / max_activity)) || 0 : 0;
    
    const block = document.createElement('div');
    block.style.cssText = `
      width: 100%;
      height: 80px;
      background: rgba(102, 126, 234, ${0.1 + intensity * 0.8});
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.7rem;
      font-weight: 500;
      color: ${intensity > 0.5 ? 'white' : '#667eea'};
      position: relative;
      cursor: pointer;
      transition: all 0.2s ease;
    `;
    
    block.textContent = activity;
    block.title = `${hour}:00 - ${activity} activities`;
    
    block.addEventListener('mouseenter', () => {
      block.style.transform = 'scale(1.1)';
      block.style.zIndex = '10';
    });
    
    block.addEventListener('mouseleave', () => {
      block.style.transform = 'scale(1)';
      block.style.zIndex = '1';
    });
    
    container.appendChild(block);
  });
}

/** Normalize a chat chart payload {type, title, data} into a Chart.js config (or null). */
export function chatChartConfig(chart) {
  if (!chart || typeof chart !== "object") return null;
  const type = ["line", "bar", "pie", "doughnut", "radar", "polarArea", "scatter"].includes(chart.type) ? chart.type : "bar";
  let data = chart.data;
  if (Array.isArray(data)) {
    // [{label|date|x, value|count|y}] -> labels + one dataset
    data = {
      labels: data.map((p) => p.label ?? p.date ?? p.x ?? ""),
      datasets: [{ label: chart.title || "", data: data.map((p) => p.value ?? p.count ?? p.y ?? null) }],
    };
  } else if (data && !data.datasets && Array.isArray(data.labels) && Array.isArray(data.values)) {
    data = { labels: data.labels, datasets: [{ label: chart.title || "", data: data.values }] };
  }
  if (!data || !Array.isArray(data.labels) || !Array.isArray(data.datasets) || data.datasets.length === 0) return null;
  data = {
    labels: data.labels.map((l) => String(l)),
    datasets: data.datasets.map((d, i) => ({
      borderColor: ["#667eea", "#4ecdc4", "#ff6b6b", "#feca57"][i % 4],
      backgroundColor: type === "line" ? "rgba(102, 126, 234, 0.15)" : ["#667eea", "#4ecdc4", "#ff6b6b", "#feca57", "#96ceb4", "#ff9ff3"],
      ...d,
      label: d.label === undefined ? chart.title || "" : String(d.label),
    })),
  };
  return {
    type,
    data,
    options: {
      responsive: true,
      spanGaps: true,
      plugins: { title: { display: Boolean(chart.title), text: String(chart.title || "") }, legend: { display: data.datasets.length > 1 } },
      ...(type === "line" || type === "bar" ? { scales: { y: { beginAtZero: true } } } : {}),
    },
  };
}

/** Render a chat chart into a new canvas inside `container`. Returns the Chart or null. */
export function renderChatChart(container, chart) {
  const config = chatChartConfig(chart);
  if (!config || typeof Chart === "undefined") return null;
  const canvas = el("canvas", { width: 400, height: 220 });
  container.appendChild(canvas);
  try {
    return new Chart(canvas, config);
  } catch (error) {
    console.error("Chart render failed:", error);
    canvas.replaceWith(el("div", { class: "muted", text: "This chart could not be displayed." }));
    return null;
  }
}
