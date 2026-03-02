"""Automation Agent — multi-step planning loop with observation-driven feedback.

The core agent that translates natural language tasks into browser
actions through an LLM-driven loop:

    Task → DOM Analysis → LLM Decision → Action Execution → Observation → Repeat

Architecture reference: §7.3
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


# Load tool definitions from the JSON schema
_SCHEMA_PATH = Path(__file__).parent / "action_schema.json"


def _load_tool_definitions() -> List[Dict]:
    """Load and return the action schema from action_schema.json."""
    try:
        with open(_SCHEMA_PATH, "r") as f:
            return json.load(f)["tools"]
    except Exception as exc:
        logger.error(f"[AutomationAgent] Failed to load action schema: {exc}")
        return []


class AutomationAgent:
    """Multi-step browser automation agent driven by LLM reasoning.

    Runs an observe-plan-act loop up to MAX_STEPS, feeding DOM state
    and action observations back into the LLM context window.
    """

    MAX_STEPS = 30

    SYSTEM_PROMPT = """\
You are a browser automation agent. You will be given a task and the current state of a browser.
Your job is to select and execute browser actions step-by-step until the task is complete.

Rules:
- Always analyze the current DOM or screenshot before acting
- Prefer CSS selectors from the accessibility tree over XPath
- If an action fails, try an alternative approach
- Use 'finish' when the task is fully complete
- Never loop on the same action more than 3 times
"""

    def __init__(self, ai_router, browser, action_executor, accessibility_extractor=None):
        """Initialise the automation agent.

        Args:
            ai_router: AIRouter instance for LLM inference
            browser: BrowserEngine instance
            action_executor: ActionExecutor instance
            accessibility_extractor: Optional AccessibilityExtractor instance
        """
        self.ai = ai_router
        self.browser = browser
        self.executor = action_executor
        self.accessibility = accessibility_extractor
        self.history: List[Dict[str, Any]] = []
        self._tool_definitions = _load_tool_definitions()

    async def run(self, task: str) -> Dict[str, Any]:
        """Run the automation loop for a given task.

        Args:
            task: Natural language description of the task

        Returns:
            Dict with 'success', 'result', 'data', and 'steps' keys
        """
        # Initialise conversation history
        self.history = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"TASK: {task}"},
        ]

        for step in range(self.MAX_STEPS):
            logger.info(f"[AutomationAgent] Step {step + 1}/{self.MAX_STEPS}")

            # ── 1. Capture current browser state ─────────────────────
            dom_text = ""
            if self.accessibility:
                try:
                    dom_text = await self.accessibility.get_labeled_dom()
                except Exception as exc:
                    logger.warning(f"[AutomationAgent] DOM extraction failed: {exc}")
                    dom_text = "(DOM extraction unavailable)"

            url = self.browser.url

            state_message = (
                f"Step {step + 1}/{self.MAX_STEPS}\n"
                f"Current URL: {url}\n"
                f"Current Page Elements:\n{dom_text}\n\n"
                f"Select the next action to take."
            )
            self.history.append({"role": "user", "content": state_message})

            # ── 2. Get AI decision ───────────────────────────────────
            try:
                response = await self.ai.route(
                    messages=self.history,
                    tools=self._tool_definitions,
                )
            except Exception as exc:
                logger.error(f"[AutomationAgent] AI request failed: {exc}")
                return {
                    "success": False,
                    "result": f"AI request failed: {exc}",
                    "steps": step + 1,
                }

            # ── 3. Parse tool call from response ─────────────────────
            choice = response.get("choices", [{}])[0].get("message", {})
            self.history.append({
                "role": "assistant",
                "content": choice.get("content", ""),
            })

            tool_calls = choice.get("tool_calls", [])
            if not tool_calls:
                # Model returned text instead of a tool call — re-prompt
                logger.debug("[AutomationAgent] No tool call in response, re-prompting")
                continue

            tool_call = tool_calls[0]
            func = tool_call.get("function", {})
            action_name = func.get("name", "")

            try:
                params = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                params = {}
                logger.warning("[AutomationAgent] Failed to parse tool call arguments")

            # ── 4. Execute the action ────────────────────────────────
            logger.info(
                f"[AutomationAgent] Action: {action_name}({json.dumps(params, ensure_ascii=False)[:120]})"
            )
            result = await self.executor.execute(action_name, params)

            # ── 5. Build observation and append to history ───────────
            observation = (
                f"Action '{action_name}' → "
                f"{'SUCCESS' if result.success else 'FAILED'}: "
                f"{result.observation}"
            )
            if result.error:
                observation += f"\nError: {result.error}"

            self.history.append({
                "role": "tool",
                "tool_call_id": tool_call.get("id", f"call_{step}"),
                "content": observation,
            })

            # ── 6. Check for task completion ─────────────────────────
            if action_name == "finish":
                logger.info("[AutomationAgent] Task completed successfully")
                return {
                    "success": True,
                    "result": result.observation,
                    "data": result.data,
                    "steps": step + 1,
                }

        # Max steps reached
        logger.warning("[AutomationAgent] Max steps reached without completion")
        return {
            "success": False,
            "result": "Max steps reached",
            "steps": self.MAX_STEPS,
        }
