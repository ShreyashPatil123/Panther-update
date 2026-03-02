"""Task Dispatcher — coordinates between AgentOrchestrator and BrowserSubAgent.

Connects to the user's existing browser via Chrome DevTools Protocol (CDP)
so that automation happens in new tabs of the SAME browser window.

Uses a dedicated thread + ProactorEventLoop for Playwright on Windows,
since uvicorn's SelectorEventLoop does not support subprocess transport.
"""

import asyncio
import logging
import os
import random
import sys
import threading
from typing import AsyncGenerator, Optional

from loguru import logger

try:
    from playwright.async_api import (
        async_playwright,
        Browser,
        BrowserContext,
        Page,
    )
except ImportError:
    async_playwright = None  # type: ignore


# ── Stealth Script (injected on every page load) ─────────────────────────────

STEALTH_SCRIPT = """
// Hide webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Fake plugin list (empty plugins = bot)
Object.defineProperty(navigator, 'plugins', {
  get: () => [
    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
  ]
});

// Fake language list
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

// Normalize permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
  parameters.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(parameters)
);
"""

UI_OVERLAY_SCRIPT = """
(function() {
    if (window.__panther_ui_injected) return;
    window.__panther_ui_injected = true;
    window.__panther_paused = false;
    window.__panther_allow_next_action = false;

    // --- Create Wrapper ---
    const wrapper = document.createElement('div');
    wrapper.id = 'panther-automation-overlay';
    wrapper.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:2147483647;pointer-events:none;overflow:hidden;box-sizing:border-box;margin:0;padding:0;font-family:system-ui,-apple-system,sans-serif;';
    
    // --- Animated Glowing Vignette Border ---
    const border = document.createElement('div');
    border.id = 'panther-glow-vignette';
    // Base cyan theme: rgba(6, 182, 212, X)
    border.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;box-sizing:border-box;pointer-events:none;' +
                           'background: radial-gradient(circle at center, transparent 60%, rgba(15, 23, 42, 0.3) 100%);' +
                           'box-shadow: inset 0 0 100px 20px rgba(6, 182, 212, 0.3);' +
                           'animation: vignette-pulse 4s ease-in-out infinite alternate; transition: box-shadow 0.2s;';
                           
    // --- Bottom Pill Status Bar ---
    const pill = document.createElement('div');
    pill.style.cssText = 'position:absolute;bottom:24px;left:50%;transform:translateX(-50%);' +
                         'background:rgba(15, 23, 42, 0.85);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);' +
                         'color:#e2e8f0;padding:8px 16px;border-radius:9999px;display:flex;align-items:center;gap:12px;' +
                         'box-shadow:0 10px 25px -5px rgba(0,0,0,0.5), 0 0 15px rgba(6, 182, 212, 0.2);' +
                         'border:1px solid rgba(255,255,255,0.1);pointer-events:auto;transition:all 0.3s ease;';
    
    // Status Icon + Text Container
    const statusContainer = document.createElement('div');
    statusContainer.id = 'panther-status-pill';
    statusContainer.style.cssText = 'display:flex;align-items:center;gap:10px;font-size:14px;font-weight:500;letter-spacing:0.3px;';
    
    // Working Pulse Animation SVG (replaces the simple dot)
    const workingHtml = `
        <div style="position:relative;width:16px;height:16px;display:flex;align-items:center;justify-content:center;">
            <div style="position:absolute;width:100%;height:100%;background:#06b6d4;border-radius:50%;opacity:0.4;animation:ping 2s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>
            <div style="position:absolute;width:8px;height:8px;background:#06b6d4;border-radius:50%;box-shadow:0 0 8px #06b6d4;"></div>
        </div>
        Working...
    `;
    
    // Render paused state
    const pausedHtml = `
        <div style="width:8px;height:8px;background:#f59e0b;border-radius:50%;box-shadow:0 0 8px #f59e0b;"></div>
        Paused
    `;

    statusContainer.innerHTML = workingHtml;

    // Pause / Stop Agent interactive button
    const pauseBtn = document.createElement('button');
    pauseBtn.id = 'panther-pause-btn';
    pauseBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect>
        </svg>
    `;
    pauseBtn.style.cssText = 'background:rgba(255,255,255,0.1);border:none;color:#94a3b8;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all 0.2s ease;padding:0;';
    
    pauseBtn.onmouseover = () => { if(!window.__panther_paused) { pauseBtn.style.background = 'rgba(239, 68, 68, 0.2)'; pauseBtn.style.color = '#ef4444'; } };
    pauseBtn.onmouseout = () => { if(!window.__panther_paused) { pauseBtn.style.background = 'rgba(255,255,255,0.1)'; pauseBtn.style.color = '#94a3b8'; } };
    
    pauseBtn.onclick = async (e) => {
        e.preventDefault();
        e.stopPropagation();
        const isNowPaused = !window.__panther_paused;
        window.__panther_paused = isNowPaused;
        
        if (window.pantherPauseEvent) {
            await window.pantherPauseEvent(isNowPaused);
        }
        
        if (isNowPaused) {
            border.style.animation = 'none';
            border.style.boxShadow = 'inset 0 0 80px 10px rgba(245, 158, 11, 0.3)';
            statusContainer.innerHTML = pausedHtml;
            pauseBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                    <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
            `;
            pauseBtn.style.background = 'rgba(16, 185, 129, 0.2)';
            pauseBtn.style.color = '#10b981';
            pauseBtn.onmouseover = () => { pauseBtn.style.background = 'rgba(16, 185, 129, 0.4)'; };
            pauseBtn.onmouseout = () => { pauseBtn.style.background = 'rgba(16, 185, 129, 0.2)'; };
            // Remove global not-allowed cursor when paused
            document.documentElement.classList.remove('panther-active');
        } else {
            border.style.animation = 'vignette-pulse 4s ease-in-out infinite alternate';
            statusContainer.innerHTML = workingHtml;
            pauseBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect>
                </svg>
            `;
            pauseBtn.style.background = 'rgba(255,255,255,0.1)';
            pauseBtn.style.color = '#94a3b8';
            pauseBtn.onmouseover = () => { pauseBtn.style.background = 'rgba(239, 68, 68, 0.2)'; pauseBtn.style.color = '#ef4444'; };
            pauseBtn.onmouseout = () => { pauseBtn.style.background = 'rgba(255,255,255,0.1)'; pauseBtn.style.color = '#94a3b8'; };
            // Reapply global cursor
            document.documentElement.classList.add('panther-active');
        }
    };

    pill.appendChild(statusContainer);
    pill.appendChild(document.createElement('div')).style.cssText = 'width:1px;height:16px;background:rgba(255,255,255,0.1);';
    pill.appendChild(pauseBtn);
    wrapper.appendChild(border);
    wrapper.appendChild(pill);
    
    // --- Global Animations and Overrides ---
    const style = document.createElement('style');
    style.textContent = `
        @keyframes vignette-pulse {
            0% { box-shadow: inset 0 0 80px 10px rgba(6, 182, 212, 0.2); }
            100% { box-shadow: inset 0 0 160px 40px rgba(6, 182, 212, 0.6); }
        }
        @keyframes ping {
            75%, 100% { transform: scale(2); opacity: 0; }
        }
        @keyframes error-shake {
            0%, 100% { transform: translateX(-50%); }
            20%, 60% { transform: translateX(calc(-50% - 4px)); }
            40%, 80% { transform: translateX(calc(-50% + 4px)); }
        }
        /* Force not-allowed cursor globally when active */
        html.panther-active, html.panther-active * {
            cursor: not-allowed !important;
        }
        html.panther-active .panther-interactive, html.panther-active .panther-interactive * {
            cursor: pointer !important;
        }
    `;
    document.head.appendChild(style);
    
    // Tag the pill button to allow interaction
    pill.classList.add('panther-interactive');

    // Wait for body to exist before appending
    const observer = new MutationObserver(() => {
        if (document.body && !document.getElementById('panther-automation-overlay')) {
            document.body.appendChild(wrapper);
            // Apply cursor class
            if (!window.__panther_paused) {
                document.documentElement.classList.add('panther-active');
            }
        }
    });
    observer.observe(document.documentElement, { childList: true });

    // --- Active Visual Rejection Function ---
    let flashTimeout;
    function triggerRejection() {
        // Flash border red
        const oldAnim = border.style.animation;
        border.style.animation = 'none';
        border.style.boxShadow = 'inset 0 0 150px 50px rgba(239, 68, 68, 0.7)';
        
        // Shake pill
        pill.style.animation = 'error-shake 0.4s ease-in-out';
        
        clearTimeout(flashTimeout);
        flashTimeout = setTimeout(() => {
            if (!window.__panther_paused) {
                border.style.animation = oldAnim || 'vignette-pulse 4s ease-in-out infinite alternate';
                border.style.boxShadow = '';
            } else {
                border.style.boxShadow = 'inset 0 0 80px 10px rgba(245, 158, 11, 0.3)';
            }
            pill.style.animation = 'none';
        }, 400);
    }

    // --- Intercept all human events ---
    const events = ['click', 'mousedown', 'mouseup', 'keydown', 'wheel'];
    events.forEach(eventType => {
        window.addEventListener(eventType, (e) => {
            // Let the overlay elements receive clicks
            if (e.target.closest && e.target.closest('#panther-automation-overlay')) return;
            
            // Bypass during PAUSE or trusted agent actions
            if (window.__panther_paused || window.__panther_allow_next_action) {
                // Keep cursor correct during pause
                if (window.__panther_paused) {
                    document.documentElement.classList.remove('panther-active');
                }
                return;
            }
            
            // Otherwise, BLOCK interaction and flash
            e.preventDefault();
            e.stopPropagation();
            
            // Only flash visually on mouse attempts (don't spam flash on wheel/keydown repeats)
            if (eventType === 'mousedown' || eventType === 'click') {
                triggerRejection();
            }
        }, { capture: true, passive: false });
    });
    
    // Add visual click ripple for the agent (trusted actions)
    window.__showPantherClick = (x, y) => {
        const ripple = document.createElement('div');
        ripple.style.cssText = `position:fixed;top:${y}px;left:${x}px;width:20px;height:20px;margin-top:-10px;margin-left:-10px;border-radius:50%;background:rgba(6, 182, 212, 0.6);border:2px solid #06b6d4;z-index:2147483647;pointer-events:none;transform:scale(0);opacity:1;transition:all 0.5s cubic-bezier(0, 0, 0.2, 1);`;
        document.body.appendChild(ripple);
        
        // Trigger reflow
        void ripple.offsetWidth;
        
        ripple.style.transform = 'scale(2)';
        ripple.style.opacity = '0';
        
        setTimeout(() => { if (ripple.parentNode) ripple.parentNode.removeChild(ripple); }, 500);
    };
})();
"""


# ═══════════════════════════════════════════════════════════════════════════════
# PlaywrightThread — runs Playwright in its own asyncio loop on a background
# thread so it works inside uvicorn's SelectorEventLoop on Windows.
# ═══════════════════════════════════════════════════════════════════════════════

class _PlaywrightThread:
    """Manages a dedicated thread with a ProactorEventLoop for Playwright."""

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> asyncio.AbstractEventLoop:
        """Start the background thread and return its event loop."""
        if self._loop is not None and self._loop.is_running():
            return self._loop

        ready = threading.Event()

        def _run():
            if sys.platform == "win32":
                self._loop = asyncio.ProactorEventLoop()
            else:
                self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=_run, daemon=True, name="playwright-loop")
        self._thread.start()
        ready.wait(timeout=5)
        return self._loop

    def run_coroutine(self, coro):
        """Schedule a coroutine on the Playwright loop and wait for the result."""
        if self._loop is None:
            self.start()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    async def run_coroutine_async(self, coro):
        """Schedule a coroutine on the Playwright loop, await from the calling loop."""
        if self._loop is None:
            self.start()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        # Bridge: await the concurrent.futures.Future from the calling loop
        return await asyncio.wrap_future(future)

    def stop(self):
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        self._loop = None
        self._thread = None


# Module-level singleton
_pw_thread = _PlaywrightThread()


class TaskDispatcher:
    """
    Coordinates between AgentOrchestrator and BrowserSubAgent.
    Manages browser lifecycle and streams SSE progress events.

    Connects to the user's existing browser via CDP so that automation
    happens in new tabs of the SAME browser window.

    All Playwright calls run on a dedicated ProactorEventLoop thread
    to avoid Windows SelectorEventLoop subprocess limitations.
    """

    def __init__(self, api_key: str, headless: Optional[bool] = None, cdp_url: Optional[str] = None):
        self.api_key = api_key
        self.headless = headless if headless is not None else (
            os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
        )
        self.cdp_url = cdp_url or os.getenv("CDP_URL", "http://127.0.0.1:9222")
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        # ── Pause / Resume state ─────────────────────────────────────────
        self.running_event = asyncio.Event()
        self.running_event.set()  # Default: running

    # ── Pause / Resume controls ──────────────────────────────────────────

    def pause_agent(self) -> None:
        """Pause the agent — the sub-agent loop will block at the next checkpoint."""
        self.running_event.clear()
        logger.info("[TaskDispatcher] Agent PAUSED")

    def resume_agent(self) -> None:
        """Resume the agent — unblocks the sub-agent loop."""
        self.running_event.set()
        logger.info("[TaskDispatcher] Agent RESUMED")

    def get_state(self) -> str:
        """Return current agent state: 'running' or 'paused'."""
        return "running" if self.running_event.is_set() else "paused"

    async def _is_alive(self) -> bool:
        """Check if the browser is still usable."""
        if not self._browser:
            return False
        try:
            alive = await _pw_thread.run_coroutine_async(self._check_browser())
            return alive
        except Exception:
            return False

    async def _check_browser(self) -> bool:
        """Internal: check browser liveness (runs on Playwright thread)."""
        try:
            if self._browser and not self._browser.is_connected():
                return False
            return True
        except Exception:
            return False


    async def initialize(self) -> None:
        """Connect to user's browser via CDP, or fall back to launching Chromium."""
        if async_playwright is None:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            )

        # Clean up any stale state first
        if self._playwright or self._browser:
            try:
                await self.close()
            except Exception:
                pass
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None

        # Ensure the Playwright thread is running
        _pw_thread.start()

        # Run the actual Playwright launch on the dedicated loop
        await _pw_thread.run_coroutine_async(self._launch_browser())

        logger.info("[TaskDispatcher] Browser initialized (CDP={}, headless={})".format(
            self.cdp_url, self.headless
        ))

    async def _launch_browser(self) -> None:
        """Connect to existing browser via CDP, or launch standalone Chromium."""
        self._playwright = await async_playwright().start()

        # ── Try connecting to existing browser via CDP ────────────────────
        try:
            # Increased timeout to 15000 as Perplexity recommends waiting for OS port bind
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self.cdp_url, timeout=15000
            )
            
            # Perplexity fix: Must use the EXISTING default context.
            # Calling new_context() over CDP spawns a new window!
            contexts = self._browser.contexts
            if not contexts:
                # Wait briefly for browser to finish initiating contexts
                await asyncio.sleep(2)
                contexts = self._browser.contexts
                
            if contexts:
                self._context = contexts[0]
            else:
                logger.warning("[TaskDispatcher] No existing contexts found via CDP. Forcing new context.")
                self._context = await self._browser.new_context()

            # Inject stealth and UI scripts for this context
            await self._context.add_init_script(STEALTH_SCRIPT)
            await self._context.add_init_script(UI_OVERLAY_SCRIPT)

            # Expose Python binding for the Pause button
            async def handle_pause_event(source, is_paused: bool):
                if is_paused:
                    self.pause_agent()
                else:
                    self.resume_agent()
            
            try:
                # If already exposed in this context from a previous run, it might throw
                await self._context.expose_binding("pantherPauseEvent", handle_pause_event)
            except Exception as e:
                logger.debug(f"[TaskDispatcher] Binding pantherPauseEvent already exists or failed: {e}")

            # The actual new tab will be created when a task is dispatched
            logger.info(f"[TaskDispatcher] Connected to existing browser via CDP: {self.cdp_url}")
            return

        except Exception as e:
            logger.warning(f"[TaskDispatcher] CDP connection failed ({e}), launching standalone Chromium")

        # ── Fallback: launch standalone Chromium ──────────────────────────
        launch_args = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--window-size=1440,900",
        ]

        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=launch_args,
        )

        self._context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            java_script_enabled=True,
        )

        # Inject stealth scripts to hide automation fingerprints
        await self._context.add_init_script(STEALTH_SCRIPT)
        await self._context.add_init_script(UI_OVERLAY_SCRIPT)

        # Expose Python binding for the Pause button
        async def handle_pause_event(source, is_paused: bool):
            if is_paused:
                self.pause_agent()
            else:
                self.resume_agent()
        
        try:
            await self._context.expose_binding("pantherPauseEvent", handle_pause_event)
        except Exception as e:
            logger.warning(f"[TaskDispatcher] Could not expose pantherPauseEvent binding: {e}")

        # The actual new tab will be created when a task is dispatched


    async def dispatch(
        self,
        task: str,
        context_data: Optional[dict] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Dispatch a task to BrowserSubAgent and yield SSE events.
        Each task gets a NEW TAB in the existing browser.
        """
        # Check if browser is still alive, reinitialize if stale
        if not self._browser or not await self._is_alive():
            logger.info("[TaskDispatcher] Browser not alive, (re)initializing...")
            try:
                await self.initialize()
            except Exception as init_err:
                yield {"type": "error", "message": f"Browser initialization failed: {init_err}"}
                return


        yield {"type": "plan", "message": f"🌐 Starting browser task: {task}"}

        # Add requested delay before opening the new tab
        await asyncio.sleep(2.0)

        # Always create a fresh tab for each new task
        try:
            new_page = await _pw_thread.run_coroutine_async(
                self._create_new_tab()
            )
            if new_page:
                self._page = new_page
        except Exception as e:
            logger.warning(f"[TaskDispatcher] Could not create new tab: {e}")

        # Run the sub-agent on the Playwright thread, bridging events via Queue
        event_queue: asyncio.Queue = asyncio.Queue()
        caller_loop = asyncio.get_event_loop()

        async def _run_subagent():
            try:
                from src.capabilities.extension_client import ExtensionRPCClient
                from src.capabilities.browser_subagent import BrowserSubAgent

                ext = ExtensionRPCClient(self._page)
                sub_agent = BrowserSubAgent(
                    api_key=self.api_key,
                    playwright_page=self._page,
                    extension_client=ext,
                    dispatcher=self,
                )

                async for event in sub_agent.execute_task(task, context=context_data):
                    caller_loop.call_soon_threadsafe(event_queue.put_nowait, event)

            except Exception as e:
                logger.error(f"[TaskDispatcher] Sub-agent crashed: {e}")
                caller_loop.call_soon_threadsafe(
                    event_queue.put_nowait,
                    {"type": "error", "message": f"Browser sub-agent error: {e}"},
                )
            finally:
                # ALWAYS send the sentinel so the consumer never hangs
                caller_loop.call_soon_threadsafe(event_queue.put_nowait, None)

        # Start sub-agent on the Playwright thread
        pw_loop = _pw_thread.start()
        asyncio.run_coroutine_threadsafe(_run_subagent(), pw_loop)

        # Yield events as they arrive (with timeout to prevent infinite hangs)
        while True:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=60.0)
            except asyncio.TimeoutError:
                logger.warning("[TaskDispatcher] Event queue timed out after 60s")
                yield {"type": "error", "message": "Browser agent timed out (no response for 60s)"}
                break
            if event is None:
                break
            yield event

    async def _create_new_tab(self) -> Optional[Page]:
        """Create a new tab in the browser context."""
        if self._context:
            page = await self._context.new_page()
            await page.bring_to_front()
            try:
                await page.evaluate("window.focus()")
            except Exception:
                pass
            return page
        return None

    async def close(self) -> None:
        """Clean up browser resources."""
        try:
            if self._page or self._browser or self._playwright:
                await _pw_thread.run_coroutine_async(self._close_browser())
        except Exception as e:
            logger.warning(f"[TaskDispatcher] Cleanup error: {e}")

    async def _close_browser(self) -> None:
        """Internal: close browser (runs on the Playwright thread's loop)."""
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
            # Don't close the context/browser if we connected via CDP
            # (that would close the user's browser!)
            if self._context and not self._browser:
                await self._context.close()
            if self._browser:
                # Check if this was a CDP connection — don't close user's browser
                # Playwright's CDP-connected browser has a different cleanup path
                try:
                    await self._browser.close()
                except Exception:
                    pass  # CDP connections may not support close
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"[TaskDispatcher] Close error: {e}")
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
