// public/js/chat.js: Assistant chat UI.
import { state } from "./state.js";
import { loadInsightsData } from "./insights.js";
import { updateCharacterCount, showNotification, showLoadingState, hideLoadingState } from "./dom.js";

// Reset all assistant UI and state when pet changes
function resetAssistantState() {
  console.log('Resetting assistant state for new pet...');
  
  // Reset assistant data loaded flag
  state.assistantDataLoaded = false;
  
  // Clear chat history - get the chat container and reset it to initial state
  const chatContainer = document.getElementById('chat-container');
  if (chatContainer) {
    chatContainer.innerHTML = `
      <div class="assistant-message">
        <div style="display: flex; align-items: flex-start; gap: 15px;">
          <div style="width: 45px; height: 45px; background: linear-gradient(135deg, #667eea, #764ba2); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 20px; flex-shrink: 0; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);">
            🤖
          </div>
          <div style="background: white; padding: 20px; border-radius: 16px; border: 1px solid #e1e8ed; flex: 1; line-height: 1.6; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);">
            <strong style="color: #667eea; font-size: 1.1rem;">Hello! I'm your Pet Health Assistant.</strong><br><br>
            I have access to all your pet's health data including:
            <br><br>
            🎙️ <strong>Voice recordings</strong> with AI summaries<br>
            📄 <strong>Medical documents</strong> and veterinary records<br>
            📊 <strong>Health tracking data</strong> and patterns<br>
            📝 <strong>Notes and observations</strong><br><br>
            <strong style="color: #667eea;">How can I help you today?</strong> Ask me about symptoms, patterns, medications, or anything related to your pet's health!
          </div>
        </div>
      </div>
    `;
  }
  
  // Clear chat input
  const chatInput = document.getElementById('chat-input');
  if (chatInput) {
    chatInput.value = '';
  }
  
  // Reset AI health summary to default state
  const summaryDiv = document.getElementById('ai-health-summary');
  if (summaryDiv) {
    summaryDiv.innerHTML = `
      <div style="text-align: center;">
        <div style="font-size: 2.5rem; margin-bottom: 10px;">🤖</div>
        <div style="font-size: 1.2rem; font-weight: 600; margin-bottom: 10px;">AI Health Insights</div>
        <div style="opacity: 0.9;">Ask a question below or use the chat to get personalized health insights based on your pet's data</div>
      </div>
    `;
  }
  
  // Clear knowledge search input and results
  const knowledgeSearch = document.getElementById('knowledge-search');
  if (knowledgeSearch) {
    knowledgeSearch.value = '';
  }
  
  const knowledgeResults = document.getElementById('knowledge-results');
  if (knowledgeResults) {
    knowledgeResults.innerHTML = `
      <div style="text-align: center; color: #7f8c8d;">
        <i class="fas fa-book-medical"></i>
        <p>Search our veterinary knowledge base for symptoms, treatments, and health information</p>
      </div>
    `;
  }
  
  console.log('Assistant state reset complete');
}

window.sendChatMessage = async function() {
  console.log('sendChatMessage called');
  const input = document.getElementById('chat-input');
  const sendButton = document.getElementById('send-chat');
  console.log('Chat input element:', input);
  
  if (!input) {
    console.error('Chat input element not found');
    showNotification('Chat input not found', 'error');
    return;
  }
  
  const message = input.value.trim();
  console.log('Message:', message);
  
  if (!message) {
    console.log('Empty message');
    showNotification('Please enter a message first', 'warning');
    input.focus();
    return;
  }
  
  if (!state.selectedPet) {
    console.log('No pet selected');
    showNotification('Please select a pet first', 'warning');
    return;
  }
  
  if (!state.currentUser) {
    console.log('User not authenticated');
    showNotification('Please log in first', 'error');
    return;
  }

  console.log('Adding user message to chat...');
  // Show loading state on button
  if (sendButton) {
    showLoadingState(sendButton, 'Sending');
  }
  input.disabled = true;
  
  // Add user message to chat
  addChatMessage(message, 'user');
  
  // Clear input and show loading
  input.value = '';
  updateCharacterCount('chat-input', 'char-count', 1000);
  console.log('Adding loading message...');
  addChatMessage('🤔 Analyzing your pet\'s data and generating response...', 'assistant', true);

  try {
    console.log('Sending request to API...');
    const response = await fetch(`/api/pets/${state.selectedPet}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        query: message
      })
    });

    console.log('Response received:', response.status);
    const data = await response.json();
    console.log('Response data:', data);
    
    // Remove loading message and add real response
    removeLastChatMessage();
    
    if (data.status === 'success') {
      // Always add response text if available, even if empty
      if (data.response) {
      console.log('Adding assistant response...');
      addChatMessage(data.response, 'assistant');
      } else {
        console.log('No text response, checking for visualizations...');
      }
      
      // If sources are provided, add them
      if (data.sources && data.sources.length > 0) {
        console.log('Adding sources...');
        addChatSources(data.sources);
      }
      
      // If visualizations are provided, add them
      if (data.visualizations && Object.keys(data.visualizations).length > 0) {
        console.log('Adding visualizations...');
        addChatVisualizations(data.visualizations, data.visualization_description);
      } else if (!data.response) {
        // If no response text AND no visualizations, show helpful message
        console.log('No response text or visualizations available');
        addChatMessage('I\'m processing your request, but there might not be enough data available yet. Try asking about something else or add some data for your pet first.', 'assistant');
      }
      
      // Show function call information if available (for debugging)
      if (data.function_calls_made && data.function_calls_made.length > 0) {
        console.log('Function calls made:', data.function_calls_made);
      }
      
      // Load health insights on first interaction
      if (!state.assistantDataLoaded) {
        console.log('Loading health insights on first interaction...');
        state.assistantDataLoaded = true;
        loadInsightsData();
      }
    } else {
      console.error('API error:', data.error || 'Unknown error');
      console.error('Full response data:', data);
      addChatMessage('Sorry, I encountered an error processing your request: ' + (data.error || 'Unknown error'), 'assistant');
    }
    
    // Reset UI state
    if (sendButton) {
      hideLoadingState(sendButton);
    }
    input.disabled = false;
    input.focus();
    
  } catch (error) {
    console.error('Error sending chat message:', error);
    removeLastChatMessage();
    addChatMessage('Sorry, I\'m having trouble connecting right now. Please check your internet connection and try again.', 'assistant');
    
    // Reset UI state
    if (sendButton) {
      hideLoadingState(sendButton);
    }
    input.disabled = false;
    input.focus();
    showNotification('Failed to send message. Please try again.', 'error');
  }
}

window.addChatMessage = function(message, sender, isLoading = false) {
  const container = document.getElementById('chat-container');
  const messageDiv = document.createElement('div');
  
  // Parse markdown for assistant messages only
  const processedMessage = sender === 'assistant' && !isLoading ? window.parseMarkdown(message) : message;
  
  if (sender === 'user') {
    messageDiv.innerHTML = `
      <div style="display: flex; align-items: flex-start; gap: 12px; justify-content: flex-end;">
        <div style="background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 15px; border-radius: 12px; max-width: 70%; line-height: 1.6;">
          ${message}
        </div>
        <div style="width: 40px; height: 40px; background: #667eea; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 18px; flex-shrink: 0;">
          👤
        </div>
      </div>
    `;
  } else {
    messageDiv.innerHTML = `
      <div style="display: flex; align-items: flex-start; gap: 12px;">
        <div style="width: 40px; height: 40px; background: linear-gradient(135deg, #667eea, #764ba2); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 18px; flex-shrink: 0;">
          🤖
        </div>
        <div style="background: white; padding: 15px; border-radius: 12px; border: 1px solid #e1e8ed; flex: 1; line-height: 1.6; ${isLoading ? 'opacity: 0.7;' : ''}">
          ${isLoading ? '<i class="fas fa-spinner fa-spin"></i> ' : ''}${processedMessage}
        </div>
      </div>
    `;
  }
  
  if (isLoading) {
    messageDiv.classList.add('loading-message');
  }
  
  container.appendChild(messageDiv);
  container.scrollTop = container.scrollHeight;
}

window.addChatSources = function(sources) {
  const container = document.getElementById('chat-container');
  const sourcesDiv = document.createElement('div');
  
  sourcesDiv.innerHTML = `
    <div style="display: flex; align-items: flex-start; gap: 12px;">
      <div style="width: 40px; height: 40px; background: #e1e8ed; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #667eea; font-size: 18px; flex-shrink: 0;">
        📚
      </div>
      <div style="background: #f8fafc; padding: 12px; border-radius: 8px; border: 1px solid #e1e8ed; flex: 1; font-size: 0.9rem;">
        <strong>Sources:</strong><br>
        ${sources.map(source => `• ${source.type}: ${source.summary || source.content}`.slice(0, 100) + '...').join('<br>')}
      </div>
    </div>
  `;
  
  container.appendChild(sourcesDiv);
  container.scrollTop = container.scrollHeight;
}

window.addChatVisualizations = function(visualizations, description) {
  const container = document.getElementById('chat-container');

  // Remove any previous visualization blocks
  const prevVizBlocks = container.querySelectorAll('.chat-visualization-block');
  prevVizBlocks.forEach(block => block.remove());

  const vizDiv = document.createElement('div');
  vizDiv.classList.add('chat-visualization-block');
  
  // Global chart map to track chart instances
  window._chatCharts = window._chatCharts || {};
  
  // Prepare valid charts only
  const validCharts = Object.entries(visualizations).filter(([chartName, chartConfig]) => {
    try {
      console.log('Checking chart:', chartName, chartConfig);
      if (!chartConfig.data ||
          !chartConfig.data.labels ||
          !chartConfig.data.datasets ||
          !chartConfig.data.datasets.length) {
        return false;
      }
      const dataLen = chartConfig.data.datasets[0].data.length;
      const chartType = (chartConfig.type || chartName).toLowerCase();
      // For line, area, activity_trend, sleep_pattern, require at least 2 data points
      if (["line", "area", "activity_trend", "sleep_pattern", "trend"].some(type => chartType.includes(type))) {
        if (chartConfig.data.labels.length < 2 || dataLen < 2) return false;
      } else {
        // For others, require at least 1 data point
        if (chartConfig.data.labels.length < 1 || dataLen < 1) return false;
      }
      return true;
    } catch (e) {
      console.log('Chart filter error:', chartName, e);
      return false;
    }
  });
  
  // If no valid charts, do not show visualization container
  if (validCharts.length === 0) {
    const noDataDiv = document.createElement('div');
    noDataDiv.classList.add('chat-visualization-block');
    noDataDiv.innerHTML = `
      <div style="display: flex; align-items: flex-start; gap: 12px;">
        <div style="width: 40px; height: 40px; background: #667eea; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 18px; flex-shrink: 0;">
          📊
        </div>
        <div style="background: white; padding: 15px; border-radius: 12px; border: 1px solid #e1e8ed; flex: 1; color: #aaa;">
          <div style="margin-bottom: 10px; color: #667eea; font-weight: 500;">
            No data available to display a visualization for this question.
          </div>
        </div>
      </div>
    `;
    container.appendChild(noDataDiv);
    container.scrollTop = container.scrollHeight;
    return;
  }
  
  // Create visualization container
  vizDiv.innerHTML = `
    <div style="display: flex; align-items: flex-start; gap: 12px;">
      <div style="width: 40px; height: 40px; background: #667eea; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 18px; flex-shrink: 0;">
        📊
      </div>
      <div style="background: white; padding: 15px; border-radius: 12px; border: 1px solid #e1e8ed; flex: 1;">
        <div style="margin-bottom: 10px; color: #667eea; font-weight: 500;">
          📈 Visualization: ${description || 'Data visualization'}
        </div>
        <div id="chat-visualizations" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px;">
        </div>
      </div>
    </div>
  `;
  
  container.appendChild(vizDiv);
  container.scrollTop = container.scrollHeight;
  
  // Render only valid charts after the container is added to DOM
  setTimeout(() => {
    const chartsContainer = vizDiv.querySelector('#chat-visualizations');
    chartsContainer.innerHTML = ''; // Clear any previous charts (no empty boxes)
    let chartIndex = 0;
    
    validCharts.forEach(([chartName, chartConfig]) => {
      const chartDiv = document.createElement('div');
      chartDiv.style.cssText = 'background: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e1e8ed;';
      
      const canvasId = `chat-chart-${chartIndex}`;
      chartDiv.innerHTML = `
        <h4 style="margin-bottom: 10px; color: #2c3e50; text-transform: capitalize;">${chartName.replace(/_/g, ' ')}</h4>
        <canvas id="${canvasId}" width="300" height="200"></canvas>
      `;
      
      chartsContainer.appendChild(chartDiv);
      
      // Create chart after canvas is in DOM
      setTimeout(() => {
        try {
          const canvas = document.getElementById(canvasId);
          if (canvas) {
            // Destroy previous chart if it exists
            if (window._chatCharts[canvasId]) {
              window._chatCharts[canvasId].destroy();
            }
            window._chatCharts[canvasId] = new Chart(canvas, chartConfig);
          }
        } catch (error) {
          console.error(`Error creating chart ${chartName}:`, error);
          chartDiv.innerHTML = `
            <div style="text-align: center; color: #e53e3e; padding: 20px;">
              <i class="fas fa-exclamation-triangle"></i>
              <p>Error displaying chart: ${error.message}</p>
            </div>
          `;
        }
      }, 100);
      
      chartIndex++;
    });
  }, 100);
}

window.removeLastChatMessage = function() {
  const container = document.getElementById('chat-container');
  const loadingMessage = container.querySelector('.loading-message');
  if (loadingMessage) {
    loadingMessage.remove();
  }
}

window.showQuickQuestions = function() {
  const loading = document.getElementById('quick-questions-loading');
  const buttons = document.getElementById('quick-questions-buttons');
  if (loading) loading.style.display = 'none';
  if (buttons) buttons.style.display = 'block';
}

window.hideQuickQuestions = function() {
  const loading = document.getElementById('quick-questions-loading');
  const buttons = document.getElementById('quick-questions-buttons');
  if (buttons) buttons.style.display = 'none';
  if (loading) {
    loading.innerHTML = '<i class="fas fa-info-circle"></i> Please add a pet first to use quick questions';
    loading.style.display = 'block';
  }
}

window.askQuickQuestion = function(question) {
  console.log('Quick question clicked:', question);
  console.log('Selected pet:', state.selectedPet);
  console.log('Current user:', state.currentUser);
  
  if (!state.currentUser) {
    console.error('User not authenticated');
    showNotification('Please log in first', 'error');
    return;
  }
  
  if (!state.selectedPet) {
    console.error('No pet selected');
    showNotification('Please select a pet first', 'error');
    return;
  }
  
  const chatInput = document.getElementById('chat-input');
  if (!chatInput) {
    console.error('Chat input element not found');
    showNotification('Chat interface not found', 'error');
    return;
  }
  
  console.log('Setting chat input value to:', question);
  chatInput.value = question;
  
  console.log('Calling sendChatMessage...');
  sendChatMessage();
}

export { resetAssistantState };
