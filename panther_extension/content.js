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


// ═══════════════════════════════════════════════════════════════════════════════
// ── PANTHER AI Cursor Visual System ─────────────────────────────────────────
// Injects a visual AI cursor, click ripple, and status banner into the page.
// All elements use pointer-events:none — zero interference with Playwright.
// ═══════════════════════════════════════════════════════════════════════════════

(function _initPantherVisuals() {
  if (window.__pantherVisualsInit) return;
  window.__pantherVisualsInit = true;

  // ── Inject stylesheet ───────────────────────────────────────────────────
  const style = document.createElement("style");
  style.id = "__panther_visual_styles__";
  style.textContent = `
    /* ── AI Cursor ──────────────────────────────────────────────────────── */
    #panther-ai-cursor {
      position: fixed;
      top: 0;
      left: 0;
      width: 28px;
      height: 28px;
      z-index: 9999999;
      pointer-events: none;
      will-change: transform;
      transition: none;
      opacity: 0;
      filter: drop-shadow(0 2px 6px rgba(255, 107, 53, 0.5));
    }
    #panther-ai-cursor.panther-visible {
      opacity: 1;
    }
    #panther-ai-cursor svg {
      width: 100%;
      height: 100%;
    }

    /* ── Click Ripple ──────────────────────────────────────────────────── */
    #panther-click-ripple {
      position: fixed;
      width: 40px;
      height: 40px;
      margin-left: -20px;
      margin-top: -20px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(255, 107, 53, 0.6) 0%, rgba(168, 85, 247, 0.3) 50%, transparent 70%);
      z-index: 9999998;
      pointer-events: none;
      opacity: 0;
      transform: scale(0);
      will-change: transform, opacity;
    }
    #panther-click-ripple.panther-ripple-active {
      animation: pantherRipple 0.5s ease-out forwards;
    }

    @keyframes pantherRipple {
      0%   { opacity: 1;   transform: scale(0.3); }
      50%  { opacity: 0.6; transform: scale(1.8); }
      100% { opacity: 0;   transform: scale(2.5); }
    }

    /* ── Status Banner ─────────────────────────────────────────────────── */
    #panther-status-banner {
      position: fixed;
      top: 8px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 9999999;
      pointer-events: none;
      padding: 6px 20px;
      border-radius: 20px;
      background: linear-gradient(135deg, rgba(20, 20, 40, 0.92), rgba(30, 15, 50, 0.92));
      color: #f0f0f0;
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      font-size: 12px;
      font-weight: 500;
      letter-spacing: 0.5px;
      border: 1px solid rgba(255, 107, 53, 0.5);
      box-shadow: 0 0 12px rgba(255, 107, 53, 0.25), 0 0 24px rgba(168, 85, 247, 0.15);
      animation: pantherGlow 2s ease-in-out infinite alternate;
      opacity: 0;
      transition: opacity 0.3s ease;
    }
    #panther-status-banner.panther-visible {
      opacity: 1;
    }

    @keyframes pantherGlow {
      0%   { box-shadow: 0 0 8px rgba(255, 107, 53, 0.2), 0 0 16px rgba(168, 85, 247, 0.1); }
      100% { box-shadow: 0 0 16px rgba(255, 107, 53, 0.4), 0 0 32px rgba(168, 85, 247, 0.25); }
    }
  `;
  document.head.appendChild(style);

  // ── Create AI Cursor element ────────────────────────────────────────────
  const cursor = document.createElement("div");
  cursor.id = "panther-ai-cursor";
  cursor.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="pantherCursorGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#FF6B35"/>
          <stop offset="100%" stop-color="#A855F7"/>
        </linearGradient>
      </defs>
      <path d="M5.5 3.21V20.8c0 .45.54.67.85.35l4.86-4.86a.5.5 0 0 1 .35-.15h6.87c.45 0 .67-.54.35-.85L5.85 2.35a.5.5 0 0 0-.35.86z"
            fill="url(#pantherCursorGrad)" stroke="#1a1a2e" stroke-width="1"/>
    </svg>
  `;
  document.body.appendChild(cursor);

  // ── Create Click Ripple element ─────────────────────────────────────────
  const ripple = document.createElement("div");
  ripple.id = "panther-click-ripple";
  document.body.appendChild(ripple);

  // ── Create Status Banner element ────────────────────────────────────────
  const banner = document.createElement("div");
  banner.id = "panther-status-banner";
  banner.textContent = "🤖 PANTHER is controlling this tab";
  document.body.appendChild(banner);

  // ═══════════════════════════════════════════════════════════════════════
  // Global control functions — called by Playwright via page.evaluate()
  // ═══════════════════════════════════════════════════════════════════════

  /**
   * Move the AI cursor to (x, y). Uses CSS transform for GPU compositing.
   */
  window.__movePantherCursor = function (x, y) {
    const el = document.getElementById("panther-ai-cursor");
    if (!el) return;
    el.style.transform = `translate(${x}px, ${y}px)`;
    if (!el.classList.contains("panther-visible")) {
      el.classList.add("panther-visible");
    }
  };

  /**
   * Show a click ripple effect at (x, y).
   */
  window.__showPantherClick = function (x, y) {
    const el = document.getElementById("panther-click-ripple");
    if (!el) return;
    // Reset animation
    el.classList.remove("panther-ripple-active");
    // Force reflow to restart animation
    void el.offsetWidth;
    el.style.left = x + "px";
    el.style.top = y + "px";
    el.classList.add("panther-ripple-active");
  };

  /**
   * Toggle the status banner and AI cursor visibility.
   */
  window.__setPantherStatus = function (isActive) {
    const banner = document.getElementById("panther-status-banner");
    const cursor = document.getElementById("panther-ai-cursor");
    if (banner) {
      if (isActive) banner.classList.add("panther-visible");
      else banner.classList.remove("panther-visible");
    }
    if (cursor) {
      if (isActive) cursor.classList.add("panther-visible");
      else cursor.classList.remove("panther-visible");
    }
  };

})();


// ── Initialization ──────────────────────────────────────────────────────────
console.log(`[PANTHER Bridge] Content script injected (v${PANTHER_CONTENT_VERSION})`);
