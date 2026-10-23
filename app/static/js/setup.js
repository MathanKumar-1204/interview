/**
 * Interview Setup JavaScript
 * Handles resume file validation and initiates plan preparation.
 */
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("setupForm");
  const resumeInput = document.getElementById("resume_file");
  const resumePreview = document.getElementById("resumePreview");
  const jdInput = document.getElementById("jd_file");
  const jdPreview = document.getElementById("jdPreview");
  const submitBtn = document.getElementById("submitBtn");
  const btnText = document.getElementById("btnText");
  const btnSpinner = document.getElementById("btnSpinner");
  const errorBox = document.getElementById("formErrorBox");
  const errorMessage = document.getElementById("formErrorMessage");

  function showError(msg) {
    errorMessage.textContent = msg;
    errorBox.style.display = "flex";
    errorBox.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function hideError() {
    errorBox.style.display = "none";
  }

  // Handle file preview updates
  function setupFileInputPreview(input, previewEl, dropzoneId) {
    const dropzone = document.getElementById(dropzoneId);
    if (!dropzone) return;

    ["dragenter", "dragover"].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
      });
    });

    ["dragleave", "drop"].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
      });
    });

    input.addEventListener("change", () => {
      if (input.files && input.files[0]) {
        const file = input.files[0];
        if (file.size > 10 * 1024 * 1024) {
          showError(`File "${file.name}" exceeds the 10 MB limit. Please select a smaller file.`);
          input.value = "";
          previewEl.style.display = "none";
          return;
        }
        hideError();
        previewEl.innerHTML = `✓ Selected: <b>${file.name}</b> (${(file.size / 1024).toFixed(1)} KB)`;
        previewEl.style.display = "flex";
      } else {
        previewEl.style.display = "none";
      }
    });
  }

  setupFileInputPreview(resumeInput, resumePreview, "resumeDropzone");
  if (jdInput && jdPreview) {
    setupFileInputPreview(jdInput, jdPreview, "jdDropzone");
  }

  // Model selection card styling toggle
  const modelRadios = document.querySelectorAll('input[name="llm_provider"]');
  modelRadios.forEach(radio => {
    radio.addEventListener("change", () => {
      document.querySelectorAll(".model-card").forEach(card => {
        card.style.borderColor = "var(--border-color)";
      });
      const parentLabel = radio.closest(".model-card");
      if (parentLabel) {
        parentLabel.style.borderColor = "var(--primary)";
      }
    });
  });

  // Form submission
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    hideError();

    const candidateName = document.getElementById("candidate_name").value.trim();
    const hasResume = resumeInput.files && resumeInput.files.length > 0;

    if (!candidateName) {
      showError("Please enter the candidate's name.");
      return;
    }

    if (!hasResume) {
      showError("Please upload the candidate's resume (PDF or DOCX).");
      return;
    }

    // Prepare FormData
    const formData = new FormData(form);

    submitBtn.disabled = true;
    btnText.style.display = "none";
    btnSpinner.style.display = "inline";

    try {
      // Step 1: Upload resume & create interview record
      const uploadRes = await fetch("/api/interviews", {
        method: "POST",
        body: formData,
        headers: { "Accept": "application/json" }
      });

      const uploadData = await uploadRes.json();
      if (!uploadRes.ok) {
        throw new Error(uploadData.error || "Failed to create interview session.");
      }

      const interviewId = uploadData.interview_id;
      if (uploadData.interview) {
        sessionStorage.setItem("interview_" + interviewId, JSON.stringify(uploadData.interview));
        sessionStorage.setItem("current_interview", JSON.stringify(uploadData.interview));
      }

      btnSpinner.textContent = "🤖 Generating Competency Plan...";

      // Step 2: Request structured interview planning
      const planRes = await fetch(`/api/interviews/${interviewId}/prepare`, {
        method: "POST",
        headers: {
          "Accept": "application/json",
          "Content-Type": "application/json"
        }
      });

      const planData = await planRes.json();
      if (planData.interview) {
        sessionStorage.setItem("interview_" + interviewId, JSON.stringify(planData.interview));
        sessionStorage.setItem("current_interview", JSON.stringify(planData.interview));
      }

      if (!planRes.ok) {
        // If planning fails, redirect to preparation page where error details are shown
        window.location.href = `/interviews/${interviewId}`;
        return;
      }

      // Success: redirect to interview preparation page
      window.location.href = `/interviews/${interviewId}`;

    } catch (err) {
      showError(err.message || "An unexpected error occurred during interview setup.");
      submitBtn.disabled = false;
      btnText.style.display = "inline";
      btnSpinner.style.display = "none";
      btnSpinner.textContent = "⏳ Extracting & Preparing...";
    }
  });
});
