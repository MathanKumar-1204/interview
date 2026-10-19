/**
 * Live Spoken Interview Session Controller
 * Uses ElevenLabs Conversational AI Web SDK (@elevenlabs/client) to establish a real-time,
 * two-way voice stream with microphone capture, agent speech playback, and live transcript synchronization.
 */

import { Conversation } from "https://cdn.jsdelivr.net/npm/@elevenlabs/client/+esm";

let conversationInstance = null;
let timerInterval = null;
let elapsedSeconds = 0;
let isCallActive = false;
let isFinalizing = false;
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
  const audioStatusDot = document.getElementById("audioStatusDot");
  const audioStatusText = document.getElementById("audioStatusText");

  // Format seconds to MM:SS
  function formatTime(totalSecs) {
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }

  // Update timer display & progress bar
  function tickTimer() {
    elapsedSeconds++;
    if (timerDisplay) {
      timerDisplay.textContent = formatTime(elapsedSeconds);
    }

    const totalSeconds = (targetDurationMinutes || 15) * 60;
    const pct = Math.min(100, Math.round((elapsedSeconds / totalSeconds) * 100));
    if (progressBarFill) {
      progressBarFill.style.width = `${pct}%`;
    }
    if (progressPercent) {
      progressPercent.textContent = `${pct}% Elapsed`;
    }
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

  // Set audio status pill state
  function updateAudioStatus(text, dotColor) {
    if (audioStatusText) audioStatusText.textContent = text;
    if (audioStatusDot) audioStatusDot.style.backgroundColor = dotColor;
  }

  // Reset Start Button
  function resetStartButton(message = "▶️ Start Interview Call") {
    if (startBtn) {
      startBtn.disabled = !isElevenLabsConfigured;
      startBtn.style.display = "inline-flex";
      startBtn.textContent = message;
    }
    if (endBtn) {
      endBtn.style.display = "none";
    }
    if (connectionBadge) {
      connectionBadge.className = "badge badge-gray";
      connectionBadge.textContent = "Not Connected";
    }
    updateAudioStatus("Microphone & audio ready", "#94a3b8");
  }

  // Append a turn to transcript
  function appendTranscriptTurn(role, text) {
    if (!text || !text.trim()) return;

    if (emptyTranscriptMsg) {
      emptyTranscriptMsg.style.display = "none";
    }

    const cleanRole = (role === "agent" || role === "interviewer" || role === "ai") ? "interviewer" : "candidate";
    const turn = {
      role: cleanRole,
      message: text.trim(),
      time_in_call_secs: elapsedSeconds
    };
    transcriptTurns.push(turn);

    const msgEl = document.createElement("div");
    msgEl.className = `transcript-message ${cleanRole}`;

    const roleLabel = cleanRole === "interviewer" ? "Alex (AI Interviewer)" : (candidateName || "Candidate");
    msgEl.innerHTML = `
      <div class="message-role">${escapeHtml(roleLabel)} <span style="font-weight: normal; font-size: 0.7rem; color: var(--text-muted);">• ${formatTime(elapsedSeconds)}</span></div>
      <div>${escapeHtml(text.trim())}</div>
    `;

    if (transcriptBox) {
      transcriptBox.appendChild(msgEl);
      transcriptBox.scrollTop = transcriptBox.scrollHeight;
    }

    if (turnCounter) {
      turnCounter.textContent = `${transcriptTurns.length} exchange${transcriptTurns.length === 1 ? "" : "s"}`;
    }

    // Sync turns with server in background
    syncTranscriptToServer();
  }

  function escapeHtml(string) {
    const div = document.createElement("div");
    div.innerText = string;
    return div.innerHTML;
  }

  let syncTimeout = null;
  function syncTranscriptToServer() {
    clearTimeout(syncTimeout);
    syncTimeout = setTimeout(async () => {
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
    }, 400);
  }

  // Toggle Transcript panel
  if (transcriptToggleHeader && transcriptPanelBody) {
    transcriptToggleHeader.addEventListener("click", () => {
      const isVisible = transcriptPanelBody.style.display !== "none";
      transcriptPanelBody.style.display = isVisible ? "none" : "block";
      if (transcriptToggleBtn) {
        transcriptToggleBtn.textContent = isVisible ? "Expand ▼" : "Collapse ▲";
      }
    });
  }

  // Handle Start Interview Call
  if (startBtn) {
    startBtn.addEventListener("click", async () => {
      if (!isElevenLabsConfigured) {
        alert("ElevenLabs credentials are not configured. Please check your .env settings.");
        return;
      }

      startBtn.disabled = true;
      startBtn.textContent = "Requesting Microphone Access...";
      if (connectionBadge) {
        connectionBadge.className = "badge badge-amber";
        connectionBadge.textContent = "Mic Permission";
      }
      updateAudioStatus("Requesting microphone permission...", "#f59e0b");

      try {
        // Step 1: Explicitly request and verify microphone permission
        let micStream;
        try {
          micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
          // Stop probe track immediately; SDK will acquire its own stream
          micStream.getTracks().forEach((track) => track.stop());
        } catch (micErr) {
          console.error("Microphone permission denied or failed:", micErr);
          alert(
            "Microphone access is required for the spoken interview.\n\n" +
            "Please click the microphone/lock icon in your browser's address bar, allow microphone access, and try again."
          );
          resetStartButton();
          return;
        }

        // Step 2: Fetch secure conversation credentials from server
        startBtn.textContent = "Connecting to Voice Agent...";
        updateAudioStatus("Obtaining secure interview session token...", "#f59e0b");
        if (connectionBadge) {
          connectionBadge.textContent = "Securing Session";
        }

        const res = await fetch(`/api/interviews/${interviewId}/conversation-credentials`);
        const creds = await res.json();

        if (!res.ok) {
          throw new Error(creds.error || "Failed to obtain interview conversation credentials.");
        }

        // Step 3: Start conversation session via ElevenLabs Client SDK
        updateAudioStatus("Connecting audio stream...", "#f59e0b");
        if (connectionBadge) {
          connectionBadge.textContent = "Opening Audio Stream";
        }

        const sessionConfig = {
          dynamicVariables: creds.dynamic_variables || {
            interview_id: interviewId,
            candidate_name: candidateName,
            job_title: jobTitle
          },
          onConnect: ({ conversationId: id }) => {
            console.log("Connected to ElevenLabs session:", id);
            conversationId = id;
            isCallActive = true;

            if (connectionBadge) {
              connectionBadge.className = "badge badge-emerald";
              connectionBadge.textContent = "Live Voice Connected";
            }
            if (studioStateTitle) {
              studioStateTitle.textContent = "Interview in Progress";
            }
            if (studioStateSubtitle) {
              studioStateSubtitle.textContent =
                "Alex (AI Interviewer) is conducting your spoken interview. Speak clearly into your microphone.";
            }

            updateAudioStatus("Connected • Voice stream active", "#10b981");

            startBtn.style.display = "none";
            if (endBtn) {
              endBtn.style.display = "inline-flex";
            }

            startTimer();
          },
          onDisconnect: (details) => {
            console.log("ElevenLabs session disconnected:", details);
            isCallActive = false;
            if (!isFinalizing) {
              if (connectionBadge) {
                connectionBadge.className = "badge badge-gray";
                connectionBadge.textContent = "Call Ended";
              }
              if (voiceOrb) {
                voiceOrb.className = "pulsing-orb";
              }
              if (orbIcon) {
                orbIcon.textContent = "🎙️";
              }
              updateAudioStatus("Voice call disconnected", "#94a3b8");
            }
          },
          onModeChange: ({ mode }) => {
            console.log("ElevenLabs mode:", mode);
            if (mode === "speaking") {
              if (voiceOrb) voiceOrb.className = "pulsing-orb speaking";
              if (orbIcon) orbIcon.textContent = "🎙️";
              if (connectionBadge) {
                connectionBadge.className = "badge badge-indigo";
                connectionBadge.textContent = "Alex is Speaking";
              }
              updateAudioStatus("Alex is speaking...", "#6366f1");
            } else if (mode === "listening") {
              if (voiceOrb) voiceOrb.className = "pulsing-orb listening";
              if (orbIcon) orbIcon.textContent = "🗣️";
              if (connectionBadge) {
                connectionBadge.className = "badge badge-emerald";
                connectionBadge.textContent = "Listening to You";
              }
              updateAudioStatus("Listening • Speak into your microphone", "#10b981");
            }
          },
          onMessage: (messagePayload) => {
            console.log("ElevenLabs message received:", messagePayload);
            const rawRole = messagePayload.role || (messagePayload.source === "user" ? "user" : "agent");
            const text = messagePayload.message || "";
            appendTranscriptTurn(rawRole, text);
          },
          onError: (message, context) => {
            console.error("ElevenLabs error:", message, context);
            if (connectionBadge) {
              connectionBadge.className = "badge badge-rose";
              connectionBadge.textContent = "Audio Stream Warning";
            }
            updateAudioStatus("Audio Notice: " + (message || "Connection event"), "#ef4444");
          },
          onStatusChange: ({ status }) => {
            console.log("ElevenLabs status change:", status);
            if (status === "connecting") {
              if (connectionBadge) {
                connectionBadge.className = "badge badge-amber";
                connectionBadge.textContent = "Connecting to Voice...";
              }
            }
          }
        };

        if (creds.auth_mode === "signed_url") {
          sessionConfig.signedUrl = creds.signed_url;
        } else {
          sessionConfig.agentId = creds.agent_id || configuredAgentId;
        }

        conversationInstance = await Conversation.startSession(sessionConfig);

      } catch (err) {
        console.error("Call initialization failed:", err);
        alert("Could not start voice interview call: " + err.message);
        resetStartButton();
      }
    });
  }

  // Handle End Interview & Finalize
  if (endBtn) {
    endBtn.addEventListener("click", async () => {
      const candidateTurns = transcriptTurns.filter((t) => t.role === "candidate");
      if (candidateTurns.length === 0 && transcriptTurns.length < 2) {
        const proceed = confirm(
          "Notice: Alex and you haven't exchanged enough answers yet for a thorough evaluation.\n\n" +
          "Are you sure you want to conclude the session and generate the report now?"
        );
        if (!proceed) return;
      } else {
        const proceed = confirm(
          "Are you ready to conclude your interview session and generate the evaluation report?"
        );
        if (!proceed) return;
      }

      await finalizeAndRedirect("normal");
    });
  }

  async function finalizeAndRedirect(reason) {
    isFinalizing = true;
    stopTimer();

    if (endBtn) endBtn.disabled = true;
    if (finalizingModal) finalizingModal.classList.add("active");

    // Close conversation session gracefully
    if (conversationInstance) {
      try {
        await conversationInstance.endSession();
      } catch (endErr) {
        console.warn("Session end warning:", endErr);
      }
      conversationInstance = null;
    }

    try {
      // Step 1: Tell server call has concluded
      await fetch(`/api/interviews/${interviewId}/end`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason: reason,
          conversation_id: conversationId
        })
      });

      // Step 2: Trigger report evaluation
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
        throw new Error(finalData.error || "Evaluation synthesis failed.");
      }

      // Success: redirect to report
      window.location.href = finalData.report_url || `/reports/${interviewId}`;

    } catch (err) {
      console.error("Finalization error:", err);
      if (finalizingModal) finalizingModal.classList.remove("active");
      alert("Evaluation Notice: " + err.message);
      // Return to interview preparation or dashboard
      window.location.href = `/interviews/${interviewId}`;
    }
  }

  // Handle window unload gracefully
  window.addEventListener("beforeunload", () => {
    if (isCallActive) {
      navigator.sendBeacon(
        `/api/interviews/${interviewId}/end`,
        JSON.stringify({ reason: "interrupted" })
      );
      if (conversationInstance) {
        try {
          conversationInstance.endSession();
        } catch (_) {}
      }
    }
  });
});
