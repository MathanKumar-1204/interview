/**
 * Live Spoken Interview Session Controller
 * Integrates ElevenLabs Conversational AI, Audio Waveform States, and Real-Time Transcript Management.
 */

let timerInterval = null;
let elapsedSeconds = 0;
let isCallActive = false;
let transcriptTurns = [];
let conversationId = null;

document.addEventListener("DOMContentLoaded", () => {
  const startBtn = document.getElementById("startInterviewBtn");
  const endBtn = document.getElementById("endInterviewBtn");
  const voiceOrb = document.getElementById("voiceOrb");
  const orbIcon = document.getElementById("orbIcon");
  const connectionBadge = document.getElementById("connectionBadge");
  const studioStateTitle = document.getElementById("studioStateTitle");
  const studioStateSubtitle = document.getElementById("studioStateSubtitle");
  const timerDisplay = document.getElementById("timerDisplay");
  const progressBarFill = document.getElementById("progressBarFill");
  const progressPercent = document.getElementById("progressPercent");
  const transcriptBox = document.getElementById("transcriptBox");
  const turnCounter = document.getElementById("turnCounter");
  const emptyTranscriptMsg = document.getElementById("emptyTranscriptMsg");
  const transcriptToggleBtn = document.getElementById("transcriptToggleBtn");
  const transcriptToggleHeader = document.getElementById("transcriptToggleHeader");
  const transcriptPanelBody = document.getElementById("transcriptPanelBody");
  const finalizingModal = document.getElementById("finalizingModal");
  const authWidgetMount = document.getElementById("authWidgetMount");

  // Format seconds to MM:SS
  function formatTime(totalSecs) {
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }

  // Update timer display & progress bar
  function tickTimer() {
    elapsedSeconds++;
    timerDisplay.textContent = formatTime(elapsedSeconds);

    const totalSeconds = targetDurationMinutes * 60;
    const pct = Math.min(100, Math.round((elapsedSeconds / totalSeconds) * 100));
    progressBarFill.style.width = `${pct}%`;
    progressPercent.textContent = `${pct}% Elapsed`;
  }

  function startTimer() {
    if (!timerInterval) {
      timerInterval = setInterval(tickTimer, 1000);
    }
  }

  function stopTimer() {
    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
  }

  // Append a turn to transcript
  function appendTranscriptTurn(role, text) {
    if (!text || !text.trim()) return;

    if (emptyTranscriptMsg) {
      emptyTranscriptMsg.style.display = "none";
    }

    const cleanRole = role === "agent" || role === "interviewer" ? "interviewer" : "candidate";
    const turn = {
      role: cleanRole,
      message: text.trim(),
      time_in_call_secs: elapsedSeconds
    };
    transcriptTurns.push(turn);

    const msgEl = document.createElement("div");
    msgEl.className = `transcript-message ${cleanRole}`;

    const roleLabel = cleanRole === "interviewer" ? "Alex (AI Interviewer)" : candidateName;
    msgEl.innerHTML = `
      <div class="message-role">${roleLabel} <span style="font-weight: normal; font-size: 0.7rem; color: var(--text-muted);">• ${formatTime(elapsedSeconds)}</span></div>
      <div>${escapeHtml(text.trim())}</div>
    `;

    transcriptBox.appendChild(msgEl);
    transcriptBox.scrollTop = transcriptBox.scrollHeight;

    turnCounter.textContent = `${transcriptTurns.length} exchange${transcriptTurns.length === 1 ? "" : "s"}`;

    // Sync turns with server in background
    syncTranscriptToServer();
  }

  function escapeHtml(string) {
    const div = document.createElement("div");
    div.innerText = string;
    return div.innerHTML;
  }

  async function syncTranscriptToServer() {
    try {
      await fetch(`/api/interviews/${interviewId}/transcript`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcript: transcriptTurns,
          conversation_id: conversationId
        })
      });
    } catch (e) {
      console.warn("Background transcript sync failed:", e);
    }
  }

  // Toggle Transcript panel
  if (transcriptToggleHeader && transcriptPanelBody) {
    transcriptToggleHeader.addEventListener("click", () => {
      const isVisible = transcriptPanelBody.style.display !== "none";
      transcriptPanelBody.style.display = isVisible ? "none" : "block";
      transcriptToggleBtn.textContent = isVisible ? "Expand ▼" : "Collapse ▲";
    });
  }

  // Handle Start Interview
  startBtn.addEventListener("click", async () => {
    if (!isElevenLabsConfigured) {
      alert("ElevenLabs credentials are not configured. Please check your .env settings.");
      return;
    }

    startBtn.disabled = true;
    startBtn.textContent = "Connecting to Microphone & Agent...";
    connectionBadge.className = "badge badge-amber";
    connectionBadge.textContent = "Requesting Mic & Token";

    try {
      // Step 1: Check microphone permissions explicitly
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Release initial probe stream
      stream.getTracks().forEach(t => t.stop());

      // Step 2: Fetch secure conversation credentials
      const res = await fetch(`/api/interviews/${interviewId}/conversation-credentials`);
      const creds = await res.json();

      if (!res.ok) {
        throw new Error(creds.error || "Failed to obtain interview conversation credentials.");
      }

      // Step 3: Initialize ElevenLabs Conversational AI
      if (creds.auth_mode === "signed_url") {
        if (!authWidgetMount) {
          throw new Error("Widget mount point not found.");
        }
        authWidgetMount.innerHTML = "";
        const widget = document.createElement("elevenlabs-convai");
        widget.setAttribute("signed-url", creds.signed_url);
        widget.setAttribute("dynamic-variables", JSON.stringify(creds.dynamic_variables));
        authWidgetMount.appendChild(widget);
      }

      // Update UI to Active Call
      isCallActive = true;
      startBtn.style.display = "none";
      endBtn.style.display = "inline-flex";
      connectionBadge.className = "badge badge-emerald";
      connectionBadge.textContent = "Live Voice Call";
      studioStateTitle.textContent = "Interview in Progress";
      studioStateSubtitle.textContent = "Alex is conducting your spoken interview. Speak naturally through your microphone.";
      voiceOrb.classList.add("listening");
      orbIcon.textContent = "🗣️";

      startTimer();

    } catch (err) {
      console.error("Call initialization error:", err);
      alert("Could not start interview call: " + err.message);
      startBtn.disabled = false;
      startBtn.textContent = "▶️ Start Interview Call";
      connectionBadge.className = "badge badge-rose";
      connectionBadge.textContent = "Connection Error";
    }
  });

  // Listen to ElevenLabs widget custom events
  window.addEventListener("elevenlabs-convai:call", (event) => {
    console.log("ElevenLabs Call Event:", event.detail);
    if (event.detail && event.detail.conversationId) {
      conversationId = event.detail.conversationId;
    }
  });

  window.addEventListener("elevenlabs-convai:message", (event) => {
    if (event.detail) {
      const role = event.detail.role || (event.detail.source === "user" ? "candidate" : "agent");
      const text = event.detail.message || event.detail.text || "";
      appendTranscriptTurn(role, text);

      // Adjust orb visualizer state based on who is speaking
      if (role === "candidate" || role === "user") {
        voiceOrb.className = "pulsing-orb listening";
        orbIcon.textContent = "🗣️";
      } else {
        voiceOrb.className = "pulsing-orb speaking";
        orbIcon.textContent = "🎙️";
      }
    }
  });

  // Handle End Interview & Finalize
  endBtn.addEventListener("click", async () => {
    if (!confirm("Are you ready to conclude your interview session and generate the evaluation report?")) {
      return;
    }

    await finalizeAndRedirect("normal");
  });

  async function finalizeAndRedirect(reason) {
    stopTimer();
    endBtn.disabled = true;
    finalizingModal.classList.add("active");

    try {
      // Step 1: Tell server call has ended
      await fetch(`/api/interviews/${interviewId}/end`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason: reason,
          conversation_id: conversationId
        })
      });

      // Step 2: Trigger finalization and report generation
      const finalRes = await fetch(`/api/interviews/${interviewId}/finalize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: conversationId,
          transcript: transcriptTurns
        })
      });

      const finalData = await finalRes.json();
      if (!finalRes.ok) {
        throw new Error(finalData.error || "Failed to finalize evaluation.");
      }

      // Success: redirect to report
      window.location.href = finalData.report_url || `/reports/${interviewId}`;

    } catch (err) {
      console.error("Finalization error:", err);
      finalizingModal.classList.remove("active");
      alert("Evaluation Notice: " + err.message);
      // If transcript was too short or interrupted, return to preparation or dashboard
      window.location.href = `/interviews/${interviewId}`;
    }
  }

  // Handle window unload gracefully
  window.addEventListener("beforeunload", () => {
    if (isCallActive) {
      navigator.sendBeacon(`/api/interviews/${interviewId}/end`, JSON.stringify({ reason: "interrupted" }));
    }
  });
});
