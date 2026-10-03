// public/js/recorder.js: Voice recording controls.
import { state } from "./state.js";
import { showNotification } from "./dom.js";

// Voice recording functions
window.toggleRecording = async function () {
  if (!state.currentUser) {
    showNotification("Please log in first", 'error');
    return;
  }
  
  const petId = document.getElementById("pet-select").value;
  if (!petId) {
    showNotification("Please select a pet first", 'warning');
    return;
  }

  const button = document.getElementById("record-button");
  const statusElement = document.getElementById("status");
  const outputElement = document.getElementById("output");
  const loadingOverlay = document.getElementById("loading-overlay");

  // Prevent double-clicks during processing
  if (button.disabled) {
    console.log("Button disabled, ignoring click");
    return;
  }

  console.log("🔍 Current recording state:", state.isRecording);
  console.log("🔍 Button classes:", button.className);
  console.log("🔍 Button innerHTML:", button.innerHTML);

  if (!state.isRecording) {
    // Start recording
    try {
      console.log("🎙️ Starting recording...");
      button.disabled = true; // Prevent double-click
      
      const res = await fetch('/api/start_recording', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uid: state.currentUser.uid, pet: petId })
      });

      const data = await res.json();
      console.log('Start recording response:', data);
      
      if (data.status === "recording") {
        state.isRecording = true;
        button.innerHTML = '<i class="fas fa-stop"></i> <span>Stop Recording</span>';
        button.classList.add('recording');
        button.disabled = false; // Re-enable for stop action
        statusElement.textContent = "🎙️ Recording in progress... Click Stop when finished";
        statusElement.className = "status recording";
        statusElement.style.display = "block";
        outputElement.classList.remove("has-content");
        showNotification('Recording started! Speak clearly into your microphone.', 'info');
      } else {
        button.disabled = false; // Re-enable on error
        statusElement.textContent = "Failed to start recording: " + (data.message || data.error || "Unknown error");
        statusElement.className = "status error";
        statusElement.style.display = "block";
        showNotification('Failed to start recording. Please try again.', 'error');
      }
    } catch (error) {
      console.error('Error starting recording:', error);
      button.disabled = false; // Re-enable on error
      statusElement.textContent = "Failed to start recording";
      statusElement.className = "status error";
      statusElement.style.display = "block";
      showNotification('Network error. Please check your connection and try again.', 'error');
    }
  } else {
    // Stop recording
    try {
      console.log("🛑 Stopping recording...");
      button.disabled = true;
      button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>Processing...</span>';
      statusElement.textContent = "⏳ Processing your recording...";
      statusElement.className = "status processing";
      statusElement.style.display = "block";
      loadingOverlay.style.display = "flex";
      
      const res = await fetch('/api/stop_recording', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uid: state.currentUser.uid, pet: petId })
      });

      const data = await res.json();
      console.log('Stop recording response:', data);
      
      // Handle both successful AI processing and basic transcription
      if (data.status === "success" && data.transcript && data.summary) {
        // Full AI processing successful
        document.getElementById("transcript-content").textContent = data.transcript;
        document.getElementById("summary-content").textContent = data.summary;
        
        // Show content type badge
        const contentTypeBadge = document.getElementById("content-type-badge");
        const contentType = data.content_type || "MIXED";
        const confidence = data.confidence || 0.5;
        
        let badgeClass = "badge-mixed";
        let badgeIcon = "fas fa-brain";
        let badgeText = contentType;
        
        if (contentType === "MEDICAL") {
          badgeClass = "badge-medical";
          badgeIcon = "fas fa-heartbeat";
          badgeText = "Health & Medical";
        } else if (contentType === "DAILY_ACTIVITY") {
          badgeClass = "badge-activity";
          badgeIcon = "fas fa-heart";
          badgeText = "Daily Life & Activities";
        } else {
          badgeText = "Mixed Content";
        }
        
        contentTypeBadge.innerHTML = `<i class="${badgeIcon}"></i> ${badgeText}`;
        contentTypeBadge.className = `content-type-badge ${badgeClass}`;
        contentTypeBadge.style.display = "inline-block";
        
        outputElement.classList.add("has-content");
        statusElement.textContent = `${badgeText} processed successfully!`;
        statusElement.className = "status success";
        
        showNotification('Recording processed successfully!', 'success');
        
        setTimeout(() => {
          statusElement.style.display = "none";
        }, 5000);
      } else if (data.status === "stopped" && data.transcript) {
        // Basic transcription successful (no AI processing)
        document.getElementById("transcript-content").textContent = data.transcript;
        document.getElementById("summary-content").textContent = "Transcription completed successfully. AI processing was not available.";
        
        // Hide content type badge for basic transcription
        const contentTypeBadge = document.getElementById("content-type-badge");
        contentTypeBadge.style.display = "none";
        
        outputElement.classList.add("has-content");
        statusElement.textContent = "Recording transcribed successfully!";
        statusElement.className = "status success";
        
        showNotification('Recording transcribed successfully!', 'success');
        
        setTimeout(() => {
          statusElement.style.display = "none";
        }, 5000);
      } else if (data.status === "stopped" || data.status === "success") {
        // Recording stopped but no transcript (likely no speech detected)
        statusElement.textContent = "⚠️ Recording stopped but no speech was detected. Try speaking louder or closer to your microphone.";
        statusElement.className = "status error";
        showNotification('No speech detected in recording. Please try again.', 'warning');
      } else {
        // Error case
        const errorMsg = data.error || data.message || "Unknown error";
        statusElement.textContent = "Error processing recording: " + errorMsg;
        statusElement.className = "status error";
        console.error('Recording processing error:', data);
        showNotification('Error processing recording: ' + errorMsg, 'error');
      }
    } catch (error) {
      console.error('Error stopping recording:', error);
      statusElement.textContent = "Network error while processing recording";
      statusElement.className = "status error";
      showNotification('Network error. Please check your connection and try again.', 'error');
    } finally {
      // Always reset the button state regardless of success or failure
      console.log("🔄 Resetting recording UI state");
      loadingOverlay.style.display = "none";
      state.isRecording = false;
      button.innerHTML = '<i class="fas fa-microphone"></i> <span>Start Recording</span>';
      button.classList.remove('recording');
      button.disabled = false;
      
      // Ensure status is visible if there was an error
      if (statusElement.className.includes('error')) {
        statusElement.style.display = "block";
      }
    }
  }
};
