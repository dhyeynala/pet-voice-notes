// public/js/charts.js: Analytics charts (Chart.js).
import { state } from "./state.js";

// Chart variables
let activityChart, energyChart, dietChart, overviewChart, exerciseHistogram, medicationChart;

// Enhanced update charts function
async function updateCharts() {
  if (!state.selectedPet) return;

  // Show loading states on all charts
  const chartIds = ['activityChart', 'energyChart', 'dietChart', 'overviewChart', 'exerciseHistogram', 'medicationChart', 'activityHeatmap'];
  chartIds.forEach(chartId => showChartLoading(chartId));

  try {
    // Get visualization data from enhanced API
    const response = await fetch(`/api/pets/${state.selectedPet}/visualizations?days=30`);
    const data = await response.json();
    
    if (data.visualizations) {
      // Create/update all charts
      updateActivityChart(data.visualizations.weekly_activity);
      updateEnergyChart(data.visualizations.energy_distribution);
      updateDietChart(data.visualizations.diet_frequency);
      updateOverviewChart(data.visualizations.health_overview);
      updateExerciseHistogram(data.visualizations.exercise_histogram);
      updateMedicationChart(data.visualizations.medication_adherence);
      updateActivityHeatmap(data.visualizations.activity_heatmap);
    }
    
    // Hide loading states
    chartIds.forEach(chartId => hideChartLoading(chartId));
    
  } catch (error) {
    console.error('Error updating charts:', error);
    // Hide loading states on error and fallback to basic charts
    chartIds.forEach(chartId => hideChartLoading(chartId));
    await updateChartsBasic();
  }
}

// Fallback to basic chart functionality
async function updateChartsBasic() {
  try {
    const response = await fetch(`/api/pets/${state.selectedPet}/analytics?days=30`);
    const data = await response.json();
    const entries = data.data || [];
    
    // Prepare data for charts
    const chartData = prepareChartData(entries);
    
    // Update Activity Chart
    updateActivityChart(chartData.activity);
    
    // Update Energy Chart
    updateEnergyChart(chartData.energy);
    
    // Update Diet Chart
    updateDietChart(chartData.diet);
    
    // Update Overview Chart
    updateOverviewChart(chartData.overview);
    
  } catch (error) {
    console.error('Error updating charts:', error);
  }
}

function prepareChartData(entries) {
  const last7Days = [];
  const today = new Date();
  
  for (let i = 6; i >= 0; i--) {
    const date = new Date(today);
    date.setDate(date.getDate() - i);
    last7Days.push(date.toISOString().split('T')[0]);
  }
  
  // Activity data (exercise entries + daily_activity entries per day)
  const activityData = last7Days.map(date => {
    return entries.filter(entry => 
      (entry.category === 'exercise' || entry.category === 'daily_activity') && 
      entry.timestamp.startsWith(date)
    ).length;
  });
  
  // Energy data
  const energyData = entries
    .filter(entry => entry.category === 'energy_levels')
    .map(entry => entry.level || 3);
  
  // Diet data (meals per type)
  const dietTypes = {};
  entries.filter(entry => entry.category === 'diet').forEach(entry => {
    const type = entry.type || 'meal';
    dietTypes[type] = (dietTypes[type] || 0) + 1;
  });
  
  // Overview data (entries per category)
  const overview = {};
  entries.forEach(entry => {
    const category = entry.category;
    overview[category] = (overview[category] || 0) + 1;
  });
  
  return {
    activity: { labels: last7Days.map(date => new Date(date).toLocaleDateString()), data: activityData },
    energy: energyData,
    diet: dietTypes,
    overview: overview
  };
}

// Helper function to show loading state on charts
function showChartLoading(chartId) {
  const canvas = document.getElementById(chartId);
  if (canvas) {
    const container = canvas.parentElement;
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'chart-loading';
    loadingDiv.style.cssText = `
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      text-align: center;
      color: #7f8c8d;
      z-index: 10;
      font-size: 14px;
    `;
    loadingDiv.innerHTML = '<i class="fas fa-spinner fa-spin"></i><br><span style="margin-top: 8px; display: block;">Loading chart...</span>';
    
    // Remove existing loading div if present
    const existingLoading = container.querySelector('.chart-loading');
    if (existingLoading) {
      existingLoading.remove();
    }
    
    container.style.position = 'relative';
    container.appendChild(loadingDiv);
  }
}

// Helper function to hide chart loading state
function hideChartLoading(chartId) {
  const canvas = document.getElementById(chartId);
  if (canvas) {
    const container = canvas.parentElement;
    const loadingDiv = container.querySelector('.chart-loading');
    if (loadingDiv) {
      loadingDiv.remove();
    }
  }
}

// Enhanced chart update functions
function updateActivityChart(input) {
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

function updateEnergyChart(input) {
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

function updateDietChart(input) {
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

function updateOverviewChart(input) {
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

function updateExerciseHistogram(chartConfig) {
  const ctx = document.getElementById('exerciseHistogram');
  if (!ctx) return;
  
  if (exerciseHistogram) exerciseHistogram.destroy();
  
  if (chartConfig && chartConfig.data) {
    exerciseHistogram = new Chart(ctx, chartConfig);
  }
}

function updateMedicationChart(chartConfig) {
  const ctx = document.getElementById('medicationChart');
  if (!ctx) return;
  
  if (medicationChart) medicationChart.destroy();
  
  if (chartConfig && chartConfig.data) {
    medicationChart = new Chart(ctx, chartConfig);
  }
}

function updateActivityHeatmap(heatmapData) {
  const container = document.getElementById('activityHeatmap');
  if (!container || !heatmapData) return;
  
  const { hours, activities, max_activity } = heatmapData;
  
  container.innerHTML = '';
  
  hours.forEach((hour, index) => {
    const activity = activities[index] || 0;
    const intensity = max_activity > 0 ? activity / max_activity : 0;
    
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

export { updateCharts, updateChartsBasic, prepareChartData, showChartLoading, hideChartLoading, updateActivityChart, updateEnergyChart, updateDietChart, updateOverviewChart, updateExerciseHistogram, updateMedicationChart, updateActivityHeatmap };
