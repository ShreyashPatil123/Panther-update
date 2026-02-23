/**
 * PANTHER AI Agent — Frontend Application
 * WebSocket-driven, streaming, dark-mode SPA
 */

/* ── Marked.js config ──────────────────────────────────── */
marked.setOptions({
  breaks: true,
  gfm: true,
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  },
});

/* ── State ─────────────────────────────────────────────── */
const state = {
  ws: null,
  sessionId: crypto.randomUUID(),
  sessions: [],
  pendingFiles: [], // [{name, path}]
  isStreaming: false,
  currentAiBubble: null, // DOM element for streaming
  currentAiText: "", // accumulated markdown text
  categories: [],
  activeCategory: "chat",
  lastUserMsg: "",
  userScrolledUp: false,
};

/* ── DOM refs ───────────────────────────────────────────── */
const $ = (id) => document.getElementById(id);
const el = {
  hero: $("hero"),
  chatArea: $("chatArea"),
  messages: $("messages"),
  messageInput: $("messageInput"),
  sendBtn: $("sendBtn"),
  sendIcon: $("sendIcon"),
  stopIcon: $("stopIcon"),
  attachBtn: $("attachBtn"),
  fileInput: $("fileInput"),
  attachStrip: $("attachmentStrip"),
  attachPills: $("attachmentPills"),
  historyList: $("historyList"),
  historyEmpty: $("historyEmpty"),
  newChatBtn: $("newChatBtn"),
  settingsBtn: $("settingsBtn"),
  settingsOverlay: $("settingsOverlay"),
  settingsClose: $("settingsClose"),
  saveSettingsBtn: $("saveSettingsBtn"),
  statusDot: $("statusDot"),
  statusText: $("statusText"),
  modelBadge: $("modelBadge"),
  categoryBtn: $("categoryBtn"),
  categoryPopup: $("categoryPopup"),
  settingsStatus: $("settingsStatus"),
  nvdiaKey: $("nvdiaKey"),
  googleKey: $("googleKey"),
  defaultModel: $("defaultModel"),
  ollamaToggle: $("ollamaToggle"),
  ollamaUrl: $("ollamaUrl"),
  ollamaModel: $("ollamaModel"),
  ollamaApiKey: $("ollamaApiKey"),
  ollamaLimit: $("ollamaLimit"),
  geminiLiveBtn: $("geminiLiveBtn"),
  usageBarFill: $("usageBarFill"),
  usageStats: $("usageStats"),
  usageWarning: $("usageWarning"),
  resetUsageBtn: $("resetUsageBtn"),
  deleteConfirmOverlay: $("deleteConfirmOverlay"),
  deleteConfirmClose: $("deleteConfirmClose"),
  deleteConfirmCancel: $("deleteConfirmCancel"),
  deleteConfirmBtn: $("deleteConfirmBtn"),
};

/* ══════════════════════════════════════════════════════════
   WebSocket
══════════════════════════════════════════════════════════ */
function connectWS() {
  setStatus("Connecting…", "");
  const wsUrl = `ws://${location.host}/ws/chat/${state.sessionId}`;
  state.ws = new WebSocket(wsUrl);

  state.ws.onopen = () => {
    setStatus("Connected", "ready");
    // Share WebSocket with the Models picker so model switching works mid-session
    if (window.PantherModels) window.PantherModels.setWs(state.ws);
  };

  state.ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    handleServerMessage(msg);
  };

  state.ws.onclose = () => {
    setStatus("Disconnected — reconnecting…", "error");
    setTimeout(connectWS, 2500);
  };

  state.ws.onerror = () => {
    setStatus("Connection error", "error");
  };
}

function wsSend(payload) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(payload));
  }
}

/* ══════════════════════════════════════════════════════════
   Server message handler
══════════════════════════════════════════════════════════ */
function handleServerMessage(msg) {
  switch (msg.type) {
    case "session":
      state.sessionId = msg.session_id;
      state.sessions = msg.sessions || [];
      renderHistory();
      if (msg.history && msg.history.length > 0) {
        restoreHistory(msg.history);
      }
      break;

    case "chunk":
      if (!state.currentAiBubble) {
        removeTypingIndicator();
        state.currentAiBubble = appendMessage("", false);
        state.currentAiText = "";
      }
      state.currentAiText += msg.text;
      // Render markdown progressively
      state.currentAiBubble.querySelector(".msg-bubble").innerHTML =
        marked.parse(state.currentAiText);
      highlightCode(state.currentAiBubble);
      scrollToBottom();
      break;

    case "done":
      state.isStreaming = false;
      state.currentAiBubble = null;
      state.currentAiText = "";
      removeTypingIndicator();
      setStatus("Ready", "ready");
      el.sendBtn.disabled = false;
      el.sendBtn.classList.remove("is-stop");
      el.sendIcon.style.display = "";
      el.stopIcon.style.display = "none";
      el.sendBtn.title = "Send";
      // Count toward Ollama daily usage if Ollama is active
      incrementUsageIfOllama();
      // Refresh sessions list (title may have been auto-set)
      if (msg.sessions) {
        state.sessions = msg.sessions;
        renderHistory();
      }
      if (msg.session_id) {
        state.sessionId = msg.session_id;
        highlightActiveSession();
      }
      break;

    case "error":
      state.isStreaming = false;
      state.currentAiBubble = null;
      removeTypingIndicator();
      appendMessage(`❌ Error: ${msg.text}`, false);
      setStatus("Error", "error");
      el.sendBtn.disabled = false;
      el.sendBtn.classList.remove("is-stop");
      el.sendIcon.style.display = "";
      el.stopIcon.style.display = "none";
      el.sendBtn.title = "Send";
      break;

    case "model_set":
      // Model was switched via WS — notify the Models UI
      window.dispatchEvent(
        new CustomEvent("panther:model_set", {
          detail: { model: msg.model, provider: msg.provider },
        }),
      );
      setStatus(`Model: ${(msg.model || "").split("/").pop()}`, "ready");
      break;
  }
}

/* ══════════════════════════════════════════════════════════
   Sending messages
══════════════════════════════════════════════════════════ */
async function sendMessage() {
  const text = el.messageInput.value.trim();
  if (!text || state.isStreaming) return;

  // Switch hero → chat
  el.hero.style.display = "none";
  el.chatArea.style.display = "flex";

  // Append user bubble
  const displayText = state.pendingFiles.length
    ? text + "\n" + state.pendingFiles.map((f) => `📎 ${f.name}`).join("  ")
    : text;
  appendMessage(displayText, true);

  // Send over WS
  const attachments = state.pendingFiles.map((f) => f.path);
  wsSend({ text, attachments });

  // Reset input
  el.messageInput.value = "";
  autoResizeInput();
  clearAttachments();

  // Show typing indicator
  appendTypingIndicator();

  // Update UI state
  state.lastUserMsg = text;
  state.isStreaming = true;
  el.sendBtn.classList.add("is-stop");
  el.sendIcon.style.display = "none";
  el.stopIcon.style.display = "";
  el.sendBtn.title = "Stop generating";
  setStatus("Thinking…", "working");
  
  // Force scroll to bottom on new message send
  state.userScrolledUp = false;
  scrollToBottom();
}

/* ══════════════════════════════════════════════════════════
   Chat rendering
══════════════════════════════════════════════════════════ */
function appendMessage(text, isUser) {
  const msg = document.createElement("div");
  msg.className = `msg ${isUser ? "user" : "ai"}`;

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  if (isUser) {
    avatar.textContent = "👤";
  } else {
    avatar.innerHTML =
      '<img src="/static/panther-logo.jpg" alt="PANTHER" class="msg-avatar-img" />';
  }

  const body = document.createElement("div");
  body.className = "msg-body";

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.innerHTML = isUser
    ? escapeHtml(text).replace(/\n/g, "<br>")
    : marked.parse(text);

  body.appendChild(bubble);

  // Add Copy & Regenerate Actions for AI
  if (!isUser) {
    const actions = document.createElement("div");
    actions.className = "msg-actions";
    
    const copyBtn = document.createElement("button");
    copyBtn.className = "action-btn";
    copyBtn.innerHTML = `📋 Copy`;
    copyBtn.title = "Copy Message";
    copyBtn.onclick = () => {
      // Get pure text without HTML tags for the raw markdown response
      const rawText = msg.dataset.rawText || bubble.innerText;
      copyToClipboard(rawText, copyBtn, "Copied");
    };

    const regenBtn = document.createElement("button");
    regenBtn.className = "action-btn";
    regenBtn.innerHTML = `↻ Regenerate`;
    regenBtn.title = "Regenerate Response";
    regenBtn.onclick = () => {
      if (!state.lastUserMsg || state.isStreaming) return;
      el.messageInput.value = state.lastUserMsg;
      sendMessage();
    };

    actions.appendChild(copyBtn);
    actions.appendChild(regenBtn);
    body.appendChild(actions);
    
    // Store original text for copying later as it updates
    msg.dataset.rawText = text;
  }

  msg.appendChild(avatar);
  msg.appendChild(body);
  el.messages.appendChild(msg);

  if (!isUser) highlightCode(msg);
  scrollToBottom();
  return msg;
}

function restoreHistory(history) {
  el.hero.style.display = "none";
  el.chatArea.style.display = "flex";
  el.messages.innerHTML = "";
  for (const m of history) {
    if (m.role === "user" || m.role === "assistant") {
      appendMessage(m.content || "", m.role === "user");
    }
  }
}

function appendTypingIndicator() {
  removeTypingIndicator();
  const wrap = document.createElement("div");
  wrap.className = "msg ai";
  wrap.id = "typingIndicator";
  wrap.innerHTML = `
    <div class="msg-avatar">
      <img src="/static/panther-logo.jpg" alt="PANTHER" class="msg-avatar-img" />
    </div>
    <div class="msg-body">
      <div class="typing-indicator">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    </div>`;
  el.messages.appendChild(wrap);
  scrollToBottom();
}

function removeTypingIndicator() {
  const ind = $("typingIndicator");
  if (ind) ind.remove();
}

function scrollToBottom() {
  if (!state.userScrolledUp) {
    el.chatArea.scrollTop = el.chatArea.scrollHeight;
  }
}

function highlightCode(container) {
  container.querySelectorAll("pre code").forEach((block) => {
    // If we haven't wrapped this code block yet, do it now
    const pre = block.parentElement;
    if (!pre.parentElement.classList.contains("code-block-wrapper")) {
      const wrapper = document.createElement("div");
      wrapper.className = "code-block-wrapper";
      
      const lang = (block.className.match(/language-(\w+)/) || [])[1] || "";
      const header = document.createElement("div");
      header.className = "code-header";
      header.innerHTML = `
        <span class="code-language">${lang}</span>
        <button class="code-copy-btn">📋 Copy code</button>
      `;
      
      pre.parentNode.insertBefore(wrapper, pre);
      wrapper.appendChild(header);
      wrapper.appendChild(pre);

      const copyBtn = header.querySelector(".code-copy-btn");
      copyBtn.addEventListener("click", () => {
        copyToClipboard(block.textContent, copyBtn, "Copied!");
      });
    }

    hljs.highlightElement(block);
  });
  
  // Also update dataset for parent bubble whenever we re-parse markdown
  const bubble = container.querySelector(".msg-bubble");
  if (bubble && container.dataset) {
      container.dataset.rawText = state.currentAiText;
  }
}

function copyToClipboard(text, btn, successText) {
  navigator.clipboard.writeText(text).then(() => {
    const original = btn.innerHTML;
    btn.innerHTML = `✓ ${successText}`;
    setTimeout(() => { btn.innerHTML = original; }, 2000);
  });
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/* ══════════════════════════════════════════════════════════
   Session / History
══════════════════════════════════════════════════════════ */
function renderHistory() {
  el.historyList.querySelectorAll(".history-item").forEach((n) => n.remove());
  el.historyEmpty.style.display = state.sessions.length === 0 ? "" : "none";

  for (const sess of state.sessions) {
    const title = sess.title || "Untitled";
    const btn = document.createElement("button");
    btn.className = "history-item";
    btn.dataset.sid = sess.id;
    if (sess.id === state.sessionId) btn.classList.add("active");

    btn.innerHTML = `
      <span class="history-item-text" title="${escapeHtml(title)}">${escapeHtml(title.length > 32 ? title.slice(0, 30) + "…" : title)}</span>
      <button class="history-del-btn" data-sid="${sess.id}" title="Delete">✕</button>`;

    btn.addEventListener("click", (e) => {
      if (e.target.closest(".history-del-btn")) return;
      switchSession(sess.id);
    });
    btn.querySelector(".history-del-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      deleteSession(sess.id);
    });

    el.historyList.appendChild(btn);
  }
}

function highlightActiveSession() {
  el.historyList.querySelectorAll(".history-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.sid === state.sessionId);
  });
}

function switchSession(sid) {
  state.sessionId = sid;
  el.messages.innerHTML = "";
  wsSend({ action: "switch_session", session_id: sid });
  highlightActiveSession();
}

function deleteSession(sid) {
  state.sessionToDelete = sid;
  el.deleteConfirmOverlay.style.display = "flex";
}

function confirmDeleteSession() {
  if (state.sessionToDelete) {
    wsSend({ action: "delete_session", session_id: state.sessionToDelete });
    state.sessionToDelete = null;
    el.deleteConfirmOverlay.style.display = "none";
  }
}

function cancelDeleteSession() {
  state.sessionToDelete = null;
  el.deleteConfirmOverlay.style.display = "none";
}

function newChat() {
  state.currentAiBubble = null;
  state.currentAiText = "";
  el.messages.innerHTML = "";
  el.hero.style.display = "flex";
  el.chatArea.style.display = "none";
  wsSend({ action: "new_session" });
}

/* ══════════════════════════════════════════════════════════
   File attachments
══════════════════════════════════════════════════════════ */
async function handleFileSelect(files) {
  for (const file of files) {
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (data.path) {
        state.pendingFiles.push({ name: file.name, path: data.path });
        addAttachmentPill(file.name, data.path);
      }
    } catch (e) {
      console.error("Upload failed:", e);
    }
  }
  el.attachBtn.classList.toggle("has-files", state.pendingFiles.length > 0);
}

function addAttachmentPill(name, path) {
  el.attachStrip.style.display = "";
  const pill = document.createElement("div");
  pill.className = "attachment-pill";
  pill.innerHTML = `<span>📎 ${escapeHtml(name)}</span>
    <button class="pill-remove" title="Remove">✕</button>`;
  pill.querySelector(".pill-remove").addEventListener("click", () => {
    state.pendingFiles = state.pendingFiles.filter((f) => f.path !== path);
    pill.remove();
    if (state.pendingFiles.length === 0) {
      el.attachStrip.style.display = "none";
      el.attachBtn.classList.remove("has-files");
    }
  });
  el.attachPills.appendChild(pill);
}

function clearAttachments() {
  state.pendingFiles = [];
  el.attachPills.innerHTML = "";
  el.attachStrip.style.display = "none";
  el.attachBtn.classList.remove("has-files");
}

/* ══════════════════════════════════════════════════════════
   Category popup
══════════════════════════════════════════════════════════ */
async function loadCategories() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    state.categories = data.categories || [];
    if (data.default_model)
      el.modelBadge.textContent = data.default_model.split("/").pop();
    renderCategoryPopup();
  } catch (_) {}
}

function renderCategoryPopup() {
  el.categoryPopup.innerHTML = `<div class="category-popup-header">Select Category</div>`;
  for (const cat of state.categories) {
    const item = document.createElement("button");
    item.className = `category-item${cat.id === state.activeCategory ? " active" : ""}`;
    item.dataset.id = cat.id;
    item.innerHTML = `
      <span class="cat-icon">${cat.icon}</span>
      <span class="cat-info">
        <div class="cat-label">${escapeHtml(cat.label)}</div>
        <div class="cat-model">${escapeHtml(cat.model)}</div>
      </span>
      <span class="cat-check">${cat.id === state.activeCategory ? "✓" : ""}</span>`;
    item.addEventListener("click", () => selectCategory(cat));
    el.categoryPopup.appendChild(item);
  }
}

function selectCategory(cat) {
  state.activeCategory = cat.id;
  el.categoryBtn.textContent = `${cat.icon} ${cat.label} ∧`;
  el.categoryPopup.style.display = "none";
  wsSend({ action: "set_category", category: cat.id });
  renderCategoryPopup();
}

/* ══════════════════════════════════════════════════════════
   Ollama Usage Tracker
   Persists to localStorage; auto-resets each day at midnight
══════════════════════════════════════════════════════════ */
const USAGE_KEY = "panther_ollama_usage";
const DATE_KEY = "panther_ollama_date";
const LIMIT_KEY = "panther_ollama_limit";

const usage = {
  today() {
    return new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  },
  load() {
    if (localStorage.getItem(DATE_KEY) !== this.today()) {
      localStorage.setItem(USAGE_KEY, "0");
      localStorage.setItem(DATE_KEY, this.today());
    }
    return parseInt(localStorage.getItem(USAGE_KEY) || "0", 10);
  },
  increment() {
    const n = this.load() + 1;
    localStorage.setItem(USAGE_KEY, String(n));
    this.render();
    return n;
  },
  reset() {
    localStorage.setItem(USAGE_KEY, "0");
    localStorage.setItem(DATE_KEY, this.today());
    this.render();
  },
  getLimit() {
    return parseInt(localStorage.getItem(LIMIT_KEY) || "200", 10);
  },
  setLimit(n) {
    localStorage.setItem(LIMIT_KEY, String(Math.max(1, n)));
  },
  render() {
    if (!el.usageBarFill) return;
    const count = this.load();
    const limit = this.getLimit();
    const pct = Math.min((count / limit) * 100, 100);

    if (el.ollamaLimit && !el.ollamaLimit.value) el.ollamaLimit.value = limit;

    el.usageBarFill.style.width = pct + "%";
    el.usageStats.textContent =
      `${count.toLocaleString()} / ${limit.toLocaleString()} requests today` +
      (pct >= 100 ? "  ⚠️ LIMIT REACHED" : "");

    const fill = el.usageBarFill;
    const warn = el.usageWarning;
    fill.classList.remove("warn", "danger");
    warn.style.display = "none";
    warn.className = "usage-warning";

    if (pct >= 90) {
      fill.classList.add("danger");
      warn.style.display = "";
      warn.classList.add("danger");
      warn.textContent =
        count >= limit
          ? "⛔ Daily limit reached — requests may be rejected."
          : `⚠️ ${Math.round(pct)}% used · Only ${limit - count} requests left!`;
    } else if (pct >= 70) {
      fill.classList.add("warn");
      warn.style.display = "";
      warn.classList.add("warn");
      warn.textContent = `🟡 ${Math.round(pct)}% of daily limit used · ${limit - count} requests remaining.`;
    }
  },
};

/* Also count each AI reply toward Ollama usage if Ollama is active */
function incrementUsageIfOllama() {
  // Only count if ollama is enabled (toggle checked in current DOM state)
  if (el.ollamaToggle && el.ollamaToggle.checked) {
    usage.increment();
  }
}

/* ══════════════════════════════════════════════════════════
   Settings modal
══════════════════════════════════════════════════════════ */
async function openSettings() {
  el.settingsStatus.textContent = "";
  el.settingsStatus.className = "settings-status";
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    el.defaultModel.value = data.default_model || "";
    el.ollamaToggle.checked = data.ollama_enabled || false;
    el.ollamaUrl.value = data.ollama_base_url || "";
    el.ollamaModel.value = data.ollama_model || "";
    el.nvdiaKey.value = "";
    el.googleKey.value = "";
    el.ollamaApiKey.value = "";
    el.nvdiaKey.placeholder = data.has_nvidia_key
      ? "(saved — enter to change)"
      : "nvapi-…";
    el.googleKey.placeholder = data.has_google_key
      ? "(saved — enter to change)"
      : "AIza…";
    el.ollamaApiKey.placeholder = data.has_ollama_key
      ? "(saved — enter to change)"
      : "sk-… or leave blank for local";
  } catch (_) {}
  // Render usage tracker
  usage.render();
  el.settingsOverlay.style.display = "flex";
}

async function saveSettings() {
  el.settingsStatus.textContent = "Saving…";
  el.settingsStatus.className = "settings-status";

  // Persist usage limit in localStorage before hitting the API
  const limitVal = parseInt(el.ollamaLimit.value, 10);
  if (!isNaN(limitVal) && limitVal > 0) usage.setLimit(limitVal);
  usage.render();

  const body = {
    default_model: el.defaultModel.value.trim() || null,
    ollama_enabled: el.ollamaToggle.checked,
    ollama_base_url: el.ollamaUrl.value.trim() || null,
    ollama_model: el.ollamaModel.value.trim() || null,
  };
  if (el.nvdiaKey.value.trim()) body.nvidia_api_key = el.nvdiaKey.value.trim();
  if (el.googleKey.value.trim())
    body.google_api_key = el.googleKey.value.trim();
  if (el.ollamaApiKey.value.trim())
    body.ollama_api_key = el.ollamaApiKey.value.trim();

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.ok) {
      el.settingsStatus.textContent = "✓ Saved";
      el.settingsStatus.className = "settings-status ok";
      await loadCategories();
      setTimeout(() => {
        el.settingsOverlay.style.display = "none";
      }, 900);
    } else {
      el.settingsStatus.textContent = `Error: ${data.error}`;
      el.settingsStatus.className = "settings-status err";
    }
  } catch (e) {
    el.settingsStatus.textContent = `Error: ${e.message}`;
    el.settingsStatus.className = "settings-status err";
  }
}

/* ══════════════════════════════════════════════════════════
   Status bar
══════════════════════════════════════════════════════════ */
function setStatus(text, state_) {
  el.statusText.textContent = text;
  el.statusDot.className = `status-dot${state_ ? " " + state_ : ""}`;
}

/* ══════════════════════════════════════════════════════════
   Input textarea auto-resize
══════════════════════════════════════════════════════════ */
function autoResizeInput() {
  el.messageInput.style.height = "auto";
  el.messageInput.style.height =
    Math.min(el.messageInput.scrollHeight, 140) + "px";
}

/* ══════════════════════════════════════════════════════════
   Event listeners
══════════════════════════════════════════════════════════ */
// Smart auto-scroll checking
el.chatArea.addEventListener("scroll", () => {
  // If user scrolls up by more than 10px from the bottom, pause auto-scroll
  const distanceToBottom = el.chatArea.scrollHeight - el.chatArea.scrollTop - el.chatArea.clientHeight;
  state.userScrolledUp = distanceToBottom > 10;
});

// Send & Stop
el.sendBtn.addEventListener("click", () => {
  if (state.isStreaming) {
    if (state.ws) {
      state.ws.close(); // Triggers server disconnect to abort generation
      state.isStreaming = false;
      setStatus("Stopped", "ready");
      el.sendBtn.disabled = false;
      el.sendBtn.classList.remove("is-stop");
      el.sendIcon.style.display = "";
      el.stopIcon.style.display = "none";
      el.sendBtn.title = "Send";
    }
  } else {
    sendMessage();
  }
});
el.messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
el.messageInput.addEventListener("input", autoResizeInput);

// Chips
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    el.messageInput.value = chip.dataset.prompt;
    el.messageInput.focus();
  });
});

// New chat
el.newChatBtn.addEventListener("click", newChat);

// Attach
el.attachBtn.addEventListener("click", () => el.fileInput.click());
el.fileInput.addEventListener("change", (e) => {
  if (e.target.files.length) {
    handleFileSelect(Array.from(e.target.files));
    e.target.value = "";
  }
});

// Paste files
document.addEventListener("paste", (e) => {
  const files = Array.from(e.clipboardData?.files || []);
  if (files.length) handleFileSelect(files);
});

// Drag & drop
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => {
  e.preventDefault();
  const files = Array.from(e.dataTransfer.files);
  if (files.length) handleFileSelect(files);
});

// Category popup
el.categoryBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  const open = el.categoryPopup.style.display !== "none";
  el.categoryPopup.style.display = open ? "none" : "block";
});
document.addEventListener("click", () => {
  el.categoryPopup.style.display = "none";
});

// Settings
el.settingsBtn.addEventListener("click", openSettings);
el.settingsClose.addEventListener("click", () => {
  el.settingsOverlay.style.display = "none";
});
el.settingsOverlay.addEventListener("click", (e) => {
  if (e.target === el.settingsOverlay)
    el.settingsOverlay.style.display = "none";
});
el.saveSettingsBtn.addEventListener("click", saveSettings);

// Delete Confirmation
el.deleteConfirmClose.addEventListener("click", cancelDeleteSession);
el.deleteConfirmCancel.addEventListener("click", cancelDeleteSession);
el.deleteConfirmOverlay.addEventListener("click", (e) => {
  if (e.target === el.deleteConfirmOverlay) cancelDeleteSession();
});
el.deleteConfirmBtn.addEventListener("click", confirmDeleteSession);

// Panther Live button — opens the voice assistant overlay on the same page
el.geminiLiveBtn.addEventListener('click', () => {
  if (window.PantherLive) window.PantherLive.open();
});

// Usage: limit field live-updates stored limit
el.ollamaLimit.addEventListener("change", () => {
  const n = parseInt(el.ollamaLimit.value, 10);
  if (!isNaN(n) && n > 0) {
    usage.setLimit(n);
    usage.render();
  }
});

// Reset button
el.resetUsageBtn.addEventListener("click", () => {
  usage.reset();
});

/* ══════════════════════════════════════════════════════════
   Init
══════════════════════════════════════════════════════════ */
(async () => {
  await loadCategories();
  connectWS();
})();
