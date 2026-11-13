// OTP Share Web Client
let state = {
  otps: [],
  latestOtp: null,
  status: {
    status: "unconfigured",
    monitored_email: "",
    unread_count: 0,
    connected: false
  },
  searchQuery: "",
  soundEnabled: localStorage.getItem("otp_sound") !== "false",
  autoPopup: localStorage.getItem("otp_autopopup") !== "false",
  activePopupOtp: null,
  lastSeenOtpId: null,
  pin: localStorage.getItem("otp_pin") || "",
  appFilter: localStorage.getItem("otp_app_filter") || "indiabulls"
};

// ==========================================
// Front-and-Center OTP Popup
// ==========================================
function toggleAutoPopup() {
  state.autoPopup = !state.autoPopup;
  localStorage.setItem("otp_autopopup", state.autoPopup ? "true" : "false");
  updatePopupToggleBtn();
  showToast(state.autoPopup ? "⚡ Auto-popup enabled: new OTPs pop up on front" : "Popup disabled", "info");
}

function updatePopupToggleBtn() {
  const btn = document.getElementById("toggle-popup-btn");
  if (btn) {
    btn.innerHTML = state.autoPopup ? "⚡ Popup ON" : "💤 Popup OFF";
    btn.style.color = state.autoPopup ? "var(--accent)" : "var(--text-muted)";
  }
}

function showOtpPopup(item) {
  if (!item || !item.otp_code) return;
  state.activePopupOtp = item;

  const modal = document.getElementById("new-otp-modal");
  const serviceBadge = document.getElementById("popup-service-badge");
  const subjectEl = document.getElementById("popup-subject");
  const senderEl = document.getElementById("popup-sender");
  const otpEl = document.getElementById("popup-otp-code");
  const copyBtn = document.getElementById("popup-copy-btn");

  if (serviceBadge) serviceBadge.textContent = item.service_tag || "Indiabulls";
  if (subjectEl) subjectEl.textContent = item.subject || "New Verification Code";
  if (senderEl) {
    senderEl.textContent = `From: ${item.sender_name || item.sender_email || 'Service'} • ${formatTimeAgo(item.received_at || item.created_at)}`;
  }
  if (otpEl) {
    otpEl.textContent = item.otp_code.split("").join(" ");
  }
  if (copyBtn) {
    copyBtn.innerHTML = `📋 Copy OTP`;
    copyBtn.style.background = "";
  }

  if (modal) {
    modal.classList.add("active");
  }
}

async function copyPopupOtp() {
  if (!state.activePopupOtp || !state.activePopupOtp.otp_code) return;
  const code = state.activePopupOtp.otp_code;
  await copyToClipboard(code);
  const copyBtn = document.getElementById("popup-copy-btn");
  if (copyBtn) {
    const originalText = copyBtn.innerHTML;
    copyBtn.innerHTML = `✓ Copied (${code})!`;
    copyBtn.style.background = "var(--success)";
    setTimeout(() => {
      if (copyBtn) {
        copyBtn.innerHTML = originalText;
        copyBtn.style.background = "";
      }
    }, 2000);
  }
}

function openEmailFromPopup() {
  if (state.activePopupOtp && state.activePopupOtp.id) {
    const id = state.activePopupOtp.id;
    closeModal("new-otp-modal");
    openEmailModal(id);
  }
}

// ==========================================
// Web Audio Chime Generator
// ==========================================
function playChime() {
  if (!state.soundEnabled) return;
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const ctx = new AudioContext();

    // Two pleasant tones
    const now = ctx.currentTime;
    
    // Tone 1: 587.33 Hz (D5)
    const osc1 = ctx.createOscillator();
    const gain1 = ctx.createGain();
    osc1.type = "sine";
    osc1.frequency.setValueAtTime(587.33, now);
    gain1.gain.setValueAtTime(0, now);
    gain1.gain.linearRampToValueAtTime(0.2, now + 0.05);
    gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
    osc1.connect(gain1);
    gain1.connect(ctx.destination);
    osc1.start(now);
    osc1.stop(now + 0.35);

    // Tone 2: 880 Hz (A5)
    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.type = "sine";
    osc2.frequency.setValueAtTime(880.0, now + 0.12);
    gain2.gain.setValueAtTime(0, now + 0.12);
    gain2.gain.linearRampToValueAtTime(0.25, now + 0.17);
    gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.55);
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    osc2.start(now + 0.12);
    osc2.stop(now + 0.55);
  } catch (e) {
    console.warn("Audio playback not allowed or failed:", e);
  }
}

// ==========================================
// Toast Notifications
// ==========================================
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <div style="flex: 1; font-size: 0.875rem;">${message}</div>
    <button style="background: none; border: none; color: var(--text-muted); cursor: pointer;" onclick="this.parentElement.remove()">✕</button>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    if (toast.parentElement) toast.remove();
  }, 4000);
}

// ==========================================
// API Helpers
// ==========================================
function getHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (state.pin) {
    headers["X-OTP-PIN"] = state.pin;
  }
  return headers;
}

async function apiFetch(endpoint, options = {}) {
  const opts = {
    ...options,
    headers: { ...getHeaders(), ...(options.headers || {}) }
  };
  const res = await fetch(endpoint, opts);
  if (res.status === 401) {
    document.getElementById("pin-modal").style.display = "flex";
    throw new Error("PIN required");
  }
  return res;
}

// ==========================================
// Time Ago & Date Formatters
// ==========================================
function formatTimeAgo(dateString) {
  if (!dateString) return "just now";
  let normalized = dateString.replace(" ", "T");
  // If naive timestamp without timezone offset, treat as UTC from server
  if (!normalized.includes("Z") && !normalized.includes("+") && !normalized.includes("-", 10)) {
    normalized += "Z";
  }
  const date = new Date(normalized);
  const now = new Date();
  const diffSec = Math.floor((now - date) / 1000);

  if (diffSec < 0 || diffSec <= 10) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  const diffDays = Math.floor(diffHour / 24);
  return `${diffDays}d ago`;
}

function formatLocalDateTime(dateString) {
  if (!dateString) return "";
  try {
    let normalized = dateString.replace(" ", "T");
    if (!normalized.includes("Z") && !normalized.includes("+") && !normalized.includes("-", 10)) {
      normalized += "Z";
    }
    const d = new Date(normalized);
    if (isNaN(d.getTime())) return dateString;
    return d.toLocaleString([], {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: true
    });
  } catch (e) {
    return dateString;
  }
}

// ==========================================
// Copy to Clipboard
// ==========================================
async function copyToClipboard(text, elementId = null) {
  try {
    await navigator.clipboard.writeText(text);
    showToast(`Copied <strong>${text}</strong> to clipboard!`, "success");

    if (elementId) {
      const el = document.getElementById(elementId);
      if (el) {
        const orig = el.innerHTML;
        el.innerHTML = "✓ Copied!";
        el.style.borderColor = "var(--success)";
        setTimeout(() => {
          el.innerHTML = orig;
          el.style.borderColor = "";
        }, 1500);
      }
    }
  } catch (err) {
    // Fallback
    const textarea = document.createElement("textarea");
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
    showToast(`Copied <strong>${text}</strong>!`, "success");
  }
}

// ==========================================
// Rendering
// ==========================================
function renderStatus() {
  const statusPill = document.getElementById("status-pill");
  const statusDot = document.getElementById("status-dot");
  const statusText = document.getElementById("status-text");
  const monitoredEmail = document.getElementById("monitored-email");
  const unconfiguredBanner = document.getElementById("unconfigured-banner");

  if (!statusPill) return;

  statusDot.className = "status-dot";
  if (state.status.status === "connected") {
    statusDot.classList.add("connected");
    statusText.textContent = "Listening Live";
  } else if (state.status.status === "polling") {
    statusDot.classList.add("polling");
    statusText.textContent = "Checking Mail...";
  } else if (state.status.status === "error") {
    statusDot.classList.add("error");
    statusText.textContent = "Connection Error";
  } else {
    statusText.textContent = "Not Configured";
  }

  if (monitoredEmail) {
    monitoredEmail.textContent = state.status.monitored_email
      ? `• ${state.status.monitored_email}`
      : "";
  }

  if (unconfiguredBanner) {
    unconfiguredBanner.style.display =
      state.status.status === "unconfigured" ? "block" : "none";
  }
}

function renderHero() {
  const heroCard = document.getElementById("hero-card");
  if (!heroCard) return;

  const item = state.latestOtp;
  if (!item || !item.otp_code) {
    heroCard.innerHTML = `
      <div class="hero-empty">
        <div class="hero-empty-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect width="20" height="16" x="2" y="4" rx="2"/>
            <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
          </svg>
        </div>
        <h3 style="margin-bottom: 6px; font-size: 1.1rem;">Waiting for incoming OTP emails...</h3>
        <p style="font-size: 0.85rem; color: var(--text-muted); max-width: 450px; margin: 0 auto 16px auto;">
          When an OTP or verification code arrives in your mailbox, it will appear here in real-time.
        </p>
        <button class="btn btn-secondary btn-sm" onclick="sendTestOtp()">
          ⚡ Send Simulated Test OTP
        </button>
      </div>
    `;
    return;
  }

  const codeFormatted = item.otp_code.split("").join(" ");

  heroCard.innerHTML = `
    <div class="hero-header">
      <div class="hero-label">
        <span style="display:inline-block; width:6px; height:6px; border-radius:50%; background:var(--accent);"></span>
        LATEST VERIFICATION CODE
      </div>
      <div class="hero-time" id="hero-time-ago">${formatTimeAgo(item.received_at || item.created_at)}</div>
    </div>
    <div class="hero-body">
      <div class="hero-info">
        <div class="service-badge">
          ${escapeHtml(item.service_tag || "Service")}
        </div>
        <div class="hero-subject">${escapeHtml(item.subject || "(No Subject)")}</div>
        <div style="font-size: 0.825rem; color: var(--text-muted);">
          From: ${escapeHtml(item.sender_name || item.sender_email)}
        </div>
      </div>
      <div class="hero-otp-container">
        <div class="hero-otp-display" id="hero-otp-code" title="Click to copy" onclick="copyToClipboard('${item.otp_code}', 'hero-copy-btn')">
          ${codeFormatted}
        </div>
        <button class="btn btn-primary btn-copy-lg" id="hero-copy-btn" onclick="copyToClipboard('${item.otp_code}', 'hero-copy-btn')">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
            <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
          </svg>
          Copy Code
        </button>
      </div>
    </div>
    <div style="margin-top: 18px; padding-top: 14px; border-top: 1px solid rgba(255,255,255,0.06); display: flex; justify-content: space-between; align-items: center;">
      <span style="font-size: 0.8rem; color: var(--text-muted);">
        ${item.verification_link ? `<a href="${escapeHtml(item.verification_link)}" target="_blank" style="color:var(--accent); text-decoration:none;">🔗 Open Verification Link</a>` : "Email verified & parsed"}
      </span>
      <button class="btn btn-ghost btn-sm" onclick="openEmailModal(${item.id})">
        View Full Email ➔
      </button>
    </div>
  `;
}

function renderOtpList() {
  const container = document.getElementById("otp-feed");
  const countEl = document.getElementById("otp-count");
  if (!container) return;

  let filtered = state.otps;

  // Search filter
  if (state.searchQuery) {
    const q = state.searchQuery.toLowerCase();
    filtered = filtered.filter(item =>
      (item.subject && item.subject.toLowerCase().includes(q)) ||
      (item.sender_name && item.sender_name.toLowerCase().includes(q)) ||
      (item.sender_email && item.sender_email.toLowerCase().includes(q)) ||
      (item.service_tag && item.service_tag.toLowerCase().includes(q)) ||
      (item.otp_code && item.otp_code.includes(q))
    );
  }

  if (countEl) {
    countEl.textContent = `${filtered.length} messages`;
  }

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 40px; color: var(--text-muted); background: var(--bg-card); border-radius: var(--radius-md); border: 1px dashed var(--border-color);">
        ${state.searchQuery ? "No OTPs found matching your search." : "No OTP emails received yet."}
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(item => {
    const initial = (item.service_tag || "O").charAt(0).toUpperCase();
    const timeAgo = formatTimeAgo(item.received_at || item.created_at);

    return `
      <div class="otp-card" id="otp-row-${item.id}">
        <div class="otp-card-left">
          <div class="service-icon-box">
            ${initial}
          </div>
          <div class="otp-meta">
            <div class="otp-meta-top">
              <span class="otp-sender">${escapeHtml(item.service_tag || item.sender_name)}</span>
              <span class="badge-tag">${escapeHtml(item.sender_name || item.sender_email)}</span>
              <span class="otp-time">${timeAgo}</span>
            </div>
            <div class="otp-subject" title="${escapeHtml(item.subject)}">
              ${escapeHtml(item.subject || "(No Subject)")}
            </div>
          </div>
        </div>

        <div class="otp-card-right">
          ${item.otp_code ? `
            <div class="otp-code-pill" onclick="copyToClipboard('${item.otp_code}', 'pill-${item.id}')" id="pill-${item.id}" title="Click to copy OTP">
              <span>${escapeHtml(item.otp_code)}</span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
                <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
              </svg>
            </div>
          ` : `
            <span style="font-size: 0.8rem; color: var(--text-muted);">Link / Code</span>
          `}
          <button class="btn btn-secondary btn-sm" onclick="openEmailModal(${item.id})">
            Details
          </button>
          <button class="btn btn-ghost btn-sm" style="color: var(--danger);" onclick="deleteOtp(${item.id})" title="Delete">
            ✕
          </button>
        </div>
      </div>
    `;
  }).join("");
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// ==========================================
// Data Fetching & Sync
// ==========================================
function setAppFilter(service) {
  state.appFilter = service;
  localStorage.setItem("otp_app_filter", service);
  document.querySelectorAll(".filter-chip").forEach(el => {
    const s = el.getAttribute("onclick") || "";
    el.classList.toggle("active", s.includes(`'${service}'`));
  });
  loadOtps();
}

// Deleted IDs Helper for persistent deletion
function getDeletedIds() {
  try {
    return new Set(JSON.parse(localStorage.getItem("otp_deleted_ids") || "[]"));
  } catch (e) {
    return new Set();
  }
}

function addDeletedId(id) {
  try {
    const set = getDeletedIds();
    set.add(String(id));
    localStorage.setItem("otp_deleted_ids", JSON.stringify([...set]));
  } catch (e) {}
}

async function loadOtps() {
  try {
    const filterParam = (state.appFilter && state.appFilter !== "all") ? `?service=${encodeURIComponent(state.appFilter)}` : "";
    const res = await apiFetch(`/api/otps${filterParam}`);
    const data = await res.json();
    const rawOtps = data.otps || [];
    const deletedSet = getDeletedIds();
    state.otps = rawOtps.filter(x => !deletedSet.has(String(x.id)) && !deletedSet.has(Number(x.id)));
    const newLatest = data.latest && !deletedSet.has(String(data.latest.id)) ? data.latest : (state.otps.find(x => x.otp_code) || state.otps[0] || null);

    // ONLY pop up if a strictly NEWER OTP arrives (higher ID), never when deleting or loading past OTPs
    if (state.lastSeenOtpId !== null && newLatest && newLatest.id > state.lastSeenOtpId) {
      if (state.autoPopup && newLatest.otp_code) {
        showOtpPopup(newLatest);
        playChime();
      }
    }
    if (newLatest) {
      state.lastSeenOtpId = newLatest.id;
    }

    state.latestOtp = newLatest;
    renderHero();
    renderOtpList();
  } catch (err) {
    console.error("Failed to load OTPs:", err);
  }
}

async function loadStatus() {
  try {
    const res = await apiFetch("/api/status");
    const data = await res.json();
    state.status = data;
    renderStatus();
  } catch (err) {
    console.error("Failed to load status:", err);
  }
}

function initSSE() {
  const eventSource = new EventSource("/api/stream");

  eventSource.addEventListener("new_otp", (e) => {
    try {
      const newOtp = JSON.parse(e.data);
      // If service filter is active, check if match
      if (state.appFilter && state.appFilter !== "all") {
        const combined = `${newOtp.service_tag} ${newOtp.sender_name} ${newOtp.sender_email} ${newOtp.subject}`.toLowerCase();
        if (!combined.includes(state.appFilter.toLowerCase())) {
          return; // Ignore other services when filtered!
        }
      }
      // Prepend if not exists
      if (!state.otps.some(x => x.id === newOtp.id)) {
        state.otps.unshift(newOtp);
      }
      // Re-sort descending by received_at
      state.otps.sort((a, b) => {
        const da = new Date((a.received_at || a.created_at).replace(" ", "T"));
        const db = new Date((b.received_at || b.created_at).replace(" ", "T"));
        return db - da;
      });
      // Pick newest OTP with an actual code
      state.latestOtp = state.otps.find(x => x.otp_code) || state.otps[0];
      state.lastSeenOtpId = state.latestOtp ? state.latestOtp.id : null;
      renderHero();
      renderOtpList();
      playChime();
      showToast(`⚡ New OTP from <strong>${escapeHtml(newOtp.service_tag)}</strong>: <strong>${newOtp.otp_code || 'Received'}</strong>`, "success");

      // Prominent front popup modal!
      if (state.autoPopup && newOtp.otp_code) {
        showOtpPopup(newOtp);
      }
    } catch (err) {
      console.error("SSE new_otp error:", err);
    }
  });

  eventSource.addEventListener("status", (e) => {
    try {
      const statusData = JSON.parse(e.data);
      state.status = statusData;
      renderStatus();
    } catch (err) {
      console.error("SSE status error:", err);
    }
  });

  eventSource.addEventListener("deleted_otp", (e) => {
    try {
      const data = JSON.parse(e.data);
      state.otps = state.otps.filter(x => x.id !== data.id);
      if (state.latestOtp && state.latestOtp.id === data.id) {
        state.latestOtp = state.otps.length > 0 ? state.otps[0] : null;
      }
      renderHero();
      renderOtpList();
    } catch (err) {}
  });

  eventSource.addEventListener("cleared_all", () => {
    state.otps = [];
    state.latestOtp = null;
    renderHero();
    renderOtpList();
  });

  eventSource.onerror = () => {
    // Reconnection is automatic by browser EventSource
  };
}

// ==========================================
// Actions
// ==========================================
async function triggerCheckNow() {
  const btn = document.getElementById("check-now-btn");
  if (btn) {
    btn.innerHTML = `<span style="display:inline-block; animation: spin 1s infinite linear;">↻</span> Checking...`;
    btn.disabled = true;
  }
  try {
    const res = await apiFetch("/api/check-now", { method: "POST" });
    const data = await res.json();
    await loadOtps();
    await loadStatus();
    if (data.new_count > 0) {
      showToast(`⚡ Captured ${data.new_count} new code(s)!`, "success");
    } else {
      showToast("Mailbox checked — up to date!", "info");
    }
  } catch (err) {
    showToast("Failed to trigger check", "error");
  } finally {
    setTimeout(() => {
      if (btn) {
        btn.innerHTML = `↻ Check Now`;
        btn.disabled = false;
      }
    }, 400);
  }
}

async function sendTestOtp(service = null) {
  const svc = service || (state.appFilter && state.appFilter !== "all" ? (state.appFilter.charAt(0).toUpperCase() + state.appFilter.slice(1)) : "Indiabulls");
  try {
    const res = await apiFetch("/api/test-otp", {
      method: "POST",
      body: JSON.stringify({ service: svc })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`⚡ Test OTP generated for ${svc}!`, "success");
    }
  } catch (err) {
    showToast("Failed to send test OTP", "error");
  }
}

async function deleteOtp(id) {
  if (!confirm("Are you sure you want to delete this OTP?")) return;
  
  // Track deleted in localStorage
  addDeletedId(id);

  // Remove from local state immediately
  state.otps = state.otps.filter(x => x.id !== id && String(x.id) !== String(id));
  state.latestOtp = state.otps.length > 0 ? (state.otps.find(x => x.otp_code) || state.otps[0]) : null;
  if (state.latestOtp) {
    state.lastSeenOtpId = state.latestOtp.id;
  }

  renderHero();
  renderOtpList();
  showToast("OTP deleted", "info");

  try {
    await apiFetch(`/api/otps/${id}`, { method: "DELETE" });
  } catch (err) {}
}

async function clearAllOtps() {
  if (!confirm("Are you sure you want to clear ALL OTP messages?")) return;
  try {
    state.otps.forEach(x => addDeletedId(x.id));
    state.otps = [];
    state.latestOtp = null;
    renderHero();
    renderOtpList();
    showToast("All OTP messages cleared", "info");
    await apiFetch("/api/otps/clear", { method: "POST" });
  } catch (err) {
    showToast("Failed to clear OTPs", "error");
  }
}

// ==========================================
// Email Reader Modal
// ==========================================
async function openEmailModal(id) {
  const modal = document.getElementById("email-modal");
  const modalContent = document.getElementById("email-modal-body");
  if (!modal || !modalContent) return;

  // First check if email is already in state.otps for instant render
  let email = state.otps.find(x => x.id === id || String(x.id) === String(id));

  if (!email) {
    modalContent.innerHTML = `<div style="text-align: center; padding: 30px;">Loading message details...</div>`;
    modal.classList.add("active");
    try {
      const res = await apiFetch(`/api/otps/${id}`);
      email = await res.json();
    } catch (err) {
      modalContent.innerHTML = `<div style="color:var(--danger); padding:20px;">Failed to load email details.</div>`;
      return;
    }
  }

  modal.classList.add("active");
  try {

    modalContent.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">
        <div>
          <span class="service-badge" style="margin-bottom:8px;">${escapeHtml(email.service_tag)}</span>
          <h2 style="font-size:1.25rem; font-weight:700; margin-bottom:4px;">${escapeHtml(email.subject)}</h2>
          <div style="font-size:0.85rem; color:var(--text-muted);">
            From: <strong>${escapeHtml(email.sender_name)}</strong> &lt;${escapeHtml(email.sender_email)}&gt;
          </div>
          <div style="font-size:0.8rem; color:var(--text-muted); margin-top:2px;">
            Received: ${escapeHtml(formatLocalDateTime(email.received_at || email.created_at))}
          </div>
        </div>
        ${email.otp_code ? `
          <div style="text-align:right;">
            <div style="font-size:0.75rem; color:var(--text-muted); margin-bottom:4px;">DETECTED OTP</div>
            <div class="otp-code-pill" onclick="copyToClipboard('${email.otp_code}')" title="Click to copy">
              ${escapeHtml(email.otp_code)}
            </div>
          </div>
        ` : ''}
      </div>

      ${email.verification_link ? `
        <div style="background:rgba(56,189,248,0.1); border:1px solid rgba(56,189,248,0.3); border-radius:var(--radius-md); padding:12px 16px; display:flex; align-items:center; justify-content:space-between; gap:10px;">
          <div style="font-size:0.85rem;">
            <strong>Verification Link:</strong> ${escapeHtml(email.verification_link.substring(0, 60))}...
          </div>
          <a href="${escapeHtml(email.verification_link)}" target="_blank" class="btn btn-primary btn-sm" style="text-decoration:none;">
            Open Link ➔
          </a>
        </div>
      ` : ''}

      <div style="border-top:1px solid var(--border-color); padding-top:14px; margin-top:10px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
          <span style="font-size:0.8rem; font-weight:600; color:var(--text-muted); text-transform:uppercase;">Email Body</span>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-ghost btn-sm" onclick="toggleEmailView('rendered')">Formatted</button>
            <button class="btn btn-ghost btn-sm" onclick="toggleEmailView('text')">Plain Text</button>
          </div>
        </div>

        <div id="email-view-rendered" style="background:#ffffff; color:#1e293b; border-radius:var(--radius-md); padding:18px; max-height:400px; overflow-y:auto; font-size:0.9rem;">
          ${email.body_html ? email.body_html : `<pre style="white-space: pre-wrap; font-family: inherit;">${escapeHtml(email.body_text)}</pre>`}
        </div>

        <div id="email-view-text" style="display:none; background:var(--bg-primary); color:var(--text-secondary); border-radius:var(--radius-md); padding:16px; max-height:400px; overflow-y:auto; font-family:var(--font-mono); font-size:0.8rem; white-space:pre-wrap;">
${escapeHtml(email.body_text)}
        </div>
      </div>
    `;
  } catch (err) {
    modalContent.innerHTML = `<div style="color:var(--danger); padding:20px;">Failed to load email details.</div>`;
  }
}

function toggleEmailView(type) {
  const rendered = document.getElementById("email-view-rendered");
  const text = document.getElementById("email-view-text");
  if (type === "rendered") {
    rendered.style.display = "block";
    text.style.display = "none";
  } else {
    rendered.style.display = "none";
    text.style.display = "block";
  }
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove("active");
}

// ==========================================
// Settings Modal & Tabs
// ==========================================
function switchSettingsTab(tabName) {
  const tabs = ["connect", "advanced", "help"];
  tabs.forEach(t => {
    const btn = document.getElementById(`tab-btn-${t}`);
    const content = document.getElementById(`tab-content-${t}`);
    if (btn) btn.classList.toggle("active", t === tabName);
    if (content) content.style.display = (t === tabName) ? "flex" : "none";
  });
}

async function openSettingsModal() {
  const modal = document.getElementById("settings-modal");
  if (!modal) return;
  modal.classList.add("active");
  switchSettingsTab("connect");

  try {
    const res = await apiFetch("/api/config");
    const cfg = await res.json();
    document.getElementById("cfg-email").value = cfg.EMAIL_USER || "";
    document.getElementById("cfg-host").value = cfg.IMAP_HOST || "imap.gmail.com";
    document.getElementById("cfg-port").value = cfg.IMAP_PORT || 993;
    document.getElementById("cfg-folder").value = cfg.IMAP_FOLDER || "INBOX";
    document.getElementById("cfg-keywords").value = cfg.FILTER_KEYWORDS || "";
    document.getElementById("cfg-interval").value = cfg.POLL_INTERVAL || 5;
    document.getElementById("cfg-markread").checked = cfg.MARK_AS_READ || false;
    const sfEl = document.getElementById("cfg-sender-filter");
    if (sfEl) sfEl.value = cfg.SENDER_FILTER || "";
    document.getElementById("cfg-pass").value = "";
    document.getElementById("cfg-pass").placeholder = cfg.EMAIL_PASS_SET ? "•••••••••••• (Configured)" : "16-character App Password";
    document.getElementById("test-conn-result").innerHTML = "";
  } catch (err) {
    showToast("Failed to load settings", "error");
  }
}

function applyProviderPreset(provider) {
  const hostInput = document.getElementById("cfg-host");
  const portInput = document.getElementById("cfg-port");
  if (provider === "gmail") {
    hostInput.value = "imap.gmail.com";
    portInput.value = 993;
  } else if (provider === "outlook") {
    hostInput.value = "outlook.office365.com";
    portInput.value = 993;
  } else if (provider === "yahoo") {
    hostInput.value = "imap.mail.yahoo.com";
    portInput.value = 993;
  } else if (provider === "icloud") {
    hostInput.value = "imap.mail.me.com";
    portInput.value = 993;
  }
}

async function testConnection() {
  const user = document.getElementById("cfg-email").value.trim();
  const passInput = document.getElementById("cfg-pass");
  const pass = passInput.value.trim();
  const isPassConfigured = passInput.placeholder && passInput.placeholder.includes("Configured");
  let host = document.getElementById("cfg-host").value.trim() || "imap.gmail.com";
  let port = parseInt(document.getElementById("cfg-port").value.trim()) || 993;
  const resultBox = document.getElementById("test-conn-result");
  const testBtn = document.getElementById("btn-test-conn");

  // Auto-detect provider if user left host as default
  const userLower = user.toLowerCase();
  if (host === "imap.gmail.com") {
    if (userLower.includes("@outlook.") || userLower.includes("@hotmail.") || userLower.includes("@live.")) {
      applyProviderPreset("outlook");
      host = "outlook.office365.com";
    } else if (userLower.includes("@yahoo.")) {
      applyProviderPreset("yahoo");
      host = "imap.mail.yahoo.com";
    }
  }

  if (!user) {
    resultBox.innerHTML = `
      <div style="background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 8px; padding: 10px 14px; color: var(--warning); font-size: 0.85rem;">
        ⚠️ Please enter your email address to test.
      </div>
    `;
    return;
  }

  if (!pass && !isPassConfigured) {
    resultBox.innerHTML = `
      <div style="background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 8px; padding: 10px 14px; color: var(--warning); font-size: 0.85rem;">
        ⚠️ Please enter your 16-character App Password to test.
      </div>
    `;
    return;
  }

  if (testBtn) {
    testBtn.disabled = true;
    testBtn.innerHTML = `<span style="display:inline-block; animation: spin 1s infinite linear;">↻</span> Testing...`;
  }

  resultBox.innerHTML = `
    <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 8px; padding: 10px 14px; color: var(--accent); font-size: 0.85rem;">
      ⏳ Connecting to <strong>${host}:${port}</strong> as <strong>${escapeHtml(user)}</strong>...
    </div>
  `;

  try {
    const res = await apiFetch("/api/test-connection", {
      method: "POST",
      body: JSON.stringify({
        EMAIL_USER: user,
        EMAIL_PASS: pass,
        IMAP_HOST: host,
        IMAP_PORT: port
      })
    });

    let data;
    try {
      data = await res.json();
    } catch (e) {
      data = { success: false, message: `Server error HTTP ${res.status}` };
    }

    if (data.success) {
      resultBox.innerHTML = `
        <div style="background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 8px; padding: 12px 14px; color: #34d399; font-size: 0.85rem; line-height: 1.5;">
          <div style="font-weight: 700; margin-bottom: 4px;">✓ ${escapeHtml(data.message)}</div>
          ${data.folders && data.folders.length > 0 ? `<div style="font-size: 0.8rem; opacity: 0.85;">Accessible folders: ${data.folders.map(f => `<code>${escapeHtml(f)}</code>`).join(', ')}</div>` : ''}
        </div>
      `;
      showToast("IMAP Connection successful!", "success");
    } else {
      const msg = data.message || (data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : "Connection failed.");
      resultBox.innerHTML = `
        <div style="background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 8px; padding: 12px 14px; color: #f87171; font-size: 0.85rem; line-height: 1.5;">
          <div style="font-weight: 700; margin-bottom: 4px;">✕ Connection Failed</div>
          <div>${escapeHtml(msg)}</div>
        </div>
      `;
    }
  } catch (err) {
    resultBox.innerHTML = `
      <div style="background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 8px; padding: 12px 14px; color: #f87171; font-size: 0.85rem;">
        ✕ Network request failed: ${escapeHtml(err.message)}
      </div>
    `;
  } finally {
    if (testBtn) {
      testBtn.disabled = false;
      testBtn.innerHTML = `🔌 Test IMAP Connection`;
    }
  }
}

async function saveSettings(e) {
  if (e) e.preventDefault();
  const updates = {
    EMAIL_USER: document.getElementById("cfg-email").value.trim(),
    IMAP_HOST: document.getElementById("cfg-host").value.trim(),
    IMAP_PORT: parseInt(document.getElementById("cfg-port").value.trim()) || 993,
    IMAP_FOLDER: document.getElementById("cfg-folder").value.trim() || "INBOX",
    FILTER_KEYWORDS: document.getElementById("cfg-keywords").value.trim(),
    POLL_INTERVAL: parseInt(document.getElementById("cfg-interval").value.trim()) || 5,
    MARK_AS_READ: document.getElementById("cfg-markread").checked,
    SENDER_FILTER: document.getElementById("cfg-sender-filter") ? document.getElementById("cfg-sender-filter").value.trim() : ""
  };

  const pass = document.getElementById("cfg-pass").value.trim();
  if (pass) {
    updates.EMAIL_PASS = pass;
  }

  const pin = document.getElementById("cfg-pin").value.trim();
  if (pin !== undefined) {
    updates.WEB_PIN = pin;
  }

  try {
    const res = await apiFetch("/api/config", {
      method: "POST",
      body: JSON.stringify(updates)
    });
    const data = await res.json();
    if (data.success) {
      showToast("Settings saved successfully!", "success");
      closeModal("settings-modal");
      loadStatus();
      triggerCheckNow();
    }
  } catch (err) {
    showToast("Failed to save settings", "error");
  }
}

// ==========================================
// PIN Lock Modal
// ==========================================
function submitPin() {
  const pinInput = document.getElementById("pin-input");
  if (!pinInput) return;
  state.pin = pinInput.value.trim();
  localStorage.setItem("otp_pin", state.pin);
  document.getElementById("pin-modal").style.display = "none";
  loadOtps();
  loadStatus();
}

// ==========================================
// Initialization
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
  // Sound button
  const soundBtn = document.getElementById("toggle-sound-btn");
  if (soundBtn) {
    soundBtn.innerHTML = state.soundEnabled ? "🔔 Sound ON" : "🔕 Sound OFF";
    soundBtn.addEventListener("click", () => {
      state.soundEnabled = !state.soundEnabled;
      localStorage.setItem("otp_sound", state.soundEnabled ? "true" : "false");
      soundBtn.innerHTML = state.soundEnabled ? "🔔 Sound ON" : "🔕 Sound OFF";
      showToast(state.soundEnabled ? "Sound notifications enabled" : "Sound muted", "info");
      if (state.soundEnabled) playChime();
    });
  }

  // Search input
  const searchInput = document.getElementById("search-input");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      state.searchQuery = e.target.value;
      renderOtpList();
    });
  }

  // Settings form
  const settingsForm = document.getElementById("settings-form");
  if (settingsForm) {
    settingsForm.addEventListener("submit", saveSettings);
  }

  // Popup toggle button
  updatePopupToggleBtn();

  // Modal backdrop click to close
  const newOtpModal = document.getElementById("new-otp-modal");
  if (newOtpModal) {
    newOtpModal.addEventListener("click", (e) => {
      if (e.target === newOtpModal) {
        closeModal("new-otp-modal");
      }
    });
  }

  // Keyboard Escape key dismisses modals
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeModal("new-otp-modal");
      closeModal("email-modal");
      closeModal("settings-modal");
    }
  });

  // Initial loads
  loadStatus();
  document.querySelectorAll(".filter-chip").forEach(el => {
    const s = el.getAttribute("onclick") || "";
    el.classList.toggle("active", s.includes(`'${state.appFilter}'`));
  });
  loadOtps();
  initSSE();

  // Real-time auto-sync: safe non-overlapping poll
  let isPolling = false;
  async function pollLoop() {
    if (!isPolling && !document.hidden) {
      isPolling = true;
      try {
        await loadOtps();
      } catch (err) {
      } finally {
        isPolling = false;
      }
    }
    setTimeout(pollLoop, 2500);
  }
  pollLoop();

  // Instant refresh when user switches back to tab or unlocks device
  window.addEventListener("focus", () => {
    loadOtps();
    loadStatus();
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      loadOtps();
      loadStatus();
    }
  });

  // Tick relative times every 5 seconds
  setInterval(() => {
    const heroTime = document.getElementById("hero-time-ago");
    if (heroTime && state.latestOtp) {
      heroTime.textContent = formatTimeAgo(state.latestOtp.received_at || state.latestOtp.created_at);
    }
    // Update timestamps in cards
    state.otps.forEach(item => {
      const row = document.getElementById(`otp-row-${item.id}`);
      if (row) {
        const timeEl = row.querySelector(".otp-time");
        if (timeEl) timeEl.textContent = formatTimeAgo(item.received_at || item.created_at);
      }
    });
  }, 5000);
});
