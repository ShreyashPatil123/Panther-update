/**
 * PANTHER Models — fetch + search + select
 * Handles the shiny Models button, model picker panel, and model switching.
 */

(function () {
  'use strict';

  // ── State ───────────────────────────────────────────────────────────────
  let allModels = [];
  let activeProvider = 'all';
  let currentModelId = '';
  let pickerOpen = false;
  let wsRef = null; // set by app.js

  // ── DOM refs (resolved after DOMContentLoaded) ──────────────────────────
  let modelsBtn, modelPicker, modelSearch, modelList, modelLoading,
      modelPickerClose, modelPickerStats, providerTabs;

  // ── Model fetch ──────────────────────────────────────────────────────────
  async function fetchModels() {
    showLoading(true);
    try {
      const resp = await fetch('/api/models');
      const data = await resp.json();
      allModels = data.models || [];
      currentModelId = data.current_model || '';
      renderModels();

      const total = allModels.length;
      const byProv = {};
      allModels.forEach(m => { byProv[m.provider] = (byProv[m.provider] || 0) + 1; });
      const parts = Object.entries(byProv).map(([k, v]) => `${v} ${k}`);
      modelPickerStats.textContent = `${total} models — ${parts.join(', ')}`;

      // Show/hide provider tabs based on available providers
      updateProviderTabs(byProv);
    } catch (e) {
      showLoading(false);
      modelList.innerHTML = `<div class="model-empty">Failed to load models: ${e.message}</div>`;
    }
  }

  function updateProviderTabs(byProv) {
    providerTabs.querySelectorAll('.mprov-tab[data-prov]').forEach(tab => {
      const prov = tab.dataset.prov;
      if (prov === 'all') { tab.style.display = ''; return; }
      tab.style.display = byProv[prov] ? '' : 'none';
    });
  }

  function showLoading(show) {
    modelLoading.style.display = show ? 'flex' : 'none';
  }

  // ── Render model list ────────────────────────────────────────────────────
  function renderModels() {
    showLoading(false);
    const query = (modelSearch.value || '').toLowerCase().trim();
    const filtered = allModels.filter(m => {
      const matchProv = activeProvider === 'all' || m.provider === activeProvider;
      const matchQ = !query
        || m.id.toLowerCase().includes(query)
        || (m.name || '').toLowerCase().includes(query);
      return matchProv && matchQ;
    });

    if (!filtered.length) {
      modelList.innerHTML = '<div class="model-empty">No models match your search.</div>';
      return;
    }

    // Group by provider
    const groups = {};
    filtered.forEach(m => {
      if (!groups[m.provider]) groups[m.provider] = [];
      groups[m.provider].push(m);
    });

    const provOrder = ['nvidia', 'ollama', 'gemini'];
    let html = '';
    provOrder.forEach(prov => {
      const items = groups[prov];
      if (!items) return;
      const info = providerInfo(prov);
      html += `<div class="model-group">
        <div class="model-group-label" style="--prov-color:${info.color}">${info.icon} ${info.label} <span class="model-group-count">${items.length}</span></div>`;
      items.forEach(m => {
        const isActive = m.full_id === currentModelId || m.id === currentModelId;
        const size = m.size ? ` · ${formatSize(m.size)}` : '';
        const fallback = m.fallback ? ' model-fallback' : '';
        html += `<button class="model-item${isActive ? ' model-item-active' : ''}${fallback}"
          data-id="${escHtml(m.full_id || m.id)}"
          data-provider="${escHtml(m.provider)}"
          title="${escHtml(m.full_id || m.id)}">
          <span class="model-item-name">${escHtml(m.name || m.id)}</span>
          <span class="model-item-meta">${escHtml(m.full_id || m.id)}${size}</span>
          ${isActive ? '<span class="model-item-check">✓</span>' : ''}
        </button>`;
      });
      html += '</div>';
    });
    modelList.innerHTML = html;

    // Bind click
    modelList.querySelectorAll('.model-item').forEach(btn => {
      btn.addEventListener('click', () => selectModel(btn.dataset.id, btn.dataset.provider));
    });
  }

  // ── Select a model ───────────────────────────────────────────────────────
  async function selectModel(modelId, provider) {
    if (!modelId) return;

    // Optimistic UI — update current immediately
    currentModelId = modelId;
    renderModels();

    // Close picker
    closePicker();

    // Update model badge
    updateModelBadge(modelId, provider);

    // Tell backend + re-init HTTP client
    try {
      await fetch('/api/model/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId, provider }),
      });
    } catch { /* non-fatal */ }

    // Also notify via WebSocket for immediate mid-session effect
    if (wsRef && wsRef.readyState === WebSocket.OPEN) {
      wsRef.send(JSON.stringify({ action: 'set_model', model_id: modelId, provider }));
    }
  }

  function updateModelBadge(modelId, provider) {
    const badge = document.getElementById('modelBadge');
    if (!badge) return;
    const info = providerInfo(provider);
    const shortName = modelId.split('/').pop();
    badge.textContent = shortName;
    badge.style.borderColor = info.color + '66';
    badge.style.color = info.color;
    badge.title = `${info.label}: ${modelId}`;
  }

  // ── Provider info ────────────────────────────────────────────────────────
  function providerInfo(prov) {
    const map = {
      nvidia: { label: 'NVIDIA NIM', color: '#76b900', icon: '⬛' },
      ollama: { label: 'Ollama',     color: '#a78bfa', icon: '🦙' },
      gemini: { label: 'Gemini',     color: '#4285f4', icon: '✦'  },
    };
    return map[prov] || { label: prov, color: '#888', icon: '◆' };
  }

  // ── Open / Close ─────────────────────────────────────────────────────────
  function openPicker() {
    modelPicker.hidden = false;
    pickerOpen = true;
    modelsBtn.classList.add('shiny-cta-active');
    modelSearch.focus();
    if (allModels.length === 0) fetchModels();
    else renderModels();
  }

  function closePicker() {
    modelPicker.hidden = true;
    pickerOpen = false;
    modelsBtn.classList.remove('shiny-cta-active');
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  function formatSize(bytes) {
    if (!bytes) return '';
    const gb = bytes / 1e9;
    return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / 1e6).toFixed(0)} MB`;
  }

  function escHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── Init ─────────────────────────────────────────────────────────────────
  function init() {
    modelsBtn        = document.getElementById('modelsBtn');
    modelPicker      = document.getElementById('modelPicker');
    modelSearch      = document.getElementById('modelSearch');
    modelList        = document.getElementById('modelList');
    modelLoading     = document.getElementById('modelLoading');
    modelPickerClose = document.getElementById('modelPickerClose');
    modelPickerStats = document.getElementById('modelPickerStats');
    providerTabs     = document.getElementById('modelProviderTabs');

    if (!modelsBtn) return; // guard

    modelsBtn.addEventListener('click', () => pickerOpen ? closePicker() : openPicker());
    modelPickerClose.addEventListener('click', closePicker);

    // Close picker when clicking outside
    document.addEventListener('click', e => {
      if (pickerOpen && !modelPicker.contains(e.target) && e.target !== modelsBtn && !modelsBtn.contains(e.target)) {
        closePicker();
      }
    });

    // Search filter
    modelSearch.addEventListener('input', () => renderModels());
    modelSearch.addEventListener('keydown', e => { if (e.key === 'Escape') closePicker(); });

    // Provider tabs
    providerTabs.querySelectorAll('.mprov-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        activeProvider = tab.dataset.prov;
        providerTabs.querySelectorAll('.mprov-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        renderModels();
      });
    });

    // Listen for WS model_set confirmations dispatched by app.js
    window.addEventListener('panther:model_set', e => {
      const { model, provider } = e.detail || {};
      if (model) { currentModelId = model; updateModelBadge(model, provider); }
    });

    // Expose WS setter for app.js to call: window.PantherModels.setWs(ws)
    window.PantherModels = { setWs: ws => { wsRef = ws; } };
  }

  document.addEventListener('DOMContentLoaded', init);
})();
