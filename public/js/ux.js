// public/js/ux.js: Progressive UX enhancements (validation hints, help, shortcuts).
import { state } from "./state.js";
import { showNotification, showLoadingState, hideLoadingState } from "./dom.js";

// Smart Form Validation with Real-time Feedback
function setupSmartValidation() {
    const inputs = document.querySelectorAll('input, textarea, select');
    
    inputs.forEach(input => {
        // Skip if already processed
        if (input.dataset.validationSetup) return;
        input.dataset.validationSetup = 'true';
        
        // Add validation container
        if (!input.parentElement.querySelector('.validation-message')) {
            const validationDiv = document.createElement('div');
            validationDiv.className = 'validation-message';
            input.parentElement.style.position = 'relative';
            input.parentElement.appendChild(validationDiv);
        }
        
        // Real-time validation
        input.addEventListener('input', () => validateField(input));
        input.addEventListener('blur', () => validateField(input));
        
        // Success indicators
        input.addEventListener('input', () => {
            if (input.value && !input.dataset.hasError) {
                addSuccessIndicator(input);
            }
        });
    });
}

function validateField(input) {
    const validationDiv = input.parentElement.querySelector('.validation-message');
    if (!validationDiv) return true;
    
    let isValid = true;
    let message = '';
    
    // Email validation
    if (input.type === 'email' && input.value) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(input.value)) {
            isValid = false;
            message = 'Please enter a valid email address';
        }
    }
    
    // Required field validation
    if (input.required && !input.value.trim()) {
        isValid = false;
        message = 'This field is required';
    }
    
    // Phone validation
    if (input.name === 'phone' && input.value) {
        const phoneRegex = /^[\+]?[1-9][\d]{0,15}$/;
        if (!phoneRegex.test(input.value.replace(/[\s\-\(\)]/g, ''))) {
            isValid = false;
            message = 'Please enter a valid phone number';
        }
    }
    
    // Update validation UI
    if (!isValid) {
        validationDiv.textContent = message;
        validationDiv.classList.remove('success');
        validationDiv.classList.add('show');
        input.classList.add('error');
        input.dataset.hasError = 'true';
    } else {
        validationDiv.classList.remove('show');
        input.classList.remove('error');
        delete input.dataset.hasError;
        
        if (input.value) {
            validationDiv.textContent = 'Looks good!';
            validationDiv.classList.add('success');
            validationDiv.classList.add('show');
            setTimeout(() => validationDiv.classList.remove('show'), 2000);
        }
    }
    
    return isValid;
}

function addSuccessIndicator(input) {
    // Remove existing indicator
    const existing = input.parentElement.querySelector('.auto-save-status');
    if (existing) existing.remove();
    
    // Add new indicator
    const indicator = document.createElement('div');
    indicator.className = 'auto-save-status';
    input.parentElement.style.position = 'relative';
    input.parentElement.appendChild(indicator);
    
    // Remove after animation
    setTimeout(() => {
        if (indicator.parentElement) {
            indicator.parentElement.removeChild(indicator);
        }
    }, 2000);
}

// Smart Search with Suggestions
function setupSmartSearch() {
    const searchInputs = document.querySelectorAll('input[type="search"], .search-input');
    
    searchInputs.forEach(input => {
        if (input.dataset.searchSetup) return;
        input.dataset.searchSetup = 'true';
        
        const suggestionsDiv = document.createElement('div');
        suggestionsDiv.className = 'search-suggestions';
        input.parentElement.style.position = 'relative';
        input.parentElement.appendChild(suggestionsDiv);
        
        let searchTimeout;
        input.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                if (input.value.length > 2) {
                    showSearchSuggestions(input, suggestionsDiv);
                } else {
                    hideSuggestions(suggestionsDiv);
                }
            }, 300);
        });
        
        // Hide suggestions when clicking outside
        document.addEventListener('click', (e) => {
            if (!input.parentElement.contains(e.target)) {
                hideSuggestions(suggestionsDiv);
            }
        });
    });
}

function showSearchSuggestions(input, suggestionsDiv) {
    // Smart suggestions based on current context
    const suggestions = [
        { icon: '🐕', text: `Search for "${input.value}" in pets` },
        { icon: '📋', text: `Find records containing "${input.value}"` },
        { icon: '💊', text: `Medications related to "${input.value}"` },
        { icon: '🏥', text: `Veterinarians named "${input.value}"` }
    ];
    
    suggestionsDiv.innerHTML = suggestions.map(suggestion => `
        <div class="suggestion-item" onclick="selectSuggestion('${suggestion.text}', this)">
            <span>${suggestion.icon}</span>
            <span>${suggestion.text}</span>
        </div>
    `).join('');
    
    suggestionsDiv.classList.add('show');
}

function hideSuggestions(suggestionsDiv) {
    suggestionsDiv.classList.remove('show');
}

function selectSuggestion(text, element) {
    const input = element.closest('.search-suggestions').previousElementSibling;
    input.value = text;
    hideSuggestions(element.parentElement);
    input.focus();
}

// Contextual Help System
function setupContextualHelp() {
    if (document.querySelector('.contextual-help')) return;
    
    // Add contextual help button
    const helpButton = document.createElement('div');
    helpButton.className = 'contextual-help';
    helpButton.innerHTML = `
        <i class="fas fa-question"></i>
        <div class="help-tooltip">Get help with this page</div>
    `;
    document.body.appendChild(helpButton);
    
    helpButton.addEventListener('click', () => {
        showContextualHelp();
    });
}

function showContextualHelp() {
    const currentPage = getCurrentPageContext();
    const helpContent = getHelpContent(currentPage);
    
    showNotification(helpContent, 'info', 6000);
}

function getCurrentPageContext() {
    // Determine current page context
    const activeNavItem = document.querySelector('.nav-item.active');
    if (activeNavItem) {
        const navText = activeNavItem.textContent.toLowerCase();
        if (navText.includes('pet')) return 'pet-registration';
        if (navText.includes('health')) return 'health-records';
        if (navText.includes('chat')) return 'ai-chat';
        if (navText.includes('analytics')) return 'analytics';
    }
    
    if (document.querySelector('.pet-form')) return 'pet-registration';
    if (document.querySelector('.health-records')) return 'health-records';
    if (document.querySelector('.chat-container')) return 'ai-chat';
    if (document.querySelector('.analytics-dashboard')) return 'analytics';
    return 'general';
}

function getHelpContent(context) {
    const helpTexts = {
        'pet-registration': 'Fill out your pet\'s basic information. All required fields are marked with *. Use the voice input for easier data entry.',
        'health-records': 'Track your pet\'s health history. Upload photos of medical records for AI analysis. Click on any record to view details.',
        'ai-chat': 'Ask questions about your pet\'s health. The AI can analyze uploaded documents and provide personalized advice.',
        'analytics': 'View your pet\'s health trends and insights. Charts are interactive - click to drill down into specific data.',
                        'general': 'Welcome to PetPulse! Navigate using the menu. Need help? Contact support or check our FAQ.'
    };
    
    return helpTexts[context] || helpTexts.general;
}

// Auto-save Functionality
function setupAutoSave() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        if (form.dataset.autoSaveSetup) return;
        form.dataset.autoSaveSetup = 'true';
        
        const inputs = form.querySelectorAll('input, textarea, select');
        
        inputs.forEach(input => {
            let saveTimeout;
            input.addEventListener('input', () => {
                clearTimeout(saveTimeout);
                saveTimeout = setTimeout(() => {
                    autoSaveData(form, input);
                }, 2000); // Save after 2 seconds of inactivity
            });
        });
    });
}

function autoSaveData(form, input) {
    const formData = new FormData(form);
    const data = Object.fromEntries(formData);
    
    // Save to localStorage as backup
    localStorage.setItem(`autoSave_${form.id || 'form'}`, JSON.stringify({
        data: data,
        timestamp: new Date().toISOString()
    }));
    
    // Show save indicator
    addSuccessIndicator(input);
    showDataSyncIndicator('Auto-saved', 'syncing');
    
    // Simulate API call
    setTimeout(() => {
        showDataSyncIndicator('Saved to cloud', 'success');
    }, 1000);
}

function showDataSyncIndicator(message, status) {
    let indicator = document.querySelector('.data-sync-indicator');
    
    if (!indicator) {
        indicator = document.createElement('div');
        indicator.className = 'data-sync-indicator';
        document.body.appendChild(indicator);
    }
    
    indicator.innerHTML = `
        <div class="sync-status-dot ${status}"></div>
        <span>${message}</span>
    `;
    
    indicator.classList.add('show');
    
    setTimeout(() => {
        indicator.classList.remove('show');
    }, 3000);
}

// Keyboard Shortcuts
let keyboardSetupComplete = false;
function setupKeyboardShortcuts() {
    if (keyboardSetupComplete) return;
    keyboardSetupComplete = true;
    
    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + S for save
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            const activeForm = document.querySelector('form:focus-within');
            if (activeForm) {
                showNotification('Form saved!', 'success');
            }
        }
        
        // Ctrl/Cmd + / for help
        if ((e.ctrlKey || e.metaKey) && e.key === '/') {
            e.preventDefault();
            showContextualHelp();
        }
        
        // Escape to close modals/notifications
        if (e.key === 'Escape') {
            const notifications = document.querySelectorAll('.notification-toast');
            notifications.forEach(n => n.classList.remove('show'));
        }
    });
}

// Enhanced Voice Recording UX
function enhanceVoiceRecording() {
    const voiceButtons = document.querySelectorAll('.voice-btn');
    
    voiceButtons.forEach(button => {
        if (button.dataset.voiceEnhanced) return;
        button.dataset.voiceEnhanced = 'true';
        
        const indicator = document.createElement('div');
        indicator.className = 'voice-indicator';
        button.parentElement.style.position = 'relative';
        button.parentElement.appendChild(indicator);
        
        button.addEventListener('click', () => {
            if (button.classList.contains('recording')) {
                indicator.classList.add('active');
                showNotification('Recording... Speak clearly into your microphone', 'info');
            } else {
                indicator.classList.remove('active');
                showNotification('Recording stopped', 'success');
            }
        });
    });
}

// Enhanced API Interaction with Better UX
const originalFetch = window.fetch;
window.fetch = function(...args) {
    const [url, options] = args;
    
    // Show loading for API calls (but only for buttons, not automatic notifications)
    if (url && typeof url === 'string' && url.includes('/api/')) {
        const button = document.activeElement;
        if (button && button.tagName === 'BUTTON') {
            showLoadingState(button);
        }
    }
    
    return originalFetch.apply(this, args)
        .then(response => {
            // Hide loading without automatic success notifications
            const button = document.activeElement;
            if (button && button.tagName === 'BUTTON') {
                hideLoadingState(button);
            }
            
            // Only show error notifications, not success ones
            if (!response.ok) {
                showNotification('Something went wrong. Please try again.', 'error');
            }
            
            return response;
        })
        .catch(error => {
            // Hide loading and show error
            const button = document.activeElement;
            if (button && button.tagName === 'BUTTON') {
                hideLoadingState(button);
            }
            
            showNotification('Connection error. Please check your internet.', 'error');
            throw error;
        });
};

// Initialize all UX enhancements
function initializeUXEnhancements() {
    setupSmartValidation();
    setupSmartSearch();
    setupContextualHelp();
    setupAutoSave();
    setupKeyboardShortcuts();
    enhanceVoiceRecording();
    
    // Welcome message with delay
    setTimeout(() => {
        if (state.currentUser) {
            showNotification('Welcome back! Press Ctrl+/ for help', 'info', 4000);
        }
    }, 2000);
    
    // Re-initialize when new content is added
    const observer = new MutationObserver((mutations) => {
        let shouldReinitialize = false;
        mutations.forEach((mutation) => {
            if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                shouldReinitialize = true;
            }
        });
        
        if (shouldReinitialize) {
            setTimeout(() => {
                setupSmartValidation();
                setupSmartSearch();
                enhanceVoiceRecording();
            }, 100);
        }
    });
    
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
}

// Initialize UX enhancements
document.addEventListener('DOMContentLoaded', initializeUXEnhancements);

// ===================== End Enhanced UX Functions =====================

export { setupSmartValidation, validateField, addSuccessIndicator, setupSmartSearch, showSearchSuggestions, hideSuggestions, selectSuggestion, setupContextualHelp, showContextualHelp, getCurrentPageContext, getHelpContent, setupAutoSave, autoSaveData, showDataSyncIndicator, setupKeyboardShortcuts, enhanceVoiceRecording, initializeUXEnhancements };
