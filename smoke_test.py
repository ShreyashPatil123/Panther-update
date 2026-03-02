"""Smoke test for the integrated PANTHER browser automation architecture.

Runs a simple navigation task through the full SessionOrchestrator ->
AutomationAgent -> ActionExecutor pipeline using mocked AI providers.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from loguru import logger

from src.ai.ai_router import AIRouter, ProviderStrategy
from src.session.orchestrator import SessionOrchestrator


async def run_smoke_test():
    logger.info("Starting PANTHER Architecture Smoke Test...")

    # 1. Setup mocked AI provider (to avoid needing API keys)
    mock_provider = MagicMock()
    
    # Define a sequence of responses for the agent loop
    # Step 1: Navigate to google.com
    # Step 2: Finish
    mock_responses = [
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "I will navigate to google.",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "navigate",
                            "arguments": json.dumps({"url": "https://www.google.com"})
                        }
                    }]
                }
            }]
        },
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "I have reached google.",
                    "tool_calls": [{
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "finish",
                            "arguments": json.dumps({"result": "Reached Google successfully"})
                        }
                    }]
                }
            }]
        }
    ]
    
    # Mock the chat method to return responses in sequence
    mock_provider.chat = AsyncMock(side_effect=mock_responses)
    mock_provider.close = AsyncMock()

    # 2. Setup AI Router with the mock provider
    router = AIRouter(ollama=mock_provider, strategy=ProviderStrategy.LOCAL_FIRST)

    # 3. Use SessionOrchestrator to run a task
    orchestrator = SessionOrchestrator()
    
    try:
        logger.info("Executing task: 'Go to google.com'")
        result = await orchestrator.run_isolated_task(
            task="Go to google.com",
            ai_router=router,
            config={"headless": True}
        )
        
        logger.info(f"Task completed: {result}")
        
    finally:
        await orchestrator.close_all()
        await router.close()


if __name__ == "__main__":
    import os
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        asyncio.run(run_smoke_test())
    except KeyboardInterrupt:
        pass
