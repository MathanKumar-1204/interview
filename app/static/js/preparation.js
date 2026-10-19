/**
 * Interview Preparation JavaScript
 */
document.addEventListener("DOMContentLoaded", () => {
  const updateTitleBtn = document.getElementById("updateTitleBtn");
  const editJobTitle = document.getElementById("editJobTitle");
  const retryPlanBtn = document.getElementById("retryPlanBtn");

  if (updateTitleBtn && editJobTitle) {
    updateTitleBtn.addEventListener("click", async () => {
      const newTitle = editJobTitle.value.trim();
      if (!newTitle) {
        alert("Job title cannot be empty.");
        return;
      }

      updateTitleBtn.disabled = true;
      updateTitleBtn.textContent = "Saving...";

      try {
        const response = await fetch(`/api/interviews/${interviewId}/update-title`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json"
          },
          body: JSON.stringify({ job_title: newTitle })
        });

        const data = await response.json();
        if (response.ok && data.success) {
          updateTitleBtn.textContent = "Saved ✓";
          setTimeout(() => {
            updateTitleBtn.textContent = "Save Title Change";
            updateTitleBtn.disabled = false;
          }, 1500);
        } else {
          alert(data.error || "Failed to update job title.");
          updateTitleBtn.disabled = false;
          updateTitleBtn.textContent = "Save Title Change";
        }
      } catch (err) {
        alert("Error updating title: " + err.message);
        updateTitleBtn.disabled = false;
        updateTitleBtn.textContent = "Save Title Change";
      }
    });
  }

  if (retryPlanBtn) {
    retryPlanBtn.addEventListener("click", async () => {
      retryPlanBtn.disabled = true;
      retryPlanBtn.textContent = "Generating Plan...";

      try {
        const response = await fetch(`/api/interviews/${interviewId}/prepare`, {
          method: "POST",
          headers: { "Accept": "application/json" }
        });

        const data = await response.json();
        if (response.ok && data.success) {
          if (data.interview) {
            sessionStorage.setItem("interview_" + interviewId, JSON.stringify(data.interview));
            sessionStorage.setItem("current_interview", JSON.stringify(data.interview));
          }
          window.location.reload();
        } else {
          alert(data.error || "Failed to generate interview plan.");
          retryPlanBtn.disabled = false;
          retryPlanBtn.textContent = "⚡ Generate Interview Plan";
        }
      } catch (err) {
        alert("Network error: " + err.message);
        retryPlanBtn.disabled = false;
        retryPlanBtn.textContent = "⚡ Generate Interview Plan";
      }
    });
  }
});
