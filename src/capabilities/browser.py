"""Browser Controller — main entry point for browser automation.

Delegates to the DesktopBrowserSubAgent which controls the user's
ACTUAL browser (Chrome/Edge) using PyAutoGUI + Gemini visual reasoning.
"""

import os
from typing import AsyncGenerator, Optional

from loguru import logger


class BrowserController:
    """
    Thin entry point for browser automation.
    Delegates to DesktopBrowserSubAgent for real browser control.
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._agent = None

    def _get_agent(self):
        """Lazy-init the desktop browser agent."""
        if self._agent is None:
            from src.capabilities.desktop_browser_agent import DesktopBrowserSubAgent
            self._agent = DesktopBrowserSubAgent(api_key=self.api_key)
            logger.info("[BrowserController] DesktopBrowserSubAgent initialized")
        return self._agent

    async def execute_task_stream(
        self, task: str, context: Optional[dict] = None
    ) -> AsyncGenerator[dict, None]:
        """
        Execute a browser task and yield SSE progress events.
        This is called by AgentOrchestrator._handle_browser_task().
        """
        agent = self._get_agent()

        async for event in agent.execute_task(task, context=context):
            yield event
