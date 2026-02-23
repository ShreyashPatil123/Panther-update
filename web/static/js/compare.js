/**
 * PANTHER Compare — Side-by-side model comparison
 * Vertex AI Studio-inspired multi-model streaming comparison.
 */

/* ── Marked / hljs config ─────────────────────────────────── */
marked.setOptions({
  breaks: true,
  gfm: true,
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) return hljs.highlight(code, { language: lang }).value;
    return hljs.highlightAuto(code).value;
  },
});

/* ── State ─────────────────────────────────────────────────── */
const cmp = {
  ws: null,
  sessionId: crypto.randomUUID(),
  allModels: [],              // fetched from /api/models
  slots: [],                  // [{slotId, modelId, provider, temp, maxTokens, topP}]
  slotEls: {},                // slotId -> {container, content, meta, accText}
  nextSlotId: 0,
  isRunning: false,
  runningSlots: new Set(),
};

/* ── DOM refs ──────────────────────────────────────────────── */
const el = {
  grid:       document.getElementById('compareGrid'),
  prompt:     document.getElementById('comparePrompt'),
  runBtn:     document.getElementById('runAllBtn'),
  cancelBtn:  document.getElementById('cancelBtn'),
  addBtn:     document.getElementById('addSlotBtn'),
  status:     document.getElementById('compareStatus'),
};

/* ══════════════════════════════════════════════════════════════
   Models fetch (reuses existing /api/models endpoint)
   ══════════════════════════════════════════════════════════════ */
async function fetchModels() {
  try {
    const resp = await fetch('/api/models');
    const data = await resp.json();
    cmp.allModels = data.models || [];
  } catch (e) {
    console.error('Failed to fetch models:', e);
  }
}

/* ══════════════════════════════════════════════════════════════
   Slot Management
   ══════════════════════════════════════════════════════════════ */
function addSlot(preselect) {
  if (cmp.slots.length >= 4) return;

  const slotId = cmp.nextSlotId++;
  const slot = {
    slotId,
    modelId: preselect?.modelId || '',
    provider: preselect?.provider || 'nvidia',
    temp: preselect?.temp ?? 0.7,
    maxTokens: preselect?.maxTokens ?? 4096,
    topP: preselect?.topP ?? 1.0,
  };
  cmp.slots.push(slot);

  // Build DOM
  const col = document.createElement('div');
  col.className = 'compare-slot';
  col.id = `slot-${slotId}`;
  col.innerHTML = `
    <div class="slot-header">
      <div class="slot-header-top">
        <span class="slot-number">Slot ${slotId + 1}</span>
        <button class="slot-remove-btn" data-slot="${slotId}" title="Remove">&times;</button>
      </div>
      <select class="slot-model-select" data-slot="${slotId}">
        <option value="">Select a model...</option>
      </select>
      <div class="slot-params">
        <div class="slot-param">
          <label>Temp</label>
          <input type="range" min="0" max="2" step="0.1" value="${slot.temp}"
                 data-slot="${slotId}" data-param="temp" />
          <span class="slot-param-value" id="tempVal-${slotId}">${slot.temp}</span>
        </div>
        <div class="slot-param">
          <label>Max Tokens</label>
          <input type="number" min="64" max="16384" step="64" value="${slot.maxTokens}"
                 data-slot="${slotId}" data-param="maxTokens" />
        </div>
        <div class="slot-param">
          <label>Top-P</label>
          <input type="range" min="0" max="1" step="0.05" value="${slot.topP}"
                 data-slot="${slotId}" data-param="topP" />
          <span class="slot-param-value" id="topPVal-${slotId}">${slot.topP}</span>
        </div>
      </div>
    </div>
    <div class="slot-content" id="slotContent-${slotId}">
      <div class="slot-empty">Response will appear here</div>
    </div>
    <div class="slot-meta" id="slotMeta-${slotId}"></div>
    <div class="slot-actions">
      <button class="slot-action-btn" data-action="rerun" data-slot="${slotId}">Re-run</button>
      <button class="slot-action-btn" data-action="copy" data-slot="${slotId}">Copy</button>
    </div>
  `;

  el.grid.appendChild(col);

  // Store element refs
  cmp.slotEls[slotId] = {
    container: col,
    content: col.querySelector(`#slotContent-${slotId}`),
    meta: col.querySelector(`#slotMeta-${slotId}`),
    accText: '',
  };

  // Populate model dropdown
  populateModelSelect(slotId, slot.modelId);

  // Bind events
  col.querySelector('.slot-remove-btn').addEventListener('click', () => removeSlot(slotId));
  col.querySelector('.slot-model-select').addEventListener('change', (e) => {
    const opt = e.target.selectedOptions[0];
    slot.modelId = e.target.value;
    slot.provider = opt?.dataset.provider || 'nvidia';
  });
  col.querySelectorAll('input[data-param]').forEach(inp => {
    inp.addEventListener('input', () => {
      const param = inp.dataset.param;
      const val = parseFloat(inp.value);
      slot[param] = val;
      // Update displayed value for sliders
      if (param === 'temp') document.getElementById(`tempVal-${slotId}`).textContent = val.toFixed(1);
      if (param === 'topP') document.getElementById(`topPVal-${slotId}`).textContent = val.toFixed(2);
    });
  });
  col.querySelector('[data-action="rerun"]').addEventListener('click', () => rerunSlot(slotId));
  col.querySelector('[data-action="copy"]').addEventListener('click', () => copySlotResponse(slotId));

  updateGridCols();
  saveState();
}

function removeSlot(slotId) {
  if (cmp.slots.length <= 2) return; // minimum 2
  cmp.slots = cmp.slots.filter(s => s.slotId !== slotId);
  const colEl = cmp.slotEls[slotId]?.container;
  if (colEl) colEl.remove();
  delete cmp.slotEls[slotId];
  updateGridCols();
  saveState();
}

function populateModelSelect(slotId, preselect) {
  const sel = document.querySelector(`.slot-model-select[data-slot="${slotId}"]`);
  if (!sel) return;

  // Group by provider
  const groups = {};
  const provOrder = ['nvidia', 'ollama', 'gemini'];
  const provLabels = { nvidia: 'NVIDIA NIM', ollama: 'Ollama', gemini: 'Google Gemini' };

  cmp.allModels.forEach(m => {
    if (!groups[m.provider]) groups[m.provider] = [];
    groups[m.provider].push(m);
  });

  let html = '<option value="">Select a model...</option>';
  provOrder.forEach(prov => {
    const items = groups[prov];
    if (!items || !items.length) return;
    html += `<optgroup label="${provLabels[prov] || prov}">`;
    items.forEach(m => {
      const id = m.full_id || m.id;
      const selected = id === preselect ? ' selected' : '';
      html += `<option value="${esc(id)}" data-provider="${esc(m.provider)}"${selected}>${esc(m.name || id)}</option>`;
    });
    html += '</optgroup>';
  });
  sel.innerHTML = html;

  // If preselected, update the slot provider
  if (preselect) {
    const slot = cmp.slots.find(s => s.slotId === slotId);
    const model = cmp.allModels.find(m => (m.full_id || m.id) === preselect);
    if (slot && model) slot.provider = model.provider;
  }
}

function updateGridCols() {
  el.grid.classList.remove('cols-3', 'cols-4');
  if (cmp.slots.length === 3) el.grid.classList.add('cols-3');
  if (cmp.slots.length >= 4) el.grid.classList.add('cols-4');

  // Update add button state
  el.addBtn.style.display = cmp.slots.length >= 4 ? 'none' : '';
}

/* ══════════════════════════════════════════════════════════════
   WebSocket
   ══════════════════════════════════════════════════════════════ */
function connectWS() {
  setStatus('Connecting...');
  const url = `ws://${location.host}/ws/compare/${cmp.sessionId}`;
  cmp.ws = new WebSocket(url);

  cmp.ws.onopen = () => setStatus('Ready');
  cmp.ws.onclose = () => {
    setStatus('Disconnected — reconnecting...');
    setTimeout(connectWS, 2500);
  };
  cmp.ws.onerror = () => setStatus('Connection error');

  cmp.ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    switch (msg.type) {
      case 'compare_chunk':   handleChunk(msg.slot_id, msg.text); break;
      case 'compare_done':    handleDone(msg.slot_id, msg.meta); break;
      case 'compare_error':   handleError(msg.slot_id, msg.text); break;
      case 'compare_all_done': handleAllDone(); break;
    }
  };
}

/* ══════════════════════════════════════════════════════════════
   Message Handlers
   ══════════════════════════════════════════════════════════════ */
function handleChunk(slotId, text) {
  const s = cmp.slotEls[slotId];
  if (!s) return;
  s.accText += text;
  s.content.innerHTML = marked.parse(s.accText);
  s.content.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b));
  s.container.classList.add('streaming');
}

function handleDone(slotId, meta) {
  const s = cmp.slotEls[slotId];
  if (!s) return;
  cmp.runningSlots.delete(slotId);
  s.container.classList.remove('streaming');

  const provClass = meta.provider || 'nvidia';
  s.meta.innerHTML = `
    <span class="meta-badge ${esc(provClass)}">${esc(meta.provider)}</span>
    <span class="meta-stat"><span class="meta-label">TTFT:</span> <span class="meta-value">${meta.ttft_ms.toFixed(0)}ms</span></span>
    <span class="meta-stat"><span class="meta-label">Total:</span> <span class="meta-value">${(meta.total_ms / 1000).toFixed(1)}s</span></span>
    <span class="meta-stat"><span class="meta-label">Tokens:</span> <span class="meta-value">~${meta.token_count}</span></span>
  `;
  s.meta.classList.add('visible');

  updateRunningStatus();
}

function handleError(slotId, text) {
  if (slotId === -1) {
    // Global error
    setStatus(`Error: ${text}`);
    return;
  }
  const s = cmp.slotEls[slotId];
  if (!s) return;
  cmp.runningSlots.delete(slotId);
  s.container.classList.remove('streaming');
  s.content.innerHTML = `<div class="slot-error">${esc(text)}</div>`;
  updateRunningStatus();
}

function handleAllDone() {
  cmp.isRunning = false;
  cmp.runningSlots.clear();
  el.runBtn.disabled = false;
  el.cancelBtn.style.display = 'none';
  setStatus('Done');
}

function updateRunningStatus() {
  if (cmp.runningSlots.size > 0) {
    setStatus(`Streaming... (${cmp.runningSlots.size} remaining)`);
  }
}

/* ══════════════════════════════════════════════════════════════
   Run / Re-run / Cancel
   ══════════════════════════════════════════════════════════════ */
function runAll() {
  const prompt = el.prompt.value.trim();
  if (!prompt || cmp.isRunning) return;

  // Validate: every slot needs a model
  for (const slot of cmp.slots) {
    if (!slot.modelId) {
      alert(`Slot ${slot.slotId + 1} has no model selected.`);
      return;
    }
  }

  // Clear all slots
  for (const [id, s] of Object.entries(cmp.slotEls)) {
    s.accText = '';
    s.content.innerHTML = `
      <div class="slot-loading">
        <div class="slot-loading-dot"></div>
        <div class="slot-loading-dot"></div>
        <div class="slot-loading-dot"></div>
      </div>`;
    s.meta.classList.remove('visible');
    s.meta.innerHTML = '';
  }

  cmp.isRunning = true;
  cmp.runningSlots = new Set(cmp.slots.map(s => s.slotId));
  el.runBtn.disabled = true;
  el.cancelBtn.style.display = '';
  setStatus(`Streaming... (${cmp.slots.length} models)`);

  const payload = {
    action: 'compare',
    prompt,
    slots: cmp.slots.map(s => ({
      slot_id: s.slotId,
      model_id: s.modelId,
      provider: s.provider,
      temperature: s.temp,
      max_tokens: s.maxTokens,
      top_p: s.topP,
    })),
  };

  cmp.ws.send(JSON.stringify(payload));
}

function rerunSlot(slotId) {
  const prompt = el.prompt.value.trim();
  if (!prompt) return;
  const slot = cmp.slots.find(s => s.slotId === slotId);
  if (!slot || !slot.modelId) return;

  const s = cmp.slotEls[slotId];
  if (s) {
    s.accText = '';
    s.content.innerHTML = `
      <div class="slot-loading">
        <div class="slot-loading-dot"></div>
        <div class="slot-loading-dot"></div>
        <div class="slot-loading-dot"></div>
      </div>`;
    s.meta.classList.remove('visible');
    s.meta.innerHTML = '';
    s.container.classList.add('streaming');
  }

  cmp.runningSlots.add(slotId);
  setStatus(`Re-running slot ${slotId + 1}...`);

  cmp.ws.send(JSON.stringify({
    action: 'compare_rerun',
    prompt,
    slot: {
      slot_id: slotId,
      model_id: slot.modelId,
      provider: slot.provider,
      temperature: slot.temp,
      max_tokens: slot.maxTokens,
      top_p: slot.topP,
    },
  }));
}

function cancelAll() {
  if (cmp.ws && cmp.ws.readyState === WebSocket.OPEN) {
    cmp.ws.send(JSON.stringify({ action: 'compare_cancel' }));
  }
}

function copySlotResponse(slotId) {
  const s = cmp.slotEls[slotId];
  if (!s || !s.accText) return;
  navigator.clipboard.writeText(s.accText).then(() => {
    setStatus('Copied to clipboard');
    setTimeout(() => setStatus('Ready'), 1500);
  });
}

/* ══════════════════════════════════════════════════════════════
   Persistence (localStorage)
   ══════════════════════════════════════════════════════════════ */
const STORAGE_KEY = 'panther_compare_slots';

function saveState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(
      cmp.slots.map(s => ({
        modelId: s.modelId,
        provider: s.provider,
        temp: s.temp,
        maxTokens: s.maxTokens,
        topP: s.topP,
      }))
    ));
  } catch { /* noop */ }
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* noop */ }
  return null;
}

/* ══════════════════════════════════════════════════════════════
   Helpers
   ══════════════════════════════════════════════════════════════ */
function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function setStatus(text) {
  el.status.textContent = text;
}

/* ══════════════════════════════════════════════════════════════
   Event Listeners
   ══════════════════════════════════════════════════════════════ */
el.runBtn.addEventListener('click', runAll);
el.cancelBtn.addEventListener('click', cancelAll);
el.addBtn.addEventListener('click', () => addSlot());

// Ctrl+Enter to Run All
el.prompt.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    runAll();
  }
});

/* ══════════════════════════════════════════════════════════════
   Init
   ══════════════════════════════════════════════════════════════ */
(async () => {
  await fetchModels();
  connectWS();

  // Restore saved slot configs or create default 2 slots
  const saved = loadState();
  if (saved && saved.length >= 2) {
    saved.forEach(s => addSlot(s));
  } else {
    addSlot({ modelId: '', provider: 'nvidia', temp: 0.7, maxTokens: 4096, topP: 1.0 });
    addSlot({ modelId: '', provider: 'nvidia', temp: 0.7, maxTokens: 4096, topP: 1.0 });
  }
})();
