"""Interactive PANTHER Browser Agent.

Use this script to test the new browser automation architecture with real LLMs.
Requires either Ollama running locally or an NVIDIA_API_KEY in .env.

Usage:
    python interactive_panther.py "Search for latest AI news on Google"
"""

import asyncio
import os
import sys
from loguru import logger
from dotenv import load_dotenv

from src.config import load_config
from src.ai.ai_router import AIRouter, ProviderStrategy
from src.ai.ollama_provider import OllamaProvider
from src.ai.nim_provider import NIMProvider
from src.session.orchestrator import SessionOrchestrator


async def main():
    load_dotenv()
    config = load_config()
    
    # Get task from command line or prompt
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = input("\n[PANTHER] What browser task should I perform? > ")

    if not task:
        print("No task provided. Exiting.")
        return

    logger.info(f"Initializing PANTHER Architecture for task: '{task}'")

    # 1. Setup AI Providers
    ollama = None
    if config.ollama_enabled:
        ollama = OllamaProvider(
            base_url=config.ollama_base_url,
            model=config.ollama_model
        )
        logger.info(f"Ollama provider active: {config.ollama_model}")

    nim = None
    if config.nvidia_api_key and config.nvidia_api_key != "your_api_key_here":
        nim = NIMProvider(
            api_key=config.nvidia_api_key
        )
        logger.info("NVIDIA NIM provider active")

    if not ollama and not nim:
        logger.error("No AI providers configured! Please set NVIDIA_API_KEY or enable OLLAMA in .env")
        return

    # 2. Setup AI Router
    router = AIRouter(
        ollama=ollama,
        nim=nim,
        strategy=ProviderStrategy.LOCAL_FIRST if ollama else ProviderStrategy.PERFORMANCE
    )

    # 3. Use SessionOrchestrator to run the task
    orchestrator = SessionOrchestrator()
    
    print(f"\n[PANTHER] 🌐 Starting automation: '{task}'...")
    print("[PANTHER] (Press Ctrl+C to abort if it gets stuck)\n")

    try:
        result = await orchestrator.run_isolated_task(
            task=task,
            ai_router=router,
            config={
                "headless": config.browser_headless,
                "stealth": config.browser_stealth
            }
        )
        
        print(f"\n[PANTHER] ✅ Task Completed!")
        print(f"[PANTHER] Result: {result}\n")
        
    except KeyboardInterrupt:
        print("\n[PANTHER] 🛑 Task aborted by user.")
    except Exception as e:
        logger.exception(f"Task failed: {e}")
        print(f"\n[PANTHER] ❌ Error: {e}")
    finally:
        await orchestrator.close_all()
        await router.close()


if __name__ == "__main__":
    # Fix for Windows loop policy
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
