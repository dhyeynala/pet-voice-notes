// public/js/knowledge.js: Knowledge-base search.
import { state } from "./state.js";
import { loadInsightsData } from "./insights.js";
import { showNotification } from "./dom.js";

window.searchKnowledge = async function() {
  const query = document.getElementById('knowledge-search').value.trim();
  const resultsDiv = document.getElementById('knowledge-results');
  
  if (!query) {
    showNotification('Please enter a search query', 'error');
    return;
  }

  if (!state.selectedPet) {
    showNotification('Please select a pet first', 'error');
    return;
  }

  resultsDiv.innerHTML = `
    <div style="text-align: center; color: #667eea;">
      <i class="fas fa-spinner fa-spin"></i>
      <p>Searching veterinary knowledge base...</p>
    </div>
  `;

  try {
    const response = await fetch(`/api/pets/${state.selectedPet}/knowledge_search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query })
    });

    const data = await response.json();
    
    if (data.status === 'success' && data.results && data.results.length > 0) {
      resultsDiv.innerHTML = data.results.map(result => `
        <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid #667eea;">
          <h4 style="margin-bottom: 8px; color: #2c3e50;">${result.title}</h4>
          <p style="color: #666; line-height: 1.6;">${result.content}</p>
          <div style="margin-top: 8px; font-size: 0.85rem; color: #7f8c8d;">
            <strong>Category:</strong> ${result.category || 'General'} | 
            <strong>Severity:</strong> ${result.severity || 'N/A'} |
            <strong>Confidence:</strong> ${Math.round(result.score * 100)}%
          </div>
          ${result.symptoms && result.symptoms.length > 0 ? `
            <div style="margin-top: 8px; font-size: 0.85rem; color: #667eea;">
              <strong>Related symptoms:</strong> ${result.symptoms.join(', ')}
            </div>
          ` : ''}
        </div>
      `).join('');
      
      // Load health insights on first interaction
      if (!state.assistantDataLoaded) {
        console.log('Loading health insights on first knowledge search...');
        state.assistantDataLoaded = true;
        loadInsightsData();
      }
    } else {
      resultsDiv.innerHTML = `
        <div style="text-align: center; color: #7f8c8d;">
          <i class="fas fa-search"></i>
          <p>No results found for "${query}". Try different keywords or broader terms.</p>
        </div>
      `;
    }
  } catch (error) {
    console.error('Error searching knowledge:', error);
    resultsDiv.innerHTML = `
      <div style="text-align: center; color: #e53e3e;">
        <i class="fas fa-exclamation-triangle"></i>
        <p>Error searching knowledge base. Please try again.</p>
      </div>
    `;
  }
}
