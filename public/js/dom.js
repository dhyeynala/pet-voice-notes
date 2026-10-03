// public/js/dom.js: Shared DOM and UX helpers.
import { state } from "./state.js";

// Enhanced UX helper functions
function addLoadingState(element) {
  if (element) {
    element.classList.add('loading');
    element.disabled = true;
  }
}

function removeLoadingState(element) {
  if (element) {
    element.classList.remove('loading');
    element.disabled = false;
  }
}

function validateFormField(fieldId, validationFn, errorMessage) {
  const field = document.getElementById(fieldId);
  const formGroup = field?.closest('.form-group');
  const errorDiv = document.getElementById(fieldId + '-error');

  if (!field) return true;

  const isValid = validationFn(field.value);
  
  if (formGroup) {
    formGroup.classList.remove('error', 'success');
    formGroup.classList.add(isValid ? 'success' : 'error');
  }

  if (errorDiv) {
    errorDiv.textContent = isValid ? '' : errorMessage;
    errorDiv.classList.toggle('show', !isValid);
  }

  return isValid;
}

function updateCharacterCount(textareaId, countId, maxLength) {
  const textarea = document.getElementById(textareaId);
  const counter = document.getElementById(countId);
  
  if (textarea && counter) {
    const count = textarea.value.length;
    counter.textContent = count;
    counter.style.color = count > maxLength * 0.9 ? '#e53e3e' : '#7f8c8d';
  }
}

function showFeedback(message, type = 'success', duration = 3000) {
  const feedback = document.createElement('div');
  feedback.className = `feedback-${type}`;
  feedback.innerHTML = `
    <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-triangle'}"></i>
    ${message}
  `;
  
  document.body.appendChild(feedback);
  
  setTimeout(() => {
    feedback.style.animation = 'slideInDown 0.3s ease reverse';
    setTimeout(() => feedback.remove(), 300);
  }, duration);
}

function copyToClipboard(text, feedbackMessage = 'Copied to clipboard!') {
  navigator.clipboard.writeText(text).then(() => {
    const copyFeedback = document.createElement('div');
    copyFeedback.className = 'copy-feedback show';
    copyFeedback.innerHTML = `<i class="fas fa-clipboard-check"></i> ${feedbackMessage}`;
    
    document.body.appendChild(copyFeedback);
    
    setTimeout(() => {
      copyFeedback.classList.remove('show');
      setTimeout(() => copyFeedback.remove(), 300);
    }, 2000);
  });
}

function updateFormProgress() {
  const form = document.getElementById('add-pet-form');
  const progressFill = document.getElementById('form-progress');
  
  if (!form || !progressFill) return;
  
  const fields = form.querySelectorAll('input[required], select[required]');
  const filledFields = Array.from(fields).filter(field => field.value.trim() !== '');
  const progress = fields.length > 0 ? (filledFields.length / fields.length) * 100 : 0;
  
  progressFill.style.width = `${progress}%`;
}

function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// Enhanced pet selection with validation
function validatePetSelection() {
  const petSelect = document.getElementById('pet-select');
  const petStatus = document.getElementById('pet-status');
  const errorDiv = document.getElementById('pet-select-error');
  
  if (!state.selectedPet) {
    if (errorDiv) {
      errorDiv.textContent = 'Please select a pet to continue';
      errorDiv.classList.add('show');
    }
    if (petStatus) {
      petStatus.className = 'status-indicator error';
      petStatus.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Select Pet';
    }
    return false;
  }
  
  if (errorDiv) {
    errorDiv.classList.remove('show');
  }
  if (petStatus) {
    petStatus.className = 'status-indicator online';
    petStatus.innerHTML = '<i class="fas fa-circle"></i> Ready';
  }
  return true;
}

// Setup character counters and form validation
document.addEventListener('DOMContentLoaded', function() {
  // Character counters
  const chatInput = document.getElementById('chat-input');
  const textInput = document.getElementById('pet-input-text');
  
  if (chatInput) {
    const charCounter = document.getElementById('char-count');
    if (charCounter) {
      chatInput.addEventListener('input', () => updateCharacterCount('chat-input', 'char-count', 1000));
    }
  }
  
  if (textInput) {
    const textCharCounter = document.getElementById('text-char-count');
    if (textCharCounter) {
      textInput.addEventListener('input', () => updateCharacterCount('pet-input-text', 'text-char-count', 2000));
    }
  }

  // Form progress tracking
  const addPetForm = document.getElementById('add-pet-form');
  if (addPetForm) {
    const formFields = addPetForm.querySelectorAll('input, select');
    formFields.forEach(field => {
      field.addEventListener('input', debounce(updateFormProgress, 300));
      field.addEventListener('change', updateFormProgress);
    });
  }

  // Real-time validation for add pet form
  const petName = document.getElementById('pet-name');
  const animalType = document.getElementById('animal-type');
  
  if (petName) {
    petName.addEventListener('blur', () => {
      validateFormField('pet-name', 
        value => value.trim().length >= 2,
        'Pet name must be at least 2 characters long'
      );
    });
  }
  
  if (animalType) {
    animalType.addEventListener('change', () => {
      validateFormField('animal-type',
        value => value !== '',
        'Please select an animal type'
      );
    });
  }

  // Auto-save indicators for forms
  const forms = document.querySelectorAll('form');
  forms.forEach(form => {
    form.addEventListener('input', debounce(() => {
      const statusIndicator = form.querySelector('.status-indicator.saving');
      if (statusIndicator) {
        statusIndicator.style.display = 'inline-flex';
        setTimeout(() => {
          statusIndicator.style.display = 'none';
        }, 1000);
      }
    }, 1000));
  });
});

// Enable keyboard shortcuts
document.addEventListener('keydown', function(e) {
  // Ctrl/Cmd + Enter to send chat message
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    const activeElement = document.activeElement;
    if (activeElement && activeElement.id === 'chat-input') {
      e.preventDefault();
      sendChatMessage();
    }
  }
  
  // Escape to close any open modals or reset focus
  if (e.key === 'Escape') {
    const activeElement = document.activeElement;
    if (activeElement && activeElement.blur) {
      activeElement.blur();
    }
  }
});

// ===================== Enhanced UX JavaScript Functions =====================

// Smart Notification System
function showNotification(message, type = 'info', duration = 4000) {
    const notification = document.createElement('div');
    notification.className = `notification-toast ${type}`;
    
    const icon = type === 'success' ? '✓' : 
                 type === 'error' ? '✕' : 
                 type === 'warning' ? '⚠' : 'ℹ';
    
    notification.innerHTML = `
        <span style="font-size: 16px;">${icon}</span>
        <span>${message}</span>
    `;
    
    document.body.appendChild(notification);
    
    // Trigger animation
    setTimeout(() => notification.classList.add('show'), 100);
    
    // Auto remove
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => {
            if (notification.parentElement) {
                document.body.removeChild(notification);
            }
        }, 400);
    }, duration);
}

// Enhanced Loading States
function showLoadingState(element, message = 'Loading') {
    const originalContent = element.innerHTML;
    element.dataset.originalContent = originalContent;
    element.innerHTML = `
        <span class="loading-dots">${message}</span>
    `;
    element.disabled = true;
    element.classList.add('loading-shimmer');
}

function hideLoadingState(element) {
    if (element.dataset.originalContent) {
        element.innerHTML = element.dataset.originalContent;
        delete element.dataset.originalContent;
    }
    element.disabled = false;
    element.classList.remove('loading-shimmer');
}

export { addLoadingState, removeLoadingState, validateFormField, updateCharacterCount, showFeedback, copyToClipboard, updateFormProgress, debounce, validatePetSelection, showNotification, showLoadingState, hideLoadingState };
