// ─── PANTHER Browser Bridge — Content Script ────────────────────────────────
// Injected into every page. Acts as bridge between the page context and
// the background service worker.
//
// Responsibilities:
// 1. Intercept PANTHER_RPC messages from page context (sent via Playwright's
//    page.evaluate / postMessage) and forward to background.js
// 2. Capture console logs for debugging
// 3. Setup mutation observers for dynamic page changes

const PANTHER_CONTENT_VERSION = "1.0.0";

// ── Console Log Capture ─────────────────────────────────────────────────────
// Store the last 50 console messages for debugging
(function setupConsoleCapture() {
  if (window.__pantherConsoleSetup) return;
  window.__pantherConsoleSetup = true;
  window.__pantherConsoleLogs = [];

  const MAX_LOGS = 50;
  const origConsole = {
    log: console.log,
    warn: console.warn,
    error: console.error,
    info: console.info,
  };

  function captureLog(level, args) {
    try {
      const message = Array.from(args)
        .map((a) => {
          if (typeof a === "string") return a;
          try { return JSON.stringify(a); } catch { return String(a); }
        })
        .join(" ");

      window.__pantherConsoleLogs.push({
        level,
        message: message.slice(0, 500),
        timestamp: Date.now(),
      });

      // Keep only the most recent logs
      if (window.__pantherConsoleLogs.length > MAX_LOGS) {
        window.__pantherConsoleLogs.shift();
      }
    } catch {
      // Silently fail — never disrupt the page
    }
  }

  console.log = function (...args) {
    captureLog("log", args);
    origConsole.log.apply(console, args);
  };
  console.warn = function (...args) {
    captureLog("warn", args);
    origConsole.warn.apply(console, args);
  };
  console.error = function (...args) {
    captureLog("error", args);
    origConsole.error.apply(console, args);
  };
  console.info = function (...args) {
    captureLog("info", args);
    origConsole.info.apply(console, args);
  };
})();


// ── Page → Background RPC Bridge ────────────────────────────────────────────
// Playwright's page.evaluate() can post messages to window. This listener
// forwards those RPC calls to the background service worker.
window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (!event.data || event.data.type !== "PANTHER_RPC") return;

  const { method, params, requestId } = event.data;

  chrome.runtime.sendMessage(
    {
      type: "PANTHER_RPC",
      method,
      params: params ?? {},
    },
    (response) => {
      // Send the response back to the page context
      window.postMessage(
        {
          type: "PANTHER_RPC_RESPONSE",
          requestId,
          result: response,
        },
        "*"
      );
    }
  );
});


// ── Mutation Observer — Track DOM Changes ────────────────────────────────────
// Notify when significant DOM changes occur (e.g., SPA navigation, modal open)
let _lastSignificantChange = 0;
const DEBOUNCE_MS = 1000;

const observer = new MutationObserver((mutations) => {
  const now = Date.now();
  if (now - _lastSignificantChange < DEBOUNCE_MS) return;

  // Check if changes are significant (not just style/animation changes)
  let significantChanges = 0;
  for (const mutation of mutations) {
    if (mutation.type === "childList" && mutation.addedNodes.length > 0) {
      for (const node of mutation.addedNodes) {
        if (node.nodeType === Node.ELEMENT_NODE) {
          significantChanges++;
        }
      }
    }
  }

  if (significantChanges >= 3) {
    _lastSignificantChange = now;
    // Store the change event for the background worker to pick up
    window.__pantherLastDOMChange = {
      timestamp: now,
      changeCount: significantChanges,
      url: window.location.href,
    };
  }
});

// Start observing once the body is available
if (document.body) {
  observer.observe(document.body, {
    childList: true,
    subtree: true,
  });
}


// ── PANTHER Element Interaction Helpers ──────────────────────────────────────
// These are available for the background script to call via executeInTab

/**
 * Scroll an element into view with smooth animation.
 */
window.__pantherScrollTo = function (selector) {
  const el = document.querySelector(selector);
  if (!el) return { scrolled: false, error: "Element not found" };
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  return { scrolled: true };
};

/**
 * Get a snapshot of all visible interactive elements.
 */
window.__pantherGetInteractiveSnapshot = function () {
  const elements = [];
  const selectors =
    'a, button, input, select, textarea, [role="button"], [role="link"], ' +
    '[role="menuitem"], [tabindex]:not([tabindex="-1"])';

  document.querySelectorAll(selectors).forEach((el, index) => {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return;

    // Check if element is in viewport
    const inViewport =
      rect.top >= 0 &&
      rect.left >= 0 &&
      rect.bottom <= window.innerHeight &&
      rect.right <= window.innerWidth;

    elements.push({
      index,
      tag: el.tagName.toLowerCase(),
      text: (el.innerText || el.value || el.placeholder || "").trim().slice(0, 80),
      id: el.id || undefined,
      name: el.name || undefined,
      type: el.type || undefined,
      ariaLabel: el.getAttribute("aria-label") || undefined,
      href: el.getAttribute("href") || undefined,
      rect: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        w: Math.round(rect.width),
        h: Math.round(rect.height),
      },
      inViewport,
    });
  });

  return {
    elements,
    total: elements.length,
    url: window.location.href,
    title: document.title,
    timestamp: Date.now(),
  };
};


// ── Initialization ──────────────────────────────────────────────────────────
console.log(`[PANTHER Bridge] Content script injected (v${PANTHER_CONTENT_VERSION})`);
