"""Session Orchestrator — isolated browser contexts per automation task.

Each task runs in its own BrowserContext, ensuring full isolation of
cookies, localStorage, and navigation state. Sessions are automatically
cleaned up on completion or error.

Architecture reference: §11
"""

import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from loguru import logger

from src.browser.engine import BrowserEngine


class SessionOrchestrator:
    """Manage isolated browser sessions for concurrent task execution."""

    def __init__(self):
        self.active_sessions: Dict[str, BrowserEngine] = {}

    @asynccontextmanager
    async def create_session(self, config: Optional[Dict] = None):
        """Create an isolated browser session.

        Yields (session_id, BrowserEngine) and automatically cleans up
        on exit.

        Args:
            config: Optional dict with 'headless', 'stealth', 'proxy' keys
        """
        config = config or {}
        session_id = str(uuid.uuid4())
        engine = BrowserEngine()

        await engine.launch(
            headless=config.get("headless", True),
            stealth=config.get("stealth", True),
            proxy=config.get("proxy"),
        )
        self.active_sessions[session_id] = engine
        logger.info(f"[SessionOrchestrator] Session created: {session_id[:8]}…")

        try:
            yield session_id, engine
        finally:
            await engine.close()
            self.active_sessions.pop(session_id, None)
            logger.info(f"[SessionOrchestrator] Session closed: {session_id[:8]}…")

    async def run_isolated_task(
        self,
        task: str,
        ai_router,
        config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Run a browser automation task in a fully isolated session.

        Args:
            task: Natural language task description
            ai_router: AIRouter instance for LLM inference
            config: Optional browser config dict

        Returns:
            Task result dict from AutomationAgent
        """
        from src.agent.action_executor import ActionExecutor
        from src.agent.automation_agent import AutomationAgent
        from src.browser.accessibility import AccessibilityExtractor
        from src.browser.dom_interactor import DOMInteractor

        async with self.create_session(config) as (session_id, engine):
            dom = DOMInteractor(engine.page)
            ax = AccessibilityExtractor(engine.page)
            executor = ActionExecutor(engine, dom)
            agent = AutomationAgent(ai_router, engine, executor, ax)

            logger.info(
                f"[SessionOrchestrator] Running task in session {session_id[:8]}…"
            )
            return await agent.run(task)

    @property
    def session_count(self) -> int:
        """Number of currently active sessions."""
        return len(self.active_sessions)

    async def close_all(self):
        """Force-close all remaining sessions."""
        for sid, engine in list(self.active_sessions.items()):
            try:
                await engine.close()
            except Exception as exc:
                logger.warning(f"[SessionOrchestrator] Error closing {sid[:8]}: {exc}")
        self.active_sessions.clear()
