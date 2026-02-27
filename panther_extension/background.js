// ─── PANTHER Browser Bridge — Background Service Worker ─────────────────────
// Routes RPC commands from the Python backend (via content script messaging)
// to the appropriate content script or DevTools action.
//
// Communication flow:
//   Python ExtensionRPCClient → Playwright page.evaluate() → window.postMessage
//   → content.js listener → chrome.runtime.sendMessage → this background.js
//   → chrome.scripting.executeScript in active tab → response back

const PANTHER_VERSION = "1.0.0";

// ── RPC Dispatcher ──────────────────────────────────────────────────────────
async function dispatchRpcRequest(method, params, tabId) {
  switch (method) {

    case "capture_dom":
      return await executeInTab(tabId, captureDOM, [params?.options ?? {}]);

    case "capture_accessibility":
      return await executeInTab(tabId, captureAccessibilityTree, []);

    case "find_element":
      return await executeInTab(tabId, findElementByIntent, [
        params.intent ?? "",
        params.context ?? "",
      ]);

    case "highlight_element":
      return await executeInTab(tabId, highlightElement, [
        params.selector,
        params.color ?? "#FF6B35",
      ]);

    case "clear_highlights":
      return await executeInTab(tabId, clearAllHighlights, []);

    case "get_form_fields":
      return await executeInTab(tabId, extractFormFields, []);

    case "shadow_query":
      return await executeInTab(tabId, queryShadowDOM, [params.selector]);

    case "get_console_logs":
      return await executeInTab(tabId, getConsoleLogs, []);

    case "scroll_to_element":
      return await executeInTab(tabId, scrollToElement, [params.selector]);

    case "get_page_state":
      return await executeInTab(tabId, getPageState, []);

    case "dismiss_dialog":
      try {
        return await chrome.debugger.sendCommand(
          { tabId },
          "Page.handleJavaScriptDialog",
          { accept: params?.accept ?? true, promptText: params?.text ?? "" }
        );
      } catch (e) {
        return { error: e.message };
      }

    case "ping":
      return { status: "ok", version: PANTHER_VERSION };

    default:
      return { error: `Unknown RPC method: ${method}` };
  }
}

// ── Listen for messages from content scripts or external extensions ──────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "PANTHER_RPC") return false;

  (async () => {
    const tabId = sender.tab?.id ?? message.tab_id;
    if (!tabId) {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tabs.length) {
        sendResponse({ error: "No active tab" });
        return;
      }
      const activeTabId = tabs[0].id;
      const result = await dispatchRpcRequest(message.method, message.params ?? {}, activeTabId);
      sendResponse(result);
    } else {
      const result = await dispatchRpcRequest(message.method, message.params ?? {}, tabId);
      sendResponse(result);
    }
  })();

  return true; // Keep message channel open for async response
});

// Also listen for external messages (from other extensions or the Python backend)
chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  if (message?.type !== "PANTHER_RPC") return false;

  (async () => {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tabId = message.tab_id ?? tabs[0]?.id;
    if (!tabId) {
      sendResponse({ error: "No active tab" });
      return;
    }
    const result = await dispatchRpcRequest(message.method, message.params ?? {}, tabId);
    sendResponse(result);
  })();

  return true;
});


// ── Helper: Execute function in tab context ─────────────────────────────────
async function executeInTab(tabId, fn, args = []) {
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId, allFrames: false },
      func: fn,
      args,
    });
    return results[0]?.result ?? null;
  } catch (err) {
    return { error: err.message };
  }
}


// ═══════════════════════════════════════════════════════════════════════════════
// Functions below are serialized and run in the PAGE context via executeScript.
// They must be self-contained (no closures over background.js variables).
// ═══════════════════════════════════════════════════════════════════════════════


// ── DOM Capture ─────────────────────────────────────────────────────────────
function captureDOM(options = {}) {
  const maxLength = options.maxLength ?? 50000;
  const includeHidden = options.includeHidden ?? false;

  function cleanNode(node, depth = 0) {
    if (depth > 15) return null;
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent.trim();
      return text ? { type: "text", value: text } : null;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return null;

    const el = node;
    const style = window.getComputedStyle(el);
    if (!includeHidden && style.display === "none") return null;
    if (!includeHidden && style.visibility === "hidden") return null;

    const attrs = {};
    for (const attr of el.attributes) {
      if (
        [
          "id", "class", "type", "name", "placeholder", "aria-label",
          "aria-labelledby", "role", "href", "value", "data-testid",
        ].includes(attr.name)
      ) {
        attrs[attr.name] = attr.value;
      }
    }

    const rect = el.getBoundingClientRect();
    const children = Array.from(el.childNodes)
      .map((child) => cleanNode(child, depth + 1))
      .filter(Boolean);

    return {
      tag: el.tagName.toLowerCase(),
      attrs,
      text: el.innerText?.slice(0, 200) ?? "",
      rect: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        w: Math.round(rect.width),
        h: Math.round(rect.height),
      },
      children: children.length > 0 ? children : undefined,
    };
  }

  const tree = cleanNode(document.body);
  const json = JSON.stringify(tree);
  return json.slice(0, maxLength);
}


// ── Accessibility Tree Capture ──────────────────────────────────────────────
function captureAccessibilityTree() {
  const interactives = [];
  const selectors =
    'a, button, input, select, textarea, [role="button"], [role="link"], ' +
    '[role="menuitem"], [role="tab"], [role="checkbox"], [role="radio"], [tabindex]';

  document.querySelectorAll(selectors).forEach((el) => {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return;

    interactives.push({
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute("role") ?? el.tagName.toLowerCase(),
      label:
        el.getAttribute("aria-label") ??
        el.textContent?.trim().slice(0, 80) ??
        el.placeholder ??
        "",
      type: el.type ?? "",
      id: el.id ?? "",
      name: el.name ?? "",
      rect: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        w: Math.round(rect.width),
        h: Math.round(rect.height),
      },
      inViewport:
        rect.top >= 0 && rect.bottom <= window.innerHeight,
    });
  });

  return {
    interactives,
    title: document.title,
    url: window.location.href,
    timestamp: Date.now(),
  };
}


// ── Form Field Extraction ───────────────────────────────────────────────────
function extractFormFields() {
  const fields = [];
  const formElements = document.querySelectorAll(
    'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), ' +
    'select, textarea, [role="combobox"], [role="listbox"], [role="radiogroup"]'
  );

  formElements.forEach((el, idx) => {
    // Find associated label
    let label = "";
    if (el.id) {
      const labelEl = document.querySelector(`label[for="${el.id}"]`);
      if (labelEl) label = labelEl.textContent.trim();
    }
    if (!label)
      label = el.getAttribute("aria-label") ?? el.placeholder ?? "";
    if (!label) {
      const parent = el.closest("label");
      if (parent) label = parent.textContent.replace(el.value || "", "").trim();
    }

    const rect = el.getBoundingClientRect();
    fields.push({
      index: idx,
      tag: el.tagName.toLowerCase(),
      type: el.type ?? el.getAttribute("role") ?? "text",
      label: label.slice(0, 150),
      placeholder: el.placeholder ?? "",
      name: el.name ?? el.id ?? "",
      required: el.required,
      currentValue: el.value ?? "",
      options:
        el.tagName === "SELECT"
          ? Array.from(el.options).map((o) => ({
              value: o.value,
              text: o.text,
            }))
          : undefined,
      rect: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        w: Math.round(rect.width),
        h: Math.round(rect.height),
      },
    });
  });

  // Google Forms specific structure
  const gFormQuestions = document.querySelectorAll(
    "[data-item-id], .freebirdFormviewerViewItemsItemItem"
  );
  const gFormFields = Array.from(gFormQuestions).map((q) => ({
    question:
      q.querySelector(
        '.freebirdFormviewerViewItemsItemItemTitle, [role="heading"]'
      )?.textContent.trim() ?? "",
    type: q.querySelector('input[type="radio"]')
      ? "radio"
      : q.querySelector('input[type="checkbox"]')
        ? "checkbox"
        : q.querySelector('input[type="text"]')
          ? "text"
          : q.querySelector("textarea")
            ? "paragraph"
            : q.querySelector("select")
              ? "dropdown"
              : "unknown",
    options: Array.from(
      q.querySelectorAll('[role="radio"] span, [role="checkbox"] span')
    ).map((s) => s.textContent.trim()),
  }));

  return {
    fields,
    gFormFields: gFormFields.length > 0 ? gFormFields : undefined,
  };
}


// ── Semantic Element Finder ─────────────────────────────────────────────────
function findElementByIntent(intent, context) {
  const candidates = [];
  document
    .querySelectorAll(
      'a, button, input, select, textarea, [onclick], [role="button"], ' +
      '[role="link"], [role="tab"], [role="menuitem"]'
    )
    .forEach((el) => {
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return; // Skip invisible

      const text = (
        el.innerText ??
        el.value ??
        el.placeholder ??
        el.getAttribute("aria-label") ??
        ""
      )
        .trim()
        .toLowerCase();

      // Simple relevance score based on keyword overlap
      const intentWords = intent.toLowerCase().split(/\s+/);
      let score = 0;
      for (const word of intentWords) {
        if (word.length > 2 && text.includes(word)) score += 5;
      }

      candidates.push({
        tag: el.tagName.toLowerCase(),
        text: text.slice(0, 100),
        id: el.id,
        classes: el.className,
        ariaLabel: el.getAttribute("aria-label") ?? "",
        href: el.getAttribute("href") ?? "",
        type: el.type ?? "",
        rect: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          w: Math.round(rect.width),
          h: Math.round(rect.height),
        },
        score,
      });
    });

  // Return top 20 candidates sorted by relevance
  return candidates.sort((a, b) => b.score - a.score).slice(0, 20);
}


// ── Element Highlighter ─────────────────────────────────────────────────────
function highlightElement(selector, color = "#FF6B35") {
  // Remove any existing highlights first
  document.getElementById("__panther_highlight__")?.remove();
  document.getElementById("__panther_highlight_style__")?.remove();

  try {
    const el = document.querySelector(selector);
    if (!el) return { found: false };

    const outline = document.createElement("div");
    outline.id = "__panther_highlight__";
    const rect = el.getBoundingClientRect();
    Object.assign(outline.style, {
      position: "fixed",
      left: `${rect.left - 3}px`,
      top: `${rect.top - 3}px`,
      width: `${rect.width + 6}px`,
      height: `${rect.height + 6}px`,
      border: `3px solid ${color}`,
      borderRadius: "4px",
      zIndex: "999999",
      pointerEvents: "none",
      boxShadow: `0 0 12px ${color}80`,
      animation: "panther-pulse 1s ease-in-out infinite",
    });

    const style = document.createElement("style");
    style.id = "__panther_highlight_style__";
    style.textContent = `
      @keyframes panther-pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
      }
    `;
    document.head.appendChild(style);
    document.body.appendChild(outline);

    return {
      found: true,
      rect: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        w: Math.round(rect.width),
        h: Math.round(rect.height),
      },
    };
  } catch (e) {
    return { found: false, error: e.message };
  }
}

function clearAllHighlights() {
  document.getElementById("__panther_highlight__")?.remove();
  document.getElementById("__panther_highlight_style__")?.remove();
  return { cleared: true };
}


// ── Page State ──────────────────────────────────────────────────────────────
function getPageState() {
  return {
    url: window.location.href,
    title: document.title,
    readyState: document.readyState,
    scrollY: window.scrollY,
    scrollHeight: document.body.scrollHeight,
    viewportHeight: window.innerHeight,
    viewportWidth: window.innerWidth,
    hasCaptcha: !!(
      document.querySelector('iframe[src*="recaptcha"]') ||
      document.querySelector('iframe[src*="hcaptcha"]') ||
      document.querySelector("#cf-challenge-running") ||
      document.querySelector('[id*="captcha"]')
    ),
    hasForm: document.querySelectorAll("form").length > 0,
    dialogs:
      document.querySelectorAll('[role="dialog"], [role="alertdialog"]').length,
  };
}


// ── Console Log Capture ─────────────────────────────────────────────────────
function getConsoleLogs() {
  return window.__pantherConsoleLogs ?? [];
}


// ── Shadow DOM Query ────────────────────────────────────────────────────────
function queryShadowDOM(selector) {
  function deepQuery(root, sel) {
    const result = root.querySelector(sel);
    if (result) return result;
    for (const el of root.querySelectorAll("*")) {
      if (el.shadowRoot) {
        const found = deepQuery(el.shadowRoot, sel);
        if (found) return found;
      }
    }
    return null;
  }
  const el = deepQuery(document, selector);
  if (!el) return { found: false };
  const rect = el.getBoundingClientRect();
  return {
    found: true,
    rect: {
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      w: Math.round(rect.width),
      h: Math.round(rect.height),
    },
    tag: el.tagName.toLowerCase(),
  };
}


// ── Scroll to Element ───────────────────────────────────────────────────────
function scrollToElement(selector) {
  const el = document.querySelector(selector);
  if (!el) return { scrolled: false };
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  return { scrolled: true };
}


// ── Lifecycle logging ───────────────────────────────────────────────────────
console.log(`[PANTHER Bridge] Background service worker loaded (v${PANTHER_VERSION})`);
