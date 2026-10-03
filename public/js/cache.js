// public/js/cache.js: Pet data preload / cache status.
import { showNotification } from "./dom.js";

// ===================== Pet Data Caching Functions =====================

async function preloadPetData(petId) {
  // Preload pet data for faster subsequent queries
  if (!petId) return;
  
  try {
    console.log(`🔄 Preloading data for pet ${petId}...`);
    
    const response = await fetch(`/api/pets/${petId}/preload`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ days: 30 })
    });
    
    const result = await response.json();
    
    if (result.status === 'success') {
      console.log('Pet data preloaded successfully:', result.data_summary);
      
      // Show success notification with data summary
      const summary = result.data_summary;
      const message = `🚀 ${summary.pet_name} data loaded: ${summary.analytics_entries} analytics, ${summary.voice_notes} voice notes, ${summary.text_inputs} text inputs`;
      showNotification(message, 'success', 3000);
      
      // Update cache status indicator if it exists
      updateCacheStatusIndicator(petId, true, summary);
      
    } else {
      console.error('Failed to preload pet data:', result.message);
      showNotification('Failed to preload pet data', 'error', 3000);
    }
    
  } catch (error) {
    console.error('Error preloading pet data:', error);
    showNotification('Error preloading pet data', 'error', 3000);
  }
}

async function checkCacheStatus(petId) {
  // Check if pet data is cached
  if (!petId) return false;
  
  try {
    const response = await fetch(`/api/pets/${petId}/cache/status`);
    const result = await response.json();
    
    if (result.status === 'success' && result.cached) {
      console.log('Pet data is cached:', result.cache_info);
      updateCacheStatusIndicator(petId, true, result.cache_info);
      return true;
    } else {
      console.log('⚠️ Pet data not cached');
      updateCacheStatusIndicator(petId, false);
      return false;
    }
    
  } catch (error) {
    console.error('Error checking cache status:', error);
    return false;
  }
}

async function clearPetCache(petId) {
  // Clear cached data for a pet
  if (!petId) return;
  
  try {
    const response = await fetch(`/api/pets/${petId}/cache/clear`, {
      method: 'POST'
    });
    
    const result = await response.json();
    
    if (result.status === 'success') {
      console.log('🗑️ Pet cache cleared successfully');
      showNotification('Pet data cache cleared', 'info', 2000);
      updateCacheStatusIndicator(petId, false);
    } else {
      console.error('Failed to clear cache:', result.message);
    }
    
  } catch (error) {
    console.error('Error clearing cache:', error);
  }
}

function updateCacheStatusIndicator(petId, isCached, cacheInfo = null) {
  // Update UI indicators for cache status
  // Add cache status to pet selector if it exists
  const petSelect = document.getElementById("pet-select");
  if (petSelect && petSelect.value === petId) {
    // Find or create cache indicator
    let indicator = document.getElementById("cache-status-indicator");
    if (!indicator) {
      indicator = document.createElement('div');
      indicator.id = "cache-status-indicator";
      indicator.style.cssText = `
        position: absolute;
        top: -8px;
        right: -8px;
        width: 16px;
        height: 16px;
        border-radius: 50%;
        font-size: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
        pointer-events: none;
      `;
      petSelect.parentElement.style.position = 'relative';
      petSelect.parentElement.appendChild(indicator);
    }
    
    if (isCached) {
      indicator.style.backgroundColor = '#38a169';
      indicator.style.color = 'white';
      indicator.innerHTML = '⚡';
      indicator.title = `Data cached: ${cacheInfo ? cacheInfo.analytics_entries + ' analytics entries' : 'Fast mode enabled'}`;
    } else {
      indicator.style.backgroundColor = '#e53e3e';
      indicator.style.color = 'white';
      indicator.innerHTML = '○';
      indicator.title = 'Data not cached - queries will be slower';
    }
  }
}

export { preloadPetData, checkCacheStatus, clearPetCache, updateCacheStatusIndicator };
