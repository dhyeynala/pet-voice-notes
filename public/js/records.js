// public/js/records.js: PDF medical-record upload.
import { state } from "./state.js";
import { showNotification } from "./dom.js";

function setupPdfForm() {
  // PDF upload form handler
  const pdfForm = document.getElementById("pdf-form");
  if (pdfForm) {
    pdfForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      
      if (!state.currentUser) {
        alert("User not authenticated");
        return;
      }
      
      const petId = document.getElementById("pet-select").value;
      if (!petId) {
        alert("Please select a pet first");
        return;
      }
      
      const fileInput = document.getElementById("pdf-file");
      const file = fileInput.files[0];
      
      if (!file) {
        alert("Please select a PDF file");
        return;
      }
      
      if (file.type !== "application/pdf") {
        alert("Please select a valid PDF file");
        return;
      }
      
      if (file.size > 10 * 1024 * 1024) { // 10MB limit
        alert("File size too large. Please select a file under 10MB");
        return;
      }
      
      try {
        // Show loading state
        const resultBox = document.getElementById("pdf-result");
        resultBox.innerHTML = '<div style="text-align: center; padding: 20px;"><i class="fas fa-spinner fa-spin"></i> Uploading and analyzing PDF...</div>';
        resultBox.classList.add("has-content");
        
        // Create FormData for file upload
        const formData = new FormData();
        formData.append("file", file);
        formData.append("uid", state.currentUser.uid);
        formData.append("pet", petId);
        
        const response = await fetch("/api/upload_pdf", {
          method: "POST",
          body: formData
        });
        
        const data = await response.json();
        
        if (response.ok && data.summary) {
          resultBox.innerHTML = `
            <div style="color: #38a169; margin-bottom: 15px;">
              <i class="fas fa-check-circle"></i> PDF uploaded and analyzed successfully!
            </div>
            <div style="background: white; padding: 15px; border-radius: 8px; border-left: 4px solid #4ecdc4;">
              <h4 style="margin-bottom: 10px;"><i class="fas fa-file-medical"></i> ${file.name}</h4>
              <div style="margin-bottom: 10px;"><strong>AI Summary:</strong></div>
              <div style="line-height: 1.6;">${data.summary}</div>
              ${data.url ? `<div style="margin-top: 10px;"><a href="${data.url}" target="_blank" style="color: #667eea;"><i class="fas fa-external-link-alt"></i> View Original Document</a></div>` : ''}
            </div>
          `;
          
          // Clear the file input
          fileInput.value = "";
          
          // Show success notification
          showNotification("PDF uploaded and analyzed successfully!", "success");
          
        } else {
          throw new Error(data.error || "Failed to process PDF");
        }
        
      } catch (error) {
        console.error("PDF upload error:", error);
        const resultBox = document.getElementById("pdf-result");
        resultBox.innerHTML = `
          <div style="color: #e53e3e; padding: 15px; background: #fff5f5; border: 1px solid #fed7d7; border-radius: 8px;">
            <i class="fas fa-exclamation-triangle"></i> Error uploading PDF: ${error.message}
          </div>
        `;
        showNotification("Error uploading PDF", "error");
      }
    });
  }
}

export { setupPdfForm };
