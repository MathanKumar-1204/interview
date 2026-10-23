/**
 * Dashboard JavaScript handlers
 */
document.addEventListener("DOMContentLoaded", () => {
  const llmSelect = document.getElementById("dashboard_llm_provider");
  const voiceSelect = document.getElementById("dashboard_voice_engine");
  const notice = document.getElementById("prefSaveNotice");

  let noticeTimeout = null;
  async function savePreferences() {
    if (!llmSelect || !voiceSelect) return;
    try {
      const res = await fetch("/api/user/preferences", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          llm_provider: llmSelect.value,
          voice_engine: voiceSelect.value
        })
      });
      if (res.ok) {
        if (notice) {
          notice.style.display = "inline-flex";
          clearTimeout(noticeTimeout);
          noticeTimeout = setTimeout(() => {
            notice.style.display = "none";
          }, 2500);
        }
      }
    } catch (e) {
      console.warn("Could not save studio preferences:", e);
    }
  }

  if (llmSelect) llmSelect.addEventListener("change", savePreferences);
  if (voiceSelect) voiceSelect.addEventListener("change", savePreferences);
});

async function deleteInterview(interviewId) {
  if (!confirm("Are you sure you want to delete this interview and its associated reports? This action cannot be undone.")) {
    return;
  }

  try {
    const response = await fetch(`/api/interviews/${interviewId}`, {
      method: 'DELETE',
      headers: { 'Accept': 'application/json' }
    });

    const data = await response.json();
    if (response.ok && data.success) {
      const row = document.getElementById(`interview-row-${interviewId}`);
      if (row) {
        row.style.transition = 'opacity 0.3s ease';
        row.style.opacity = '0';
        setTimeout(() => row.remove(), 300);
      } else {
        window.location.reload();
      }
    } else {
      alert(data.error || "Failed to delete interview.");
    }
  } catch (err) {
    alert("Network error: " + err.message);
  }
}
