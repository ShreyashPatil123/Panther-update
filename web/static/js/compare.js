/**
 * PANTHER Compare — Vertex AI Studio-Style Multi-Model Playground
 * Concurrent WebSocket streaming · Performance metrics · Synchronized scroll
 */

/* ── Marked / hljs config ──────────────────────────────────── */
marked.setOptions({
  breaks: true,
  gfm: true,
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) return hljs.highlight(code, { language: lang }).value;
    return hljs.highlightAuto(code).value;
  },
});

/* ── State ──────────────────────────────────────────────────── */
const cmp = {
  ws: null,
  sessionId: crypto.randomUUID(),
  allModels: [],
  panes: [],            // [{paneId, modelId, provider, temp, maxTokens, topP}]
  paneEls: {},           // paneId -> {container, content, metrics, progress, accText}
  nextPaneId: 0,
  isRunning: false,
  runningPanes: new Set(),
  syncScrollEnabled: true,
  scrollLock: false,      // prevents recursive scroll events
};

/* ── DOM refs ──────────────────────────────────────────────── */
const $ = {
  workspace:    document.getElementById('workspace'),
  userPrompt:   document.getElementById('userPrompt'),
  systemPrompt: document.getElementById('systemPrompt'),
  runBtn:       document.getElementById('runAllBtn'),
  cancelBtn:    document.getElementById('cancelBtn'),
  addBtn:       document.getElementById('addPaneBtn'),
  statusBar:    document.getElementById('statusBar'),
  paneCount:    document.getElementById('paneCount'),
  systemToggle: document.getElementById('systemToggle'),
  systemBody:   document.getElementById('systemBody'),
  systemChevron:document.getElementById('systemChevron'),
};


/* ══════════════════════════════════════════════════════════════
   Models Discovery
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
   Pane Management
   ══════════════════════════════════════════════════════════════ */
function addPane(preselect) {
  if (cmp.panes.length >= 4) return;

  const paneId = cmp.nextPaneId++;
  const pane = {
    paneId,
    modelId:   preselect?.modelId || '',
    provider:  preselect?.provider || 'nvidia',
    temp:      preselect?.temp ?? 0.7,
    maxTokens: preselect?.maxTokens ?? 4096,
    topP:      preselect?.topP ?? 1.0,
  };
  cmp.panes.push(pane);

  const el = document.createElement('div');
  el.className = 'cmp-pane';
  el.id = `pane-${paneId}`;
  el.innerHTML = `
    <div class="cmp-pane-progress" id="progress-${paneId}"></div>
    <div class="cmp-pane-header">
      <div class="cmp-pane-header-top">
        <span class="cmp-pane-label">Model ${paneId + 1}</span>
        <button class="cmp-pane-remove" data-pane="${paneId}" title="Remove pane">
          <span class="material-symbols-rounded">close</span>
        </button>
      </div>
      <select class="cmp-model-select" data-pane="${paneId}">
        <option value="">Select a model...</option>
      </select>
      <button class="cmp-params-toggle" data-pane="${paneId}">
        <span class="material-symbols-rounded">expand_more</span>
        Parameters
      </button>
      <div class="cmp-params-body" id="params-${paneId}">
        <div class="cmp-params-grid">
          <div class="cmp-param">
            <div class="cmp-param-label">
              <span>Temp</span>
              <span class="cmp-param-value" id="tempVal-${paneId}">${pane.temp.toFixed(1)}</span>
            </div>
            <input type="range" min="0" max="2" step="0.1" value="${pane.temp}"
                   data-pane="${paneId}" data-param="temp" />
          </div>
          <div class="cmp-param">
            <div class="cmp-param-label">
              <span>Max Tokens</span>
            </div>
            <input type="number" min="64" max="32768" step="64" value="${pane.maxTokens}"
                   data-pane="${paneId}" data-param="maxTokens" />
          </div>
          <div class="cmp-param">
            <div class="cmp-param-label">
              <span>Top-P</span>
              <span class="cmp-param-value" id="topPVal-${paneId}">${pane.topP.toFixed(2)}</span>
            </div>
            <input type="range" min="0" max="1" step="0.05" value="${pane.topP}"
                   data-pane="${paneId}" data-param="topP" />
          </div>
        </div>
      </div>
    </div>
    <div class="cmp-pane-content" id="content-${paneId}">
      <div class="cmp-empty">
        <span class="material-symbols-rounded">smart_toy</span>
        <span>Response will appear here</span>
      </div>
    </div>
    <div class="cmp-pane-footer">
      <div class="cmp-pane-metrics" id="metrics-${paneId}"></div>
      <div class="cmp-pane-actions">
        <button class="cmp-action-btn" data-action="rerun" data-pane="${paneId}">
          <span class="material-symbols-rounded">replay</span> Re-run
        </button>
        <button class="cmp-action-btn" data-action="copy" data-pane="${paneId}">
          <span class="material-symbols-rounded">content_copy</span> Copy
        </button>
      </div>
    </div>
  `;

  $.workspace.appendChild(el);

  cmp.paneEls[paneId] = {
    container: el,
    content:   el.querySelector(`#content-${paneId}`),
    metrics:   el.querySelector(`#metrics-${paneId}`),
    progress:  el.querySelector(`#progress-${paneId}`),
    accText:   '',
  };

  populateModelSelect(paneId, pane.modelId);
  bindPaneEvents(el, pane, paneId);
  setupSyncScroll(paneId);
  updatePaneCount();
  saveState();
}

function bindPaneEvents(el, pane, paneId) {
  // Remove button
  el.querySelector('.cmp-pane-remove').addEventListener('click', () => removePane(paneId));

  // Model select
  el.querySelector('.cmp-model-select').addEventListener('change', (e) => {
    const opt = e.target.selectedOptions[0];
    pane.modelId = e.target.value;
    pane.provider = opt?.dataset.provider || 'nvidia';
    saveState();
  });

  // Params toggle
  el.querySelector('.cmp-params-toggle').addEventListener('click', (e) => {
    const btn = e.currentTarget;
    const body = el.querySelector(`#params-${paneId}`);
    btn.classList.toggle('open');
    body.classList.toggle('open');
  });

  // Param inputs
  el.querySelectorAll('input[data-param]').forEach(inp => {
    inp.addEventListener('input', () => {
      const param = inp.dataset.param;
      const val = parseFloat(inp.value);
      pane[param] = val;
      if (param === 'temp') document.getElementById(`tempVal-${paneId}`).textContent = val.toFixed(1);
      if (param === 'topP') document.getElementById(`topPVal-${paneId}`).textContent = val.toFixed(2);
      saveState();
    });
  });

  // Action buttons
  el.querySelector('[data-action="rerun"]').addEventListener('click', () => rerunPane(paneId));
  el.querySelector('[data-action="copy"]').addEventListener('click', () => copyPaneResponse(paneId));
}

function removePane(paneId) {
  if (cmp.panes.length <= 2) return;
  cmp.panes = cmp.panes.filter(p => p.paneId !== paneId);
  const container = cmp.paneEls[paneId]?.container;
  if (container) container.remove();
  delete cmp.paneEls[paneId];
  updatePaneCount();
  saveState();
}

function populateModelSelect(paneId, preselect) {
  const sel = document.querySelector(`.cmp-model-select[data-pane="${paneId}"]`);
  if (!sel) return;

  const groups = {};
  const provOrder = ['nvidia', 'gemini', 'ollama'];
  const provLabels = { nvidia: 'NVIDIA NIM', gemini: 'Google Gemini', ollama: 'Ollama' };

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

  if (preselect) {
    const pane = cmp.panes.find(p => p.paneId === paneId);
    const model = cmp.allModels.find(m => (m.full_id || m.id) === preselect);
    if (pane && model) pane.provider = model.provider;
  }
}

function updatePaneCount() {
  $.paneCount.textContent = `${cmp.panes.length} model${cmp.panes.length !== 1 ? 's' : ''}`;
  $.addBtn.style.display = cmp.panes.length >= 4 ? 'none' : '';
}


/* ══════════════════════════════════════════════════════════════
   Synchronized Scrolling
   ══════════════════════════════════════════════════════════════ */
function setupSyncScroll(paneId) {
  const contentEl = cmp.paneEls[paneId]?.content;
  if (!contentEl) return;

  contentEl.addEventListener('scroll', () => {
    if (!cmp.syncScrollEnabled || cmp.scrollLock) return;
    cmp.scrollLock = true;

    const scrollRatio = contentEl.scrollTop / Math.max(1, contentEl.scrollHeight - contentEl.clientHeight);

    for (const [id, p] of Object.entries(cmp.paneEls)) {
      if (parseInt(id) === paneId) continue;
      const target = p.content;
      const maxScroll = target.scrollHeight - target.clientHeight;
      target.classList.add('sync-scrolling');
      target.scrollTop = scrollRatio * maxScroll;
    }

    requestAnimationFrame(() => {
      cmp.scrollLock = false;
      for (const p of Object.values(cmp.paneEls)) {
        p.content.classList.remove('sync-scrolling');
      }
    });
  });
}


/* ══════════════════════════════════════════════════════════════
   WebSocket Connection
   ══════════════════════════════════════════════════════════════ */
function connectWS() {
  setStatus('Connecting...');
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${location.host}/ws/compare/${cmp.sessionId}`;
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
      case 'compare_chunk':    handleChunk(msg.slot_id, msg.text); break;
      case 'compare_done':     handleDone(msg.slot_id, msg.meta); break;
      case 'compare_error':    handleError(msg.slot_id, msg.text); break;
      case 'compare_all_done': handleAllDone(); break;
    }
  };
}


/* ══════════════════════════════════════════════════════════════
   Message Handlers
   ══════════════════════════════════════════════════════════════ */
function handleChunk(paneId, text) {
  const p = cmp.paneEls[paneId];
  if (!p) return;
  p.accText += text;
  p.content.innerHTML = marked.parse(p.accText);
  p.content.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b));
  // Auto-scroll to bottom
  p.content.scrollTop = p.content.scrollHeight;
}

function handleDone(paneId, meta) {
  const p = cmp.paneEls[paneId];
  if (!p) return;
  cmp.runningPanes.delete(paneId);

  // Stop progress indicator
  p.progress.classList.remove('active');

  const provClass = meta.provider || 'nvidia';
  const totalSec = meta.total_ms / 1000;
  const tokPerSec = totalSec > 0 ? (meta.token_count / totalSec).toFixed(1) : '—';

  p.metrics.innerHTML = `
    <span class="cmp-provider-badge ${esc(provClass)}">${esc(meta.provider)}</span>
    <span class="cmp-metric">
      <span class="cmp-metric-label">TTFT</span>
      <span class="cmp-metric-value">${meta.ttft_ms.toFixed(0)}ms</span>
    </span>
    <span class="cmp-metric">
      <span class="cmp-metric-label">Latency</span>
      <span class="cmp-metric-value">${totalSec.toFixed(1)}s</span>
    </span>
    <span class="cmp-metric">
      <span class="cmp-metric-label">Tokens</span>
      <span class="cmp-metric-value">~${meta.token_count}</span>
    </span>
    <span class="cmp-metric">
      <span class="cmp-metric-label">Tok/s</span>
      <span class="cmp-metric-value">${tokPerSec}</span>
    </span>
  `;
  p.metrics.classList.add('visible');

  updateRunningStatus();
}

function handleError(paneId, text) {
  if (paneId === -1) {
    setStatus(`Error: ${text}`);
    return;
  }
  const p = cmp.paneEls[paneId];
  if (!p) return;
  cmp.runningPanes.delete(paneId);
  p.progress.classList.remove('active');
  p.content.innerHTML = `
    <div class="cmp-error">
      <span class="material-symbols-rounded">error</span>
      <span>${esc(text)}</span>
    </div>
  `;
  updateRunningStatus();
}

function handleAllDone() {
  cmp.isRunning = false;
  cmp.runningPanes.clear();
  $.runBtn.disabled = false;
  $.cancelBtn.classList.remove('visible');
  setStatus('Done');
}

function updateRunningStatus() {
  if (cmp.runningPanes.size > 0) {
    setStatus(`Streaming... (${cmp.runningPanes.size} remaining)`);
  }
}


/* ══════════════════════════════════════════════════════════════
   Run / Re-run / Cancel
   ══════════════════════════════════════════════════════════════ */
function runAll() {
  const prompt = $.userPrompt.value.trim();
  if (!prompt || cmp.isRunning) return;

  // Validate all panes have models selected
  for (const pane of cmp.panes) {
    if (!pane.modelId) {
      setStatus(`⚠ Model ${pane.paneId + 1} has no model selected`);
      return;
    }
  }

  // Clear all pane responses
  for (const [id, p] of Object.entries(cmp.paneEls)) {
    p.accText = '';
    p.content.innerHTML = `
      <div class="cmp-loading">
        <div class="cmp-loading-dot"></div>
        <div class="cmp-loading-dot"></div>
        <div class="cmp-loading-dot"></div>
      </div>`;
    p.metrics.classList.remove('visible');
    p.metrics.innerHTML = '';
    p.progress.classList.add('active');
  }

  cmp.isRunning = true;
  cmp.runningPanes = new Set(cmp.panes.map(p => p.paneId));
  $.runBtn.disabled = true;
  $.cancelBtn.classList.add('visible');
  setStatus(`Streaming... (${cmp.panes.length} models)`);

  const systemPrompt = $.systemPrompt.value.trim();

  const payload = {
    action: 'compare',
    prompt,
    system_prompt: systemPrompt || undefined,
    slots: cmp.panes.map(p => ({
      slot_id: p.paneId,
      model_id: p.modelId,
      provider: p.provider,
      temperature: p.temp,
      max_tokens: p.maxTokens,
      top_p: p.topP,
    })),
  };

  cmp.ws.send(JSON.stringify(payload));
}

function rerunPane(paneId) {
  const prompt = $.userPrompt.value.trim();
  if (!prompt) return;
  const pane = cmp.panes.find(p => p.paneId === paneId);
  if (!pane || !pane.modelId) return;

  const p = cmp.paneEls[paneId];
  if (p) {
    p.accText = '';
    p.content.innerHTML = `
      <div class="cmp-loading">
        <div class="cmp-loading-dot"></div>
        <div class="cmp-loading-dot"></div>
        <div class="cmp-loading-dot"></div>
      </div>`;
    p.metrics.classList.remove('visible');
    p.metrics.innerHTML = '';
    p.progress.classList.add('active');
  }

  cmp.runningPanes.add(paneId);
  setStatus(`Re-running Model ${paneId + 1}...`);

  const systemPrompt = $.systemPrompt.value.trim();

  cmp.ws.send(JSON.stringify({
    action: 'compare_rerun',
    prompt,
    system_prompt: systemPrompt || undefined,
    slot: {
      slot_id: paneId,
      model_id: pane.modelId,
      provider: pane.provider,
      temperature: pane.temp,
      max_tokens: pane.maxTokens,
      top_p: pane.topP,
    },
  }));
}

function cancelAll() {
  if (cmp.ws && cmp.ws.readyState === WebSocket.OPEN) {
    cmp.ws.send(JSON.stringify({ action: 'compare_cancel' }));
  }
}

function copyPaneResponse(paneId) {
  const p = cmp.paneEls[paneId];
  if (!p || !p.accText) return;
  navigator.clipboard.writeText(p.accText).then(() => {
    setStatus('Copied to clipboard ✓');
    setTimeout(() => setStatus('Ready'), 1500);
  });
}


/* ══════════════════════════════════════════════════════════════
   System Prompt Toggle
   ══════════════════════════════════════════════════════════════ */
$.systemToggle.addEventListener('click', () => {
  $.systemBody.classList.toggle('open');
  $.systemChevron.classList.toggle('open');
});


/* ══════════════════════════════════════════════════════════════
   Auto-resize Input Textarea
   ══════════════════════════════════════════════════════════════ */
$.userPrompt.addEventListener('input', () => {
  $.userPrompt.style.height = 'auto';
  $.userPrompt.style.height = Math.min($.userPrompt.scrollHeight, 150) + 'px';
});


/* ══════════════════════════════════════════════════════════════
   Persistence (localStorage)
   ══════════════════════════════════════════════════════════════ */
const STORAGE_KEY = 'panther_compare_v2';

function saveState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      panes: cmp.panes.map(p => ({
        modelId: p.modelId,
        provider: p.provider,
        temp: p.temp,
        maxTokens: p.maxTokens,
        topP: p.topP,
      })),
      systemPrompt: $.systemPrompt.value,
    }));
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
  $.statusBar.textContent = text;
}


/* ══════════════════════════════════════════════════════════════
   Event Listeners
   ══════════════════════════════════════════════════════════════ */
$.runBtn.addEventListener('click', runAll);
$.cancelBtn.addEventListener('click', cancelAll);
$.addBtn.addEventListener('click', () => addPane());

// Ctrl+Enter to Run All
$.userPrompt.addEventListener('keydown', (e) => {
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

  // Restore saved state or create 2 default panes
  const saved = loadState();
  if (saved && saved.panes && saved.panes.length >= 2) {
    saved.panes.forEach(p => addPane(p));
    if (saved.systemPrompt) $.systemPrompt.value = saved.systemPrompt;
  } else {
    addPane({ modelId: '', provider: 'nvidia', temp: 0.7, maxTokens: 4096, topP: 1.0 });
    addPane({ modelId: '', provider: 'nvidia', temp: 0.7, maxTokens: 4096, topP: 1.0 });
  }
})();
