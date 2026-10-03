// public/js/insights.js: AI health insights panel.
import { state } from "./state.js";

// AI Assistant Functions
async function loadAssistantData() {
  if (!state.selectedPet) return;
  
  // Update AI health summary with loading state
  const summaryDiv = document.getElementById('ai-health-summary');
  summaryDiv.innerHTML = `
    <div style="text-align: center;">
      <div style="font-size: 2.5rem; margin-bottom: 10px;">🔄</div>
      <div style="font-size: 1.2rem; font-weight: 600; margin-bottom: 10px;">Loading Health Summary...</div>
      <div style="opacity: 0.9;">
        <i class="fas fa-spinner fa-spin"></i> Analyzing your pet's health data...
      </div>
    </div>
  `;
  
  try {
    // Load AI health summary
    const response = await fetch(`/api/pets/${state.selectedPet}/assistant_summary`);
    const data = await response.json();
    
    if (data.status === 'success' && data.summary) {
      summaryDiv.innerHTML = `
        <div style="text-align: left;">
          <div style="display: flex; align-items: center; margin-bottom: 15px;">
            <div style="font-size: 2rem; margin-right: 10px;">🏥</div>
            <div style="font-size: 1.2rem; font-weight: 600;">AI Health Summary</div>
          </div>
          <div style="line-height: 1.6; opacity: 0.95; font-size: 0.95rem; white-space: pre-line;">
            ${data.summary}
          </div>
          <div style="margin-top: 15px; font-size: 0.85rem; opacity: 0.8; border-top: 1px solid rgba(255,255,255,0.2); padding-top: 10px;">
            Based on ${data.data_sources?.length || 0} data sources • Updated ${new Date().toLocaleString()}
          </div>
        </div>
      `;
    } else {
      summaryDiv.innerHTML = `
        <div style="text-align: center;">
          <div style="font-size: 2.5rem; margin-bottom: 10px;">🤖</div>
          <div style="font-size: 1.2rem; font-weight: 600; margin-bottom: 10px;">AI Assistant Ready</div>
          <div style="opacity: 0.9;">Ask me anything about your pet's health, behavior, or symptoms</div>
        </div>
      `;
    }
  } catch (error) {
    console.error('Error loading assistant data:', error);
    summaryDiv.innerHTML = `
      <div style="text-align: center;">
        <div style="font-size: 2.5rem; margin-bottom: 10px;">🤖</div>
        <div style="font-size: 1.2rem; font-weight: 600; margin-bottom: 10px;">AI Assistant Ready</div>
        <div style="opacity: 0.9;">Ask me anything about your pet's health, behavior, or symptoms</div>
      </div>
    `;
  }
}

async function loadInsightsData() {
  if (!state.selectedPet) return;
  
  // Update AI health summary with loading state
  const summaryDiv = document.getElementById('ai-health-summary');
  summaryDiv.innerHTML = `
    <div style="text-align: center;">
      <div style="font-size: 2.5rem; margin-bottom: 10px;">🔄</div>
      <div style="font-size: 1.2rem; font-weight: 600; margin-bottom: 10px;">Loading Health Insights...</div>
      <div style="opacity: 0.9;">
        <i class="fas fa-spinner fa-spin"></i> Analyzing your pet's health patterns...
      </div>
    </div>
  `;
  
  try {
    // Load AI health summary
    const response = await fetch(`/api/pets/${state.selectedPet}/assistant_summary`);
    const data = await response.json();
    
    if (data.status === 'success' && data.summary) {
      summaryDiv.innerHTML = `
        <div style="text-align: left;">
          <div style="display: flex; align-items: center; margin-bottom: 15px;">
            <div style="font-size: 2rem; margin-right: 10px;">🏥</div>
            <div style="font-size: 1.2rem; font-weight: 600;">AI Health Insights</div>
          </div>
          <div style="line-height: 1.6; opacity: 0.95; font-size: 0.95rem; white-space: pre-line;">
            ${data.summary}
          </div>
          <div style="margin-top: 15px; font-size: 0.85rem; opacity: 0.8; border-top: 1px solid rgba(255,255,255,0.2); padding-top: 10px;">
            Based on ${data.data_sources?.length || 0} data sources • Updated ${new Date().toLocaleString()}
          </div>
        </div>
      `;
    } else {
      summaryDiv.innerHTML = `
        <div style="text-align: center;">
          <div style="font-size: 2.5rem; margin-bottom: 10px;">🔍</div>
          <div style="font-size: 1.2rem; font-weight: 600; margin-bottom: 10px;">Ready for Analysis</div>
          <div style="opacity: 0.9;">Use the search tool above or ask the AI assistant questions to get personalized insights</div>
        </div>
      `;
    }
  } catch (error) {
    console.error('Error loading insights data:', error);
    summaryDiv.innerHTML = `
      <div style="text-align: center;">
        <div style="font-size: 2.5rem; margin-bottom: 10px;">🔍</div>
        <div style="font-size: 1.2rem; font-weight: 600; margin-bottom: 10px;">Ready for Analysis</div>
        <div style="opacity: 0.9;">Use the search tool above or ask the AI assistant questions to get personalized insights</div>
      </div>
    `;
  }
}

export { loadAssistantData, loadInsightsData };
