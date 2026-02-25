"""Agent Orchestrator - Central brain that coordinates all capabilities."""
import asyncio
import json
import os
import re
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger

from src.api.nvidia_client import NVIDIAClient
from src.capabilities.finance import FinanceEngine
from src.capabilities.files import FileAction, PermissionType
from src.config import Settings
from src.core.file_processor import (
    build_multimodal_content,
    classify_file,
    DEFAULT_VISION_MODEL,
    FileType,
)
from src.core.model_router import TaskCategory, get_task_preset
from src.memory.memory_system import MemorySystem


class AgentOrchestrator:
    """Central agent that coordinates all capabilities."""

    def __init__(self, config: Settings):
        """Initialize agent orchestrator.

        Args:
            config: Application settings
        """
        self.config = config
        self.nvidia_client: Optional[NVIDIAClient] = None
        self.memory = MemorySystem(
            db_path=config.db_path,
            chroma_path=config.chroma_path,
        )

        # Capabilities (initialized lazily to avoid heavy imports at startup)
        self._browser = None
        self._files = None
        self._speech = None
        self._research = None
        self._task_planner = None

        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.current_session_id = "default"

        # Smart model routing
        self.active_task_category: Optional[TaskCategory] = None
        self.task_system_prompt: Optional[str] = None

        # Provider tracking — keep original keys safe across provider switches
        self.active_provider: str = "nvidia"  # "nvidia" | "ollama" | "gemini"
        self._original_nvidia_key: Optional[str] = config.nvidia_api_key

        logger.info("Agent Orchestrator initialized")

    async def initialize(self):
        """Initialize all subsystems."""
        logger.info("Initializing agent orchestrator")
        await self.memory.initialize()

        # Initialize API client
        if self.config.ollama_enabled:
            # Use Ollama (local or cloud)
            ollama_key = getattr(self.config, "ollama_api_key", None) or "ollama"
            self.set_api_key(ollama_key, base_url=self.config.ollama_base_url, provider="ollama")
            self.config.default_model = self.config.ollama_model
            logger.info(f"Ollama mode: {self.config.ollama_base_url} / {self.config.ollama_model}")
        elif self.config.nvidia_api_key and self.config.nvidia_api_key != "your_api_key_here":
            self.set_api_key(self.config.nvidia_api_key, provider="nvidia")

        logger.info("Agent orchestrator initialized successfully")

    def set_api_key(self, api_key: str, base_url: str = None, provider: str = "nvidia"):
        """Set API key and initialize/reinitialize client.

        Args:
            api_key: API key (use 'ollama' for local Ollama).
            base_url: Optional base URL override (e.g. for Ollama/Gemini).
            provider: Provider name ('nvidia', 'ollama', 'gemini').
        """
        # Close existing client if present
        if self.nvidia_client is not None:
            try:
                asyncio.get_event_loop().create_task(self.nvidia_client.close())
            except Exception:
                pass

        self.active_provider = provider

        # Only overwrite config.nvidia_api_key if it's actually NVIDIA
        if provider == "nvidia":
            self.config.nvidia_api_key = api_key
            self._original_nvidia_key = api_key

        url = base_url or self.config.nvidia_base_url
        self.nvidia_client = NVIDIAClient(
            api_key=api_key,
            base_url=url,
        )
        logger.info(f"API client initialized: provider={provider}, base_url={url}")

    def set_task_category(self, category: Optional[TaskCategory]):
        """Switch to a task-specific model and system prompt.

        Preset models are all served by NVIDIA NIM, so this also ensures the
        provider is switched back to NVIDIA when a category is selected.

        Args:
            category: TaskCategory to activate, or None to reset to default.
        """
        if category is None:
            self.active_task_category = None
            self.task_system_prompt = None
            logger.info("Task category cleared — using default model")
            return

        preset = get_task_preset(category)
        self.active_task_category = category
        self.config.default_model = preset.model
        self.task_system_prompt = preset.system_prompt

        # Preset models live on NVIDIA NIM — switch provider if needed
        if self.active_provider != "nvidia":
            nvidia_key = self._original_nvidia_key or self.config.nvidia_api_key or ""
            if nvidia_key and nvidia_key != "your_api_key_here":
                self.set_api_key(nvidia_key, provider="nvidia")
                self.config.ollama_enabled = False
                logger.info(f"Switched provider to NVIDIA for preset '{category.value}'")

        logger.info(
            f"Task category set to {category.value} — model: {preset.model}"
        )

    @property
    def is_ready(self) -> bool:
        """Check if agent is ready to process messages."""
        return self.nvidia_client is not None

    # ─────────────────────────────────────────────────────────────────────────
    # Lazy capability accessors
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def files(self):
        """Lazy-load file system manager."""
        if self._files is None:
            from src.capabilities.files import FileSystemManager
            self._files = FileSystemManager()
            logger.info("FileSystemManager initialized")
        return self._files

    @property
    def research(self):
        """Lazy-load research engine."""
        if self._research is None:
            from src.capabilities.research import ResearchEngine
            self._research = ResearchEngine()
            logger.info("ResearchEngine initialized")
        return self._research

    @property
    def task_planner(self):
        """Lazy-load task planner."""
        if self._task_planner is None:
            from src.core.task_planner import TaskPlanner
            self._task_planner = TaskPlanner()
            logger.info("TaskPlanner initialized")
        return self._task_planner

    async def get_browser(self):
        """Lazy-initialize browser controller (async)."""
        if self._browser is None:
            from src.capabilities.browser import BrowserController

            # 3-tier Google API key resolution (same as panther_live.py)
            api_key = getattr(self.config, "google_api_key", None) or ""
            if not api_key:
                try:
                    from src.utils.secure_storage import get_google_api_key
                    api_key = get_google_api_key() or ""
                except Exception:
                    pass
            if not api_key:
                api_key = os.getenv("GOOGLE_API_KEY", "")

            if not api_key:
                logger.warning("No Google API key found for browser automation!")

            self._browser = BrowserController(api_key=api_key)
            logger.info(f"BrowserController initialized (key={'set' if api_key else 'MISSING'})")
        return self._browser

    # ─────────────────────────────────────────────────────────────────────────
    # Main message processing
    # ─────────────────────────────────────────────────────────────────────────

    async def process_message(self, message: str) -> AsyncIterator[str]:
        """Main entry point for processing user messages.

        Args:
            message: User input text

        Yields:
            Response chunks
        """
        if not self.is_ready:
            yield "Please configure your NVIDIA API key in settings first."
            return

        try:
            # Store user message
            await self.memory.add_message(
                "user",
                message,
                session_id=self.current_session_id,
            )

            # Auto-title session from first user message
            await self._auto_title_session(message)

            # Retrieve relevant semantic context
            context = await self.memory.get_relevant_context(
                message,
                limit=3,
                session_id=self.current_session_id,
            )

            # Get recent conversation history for proper multi-turn context
            history = await self._get_conversation_history(limit=10)

            # Build messages for LLM
            messages = self._build_messages(message, context, history)

            # Classify intent
            intent = await self._classify_intent(message)
            logger.info(f"Classified intent: {intent}")

            # Handle based on intent
            if intent == "file_operation":
                async for chunk in self._handle_file_operation(message, messages):
                    yield chunk
            elif intent == "browser_task":
                async for chunk in self._handle_browser_task(message, messages):
                    yield chunk
            elif intent == "finance":
                async for chunk in self._handle_finance(message, messages):
                    yield chunk
            elif intent == "research":
                async for chunk in self._handle_research(message, messages):
                    yield chunk
            else:
                async for chunk in self._handle_chat(messages):
                    yield chunk

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            error_msg = str(e)
            if "404" in error_msg:
                yield (
                    f"Model '{self.config.default_model}' was not found (404). "
                    f"Please check the model name in Settings. "
                    f"Model IDs use the format 'provider/model-name' "
                    f"(e.g. 'moonshotai/kimi-k2-thinking')."
                )
            elif "429" in error_msg or "quota" in error_msg.lower():
                yield (
                    f"⚠️ Rate limit or quota exceeded for model '{self.config.default_model}'. "
                    f"Your free tier may have reached its limit. "
                    f"Please try a different model or check your billing plan."
                )
            elif "401" in error_msg:
                yield "Invalid API key. Please update your key in Settings."
            else:
                yield f"Sorry, I encountered an error: {error_msg}"

    async def process_message_with_attachments(
        self,
        message: str,
        attachments: List[str],
    ) -> AsyncIterator[str]:
        """Process a user message with file attachments.

        Handles images (vision model), documents (text extraction),
        and videos (frame analysis) automatically.

        Args:
            message: User input text
            attachments: List of file paths

        Yields:
            Response chunks
        """
        if not self.is_ready:
            yield "Please configure your NVIDIA API key in settings first."
            return

        try:
            # Process attachments
            image_blocks, needs_vision, context_text = build_multimodal_content(
                message, attachments
            )

            # Store user message
            attachment_names = ", ".join(
                __import__("os").path.basename(f) for f in attachments
            )
            await self.memory.add_message(
                "user",
                f"{message} [Attachments: {attachment_names}]",
                session_id=self.current_session_id,
            )

            # Build the user content array (multimodal format)
            user_content: List[Dict[str, Any]] = []

            # Add context from documents/text files first
            if context_text:
                user_content.append({
                    "type": "text",
                    "text": f"The user has attached files. Here is their content:\n\n{context_text}",
                })

            # Add image blocks (for vision models)
            user_content.extend(image_blocks)

            # Add the user's question
            user_content.append({
                "type": "text",
                "text": message,
            })

            # Select model — use NVIDIA vision model only when on NVIDIA;
            # Gemini and Ollama vision-capable models handle images natively.
            if needs_vision and self.active_provider == "nvidia":
                model = DEFAULT_VISION_MODEL
                logger.info(f"Auto-switching to NVIDIA vision model: {model}")
            else:
                model = self.config.default_model

            # Build messages list
            system_prompt = self.task_system_prompt or (
                "You are a helpful AI assistant with the ability to analyze "
                "attached files including images, documents, and videos. "
                "Provide thorough, detailed analysis when files are attached. "
                "Use markdown formatting for clarity."
            )

            messages: List[Dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

            # Vision models on NVIDIA NIM cap max_tokens at 1024
            # and sometimes reject streaming for multimodal payloads.
            if needs_vision:
                max_tokens = 1024
                use_stream = True  # try streaming first
            else:
                max_tokens = 4096
                use_stream = True

            # Stream response
            full_response = ""
            try:
                async for chunk in self.nvidia_client.chat_completion(
                    messages,
                    model=model,
                    max_tokens=max_tokens,
                    stream=use_stream,
                ):
                    full_response += chunk
                    yield chunk
            except Exception as vision_err:
                if needs_vision and use_stream:
                    # Retry without streaming (some vision endpoints reject SSE)
                    logger.warning(
                        f"Streaming failed for vision model, retrying "
                        f"non-streaming: {vision_err}"
                    )
                    full_response = ""
                    async for chunk in self.nvidia_client.chat_completion(
                        messages,
                        model=model,
                        max_tokens=max_tokens,
                        stream=False,
                    ):
                        full_response += chunk
                        yield chunk
                else:
                    raise

            await self.memory.add_message(
                "assistant",
                full_response,
                session_id=self.current_session_id,
            )

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            yield f"Sorry, I encountered an error: {str(e)}"

    async def process_message_with_screen(
        self,
        message: str,
        screen_b64: str,
    ) -> AsyncIterator[str]:
        """Process a message with a screen capture screenshot as context.

        The screenshot is sent as a base64 image to a vision model, identical
        to the file attachment flow but with a screen context label.

        Args:
            message: User input text
            screen_b64: Base64-encoded JPEG screenshot

        Yields:
            Response chunks
        """
        if not self.is_ready:
            yield "Please configure your NVIDIA API key in settings first."
            return

        try:
            # Store user message
            await self.memory.add_message(
                "user",
                f"{message} [Screen context included]",
                session_id=self.current_session_id,
            )

            # Build multimodal content with screen image
            user_content: List[Dict[str, Any]] = [
                {
                    "type": "text",
                    "text": (
                        "[Screen Context \u2014 captured while app was in background]\n"
                        "The following image is a screenshot of the user's screen."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{screen_b64}",
                    },
                },
                {
                    "type": "text",
                    "text": message,
                },
            ]

            if self.active_provider == "nvidia":
                model = DEFAULT_VISION_MODEL
            else:
                model = self.config.default_model
            logger.info(f"Processing screen context with vision model: {model}")

            system_prompt = self.task_system_prompt or (
                "You are a helpful AI assistant that can see the user's screen. "
                "The user has shared a screenshot of their screen with you. "
                "Describe what you see, answer their question about the screen content, "
                "or help them with the task they're working on. "
                "Use markdown formatting for clarity."
            )

            messages: List[Dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

            full_response = ""
            try:
                async for chunk in self.nvidia_client.chat_completion(
                    messages,
                    model=model,
                    max_tokens=1024,
                    stream=True,
                ):
                    full_response += chunk
                    yield chunk
            except Exception as vision_err:
                # Retry without streaming (some vision endpoints reject SSE)
                logger.warning(
                    f"Streaming failed for vision model, retrying "
                    f"non-streaming: {vision_err}"
                )
                full_response = ""
                async for chunk in self.nvidia_client.chat_completion(
                    messages,
                    model=model,
                    max_tokens=1024,
                    stream=False,
                ):
                    full_response += chunk
                    yield chunk

            await self.memory.add_message(
                "assistant",
                full_response,
                session_id=self.current_session_id,
            )

        except Exception as e:
            logger.error(f"Error processing screen context: {e}")
            yield f"Sorry, I encountered an error analyzing the screen: {str(e)}"

    async def extract_text_from_screen(self, screen_b64: str) -> Optional[str]:
        """OCR: Extract visible text from a screenshot via NVIDIA NIM vision model.

        Sends the screenshot to the vision model with an OCR-focused prompt.
        Used by the Gemini Live OCR loop to get text context for voice sessions.

        Args:
            screen_b64: Base64-encoded JPEG screenshot

        Returns:
            Extracted text or None if failed/empty
        """
        if not self.is_ready:
            return None

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": "You are an OCR assistant. Extract text only.",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{screen_b64}",
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Read and extract all visible text from this screen. "
                            "Preserve structure, layout, and hierarchy. "
                            "Return only the extracted content, nothing else."
                        ),
                    },
                ],
            },
        ]

        try:
            full_response = ""
            ocr_model = DEFAULT_VISION_MODEL if self.active_provider == "nvidia" else self.config.default_model
            async for chunk in self.nvidia_client.chat_completion(
                messages,
                model=ocr_model,
                max_tokens=2048,
                stream=False,
            ):
                full_response += chunk

            text = full_response.strip()
            if not text:
                return None

            # Truncate if too long to avoid overwhelming Gemini context
            if len(text) > 4000:
                text = text[:4000]

            return text

        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return None

    async def _get_conversation_history(self, limit: int = 10) -> List[Dict[str, str]]:
        """Get recent conversation history as LLM messages.

        Args:
            limit: Max number of messages to retrieve

        Returns:
            List of {role, content} dicts
        """
        recent = await self.memory.get_recent_messages(
            limit=limit,
            session_id=self.current_session_id,
        )
        # Filter to just role + content for LLM
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in recent
            if msg.get("role") in ("user", "assistant")
        ]

    async def _classify_intent(self, message: str) -> str:
        """Classify user intent using keyword fast-path + LLM fallback.

        Two-tier approach:
          1. Keywords catch obvious file/browser operations instantly.
          2. For everything else, the LLM decides if the query needs
             live internet data (research) or can be answered from
             training knowledge (chat).

        Args:
            message: User message

        Returns:
            Intent string: 'file_operation' | 'browser_task' | 'finance' | 'research' | 'chat'
        """
        message_lower = message.lower()

        # ── Tier 1: keyword fast-path for unambiguous intents ─────────────
        file_keywords = [
            "open file", "read file", "write file", "save file", "delete file",
            "create file", "edit file", "list files", "list folder", "show files",
            "directory", "folder contents", "file system", "read the file",
            "open the file", "show me the file", "what's in", "contents of",
        ]
        browser_keywords = [
            "browse", "open browser", "navigate to", "go to website", "go to http",
            "search the web", "search online", "look up online", "open a tab",
            "visit the site", "click on", "take a screenshot", "web search",
            "search google", "search bing",
            # ── Common site-specific phrases ──
            "go to youtube", "go to google", "go to github", "go to reddit",
            "go to twitter", "go to facebook", "go to instagram", "go to linkedin",
            "go to amazon", "go to flipkart", "go to wikipedia", "go to stackoverflow",
            "open youtube", "open google", "open github", "open reddit",
            "open twitter", "open amazon", "open flipkart", "open wikipedia",
            # ── Action-based phrases ──
            "search on youtube", "search on google", "search youtube", "search on",
            "fill the form", "fill out the form", "fill form", "submit the form",
            "automate", "scrape", "extract from website", "extract from page",
            "open the website", "open the page", "open the site", "open a website",
            "visit", "go to the",
        ]

        # ── Regex: detect URLs and "go to <site>" patterns ────────────────
        url_pattern = re.compile(
            r'(?:go to|open|visit|navigate to|check)\s+'
            r'(?:https?://)?(?:www\.)?[a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z]{2,}',
            re.IGNORECASE,
        )
        has_url = bool(re.search(r'https?://|www\.|\.com|\.org|\.net|\.io|\.in|\.co', message_lower))

        finance_keywords = [
            "stock price", "share price", "stock market", "market price",
            "gold price", "gold rate", "silver price", "silver rate",
            "bitcoin price", "btc price", "crypto price", "ethereum price",
            "forex rate", "exchange rate", "dollar rate", "usd inr",
            "nifty", "sensex", "dow jones", "nasdaq", "s&p 500",
            "crude oil price", "oil price", "commodity price",
            "24 karat", "22 karat", "24k gold", "22k gold",
        ]
        chat_keywords = [
            "hi", "hello", "hey", "thanks", "thank you", "how are you",
            "who are you", "what is your name", "good morning", "good evening",
            "good night", "bye", "goodbye", "ok", "okay", "cool", "nice",
        ]

        # ── Tier 1: keyword fast-path for unambiguous intents ─────────────
        if any(kw in message_lower for kw in file_keywords):
            return "file_operation"
        if any(kw in message_lower for kw in browser_keywords):
            return "browser_task"
        if url_pattern.search(message) or has_url:
            return "browser_task"
        if any(kw in message_lower for kw in finance_keywords):
            return "finance"
        if any(kw in message_lower for kw in chat_keywords):
            return "chat"

        # ── Tier 1.5: Length-based fast-path ──────────────────────────────
        # Short phrases (under 3 words) that didn't match specific command
        # keywords are almost certainly conversational.
        words = message.split()
        if len(words) <= 3 and len(words) > 0:
            return "chat"

        # ── Tier 2: LLM-powered classification ────────────────────────────
        # The LLM is far better at recognizing when a question needs live
        # internet data (prices, weather, news, scores, current events)
        # vs. a simple conversational reply.
        try:
            return await self._llm_classify_intent(message)
        except Exception as e:
            logger.warning(f"LLM intent classification failed, using keyword fallback: {e}")

        # ── Tier 3: keyword fallback for research (if LLM fails) ──────────
        research_keywords = [
            "research", "investigate", "find information about", "look up",
            "search for information", "deep dive", "comprehensive overview",
            "find out about", "gather information",
        ]
        if any(kw in message_lower for kw in research_keywords):
            return "research"

        return "chat"

    async def _llm_classify_intent(self, message: str) -> str:
        """Use the LLM to classify intent including browser automation.

        Args:
            message: User message

        Returns:
            'browser_task', 'finance', 'research', or 'chat'
        """
        now = datetime.now().strftime("%B %d, %Y %I:%M %p")

        classification_prompt = [
            {
                "role": "system",
                "content": (
                    f"You are an intent classifier. The current date and time is: {now}.\n\n"
                    "Your ONLY job is to decide the correct intent for the user's message.\n\n"
                    "Return EXACTLY one word — 'browser', 'finance', 'research', or 'chat'.\n\n"
                    "Return 'browser' if the user wants ANY of these:\n"
                    "- Open, visit, go to, or navigate to a website or URL\n"
                    "- Search on a specific website (YouTube, Google, Amazon, etc.)\n"
                    "- Click, scroll, fill forms, or interact with a web page\n"
                    "- Take a screenshot of a website\n"
                    "- Scrape, extract, or automate anything on a website\n"
                    "- Any task that requires controlling a real web browser\n\n"
                    "Return 'finance' if the query asks about ANY of these:\n"
                    "- Stock prices (Apple, Tesla, Reliance, any company)\n"
                    "- Cryptocurrency prices (Bitcoin, Ethereum, Solana, any coin)\n"
                    "- Gold, silver, platinum, or commodity prices\n"
                    "- Forex rates (USD/INR, EUR/USD, dollar rate)\n"
                    "- Stock market indices (Nifty, Sensex, Dow Jones, NASDAQ, S&P)\n"
                    "- Crude oil, natural gas prices\n"
                    "- Any query about market data, share price, stock quote\n\n"
                    "Return 'research' if the query asks about ANY of these:\n"
                    "- Current weather or forecasts\n"
                    "- Recent or breaking news\n"
                    "- Sports scores or live results\n"
                    "- Current events, elections, politics\n"
                    "- Product availability, reviews, or comparisons\n"
                    "- Any factual question where the answer changes over time\n\n"
                    "Return 'chat' if the query is:\n"
                    "- A greeting or casual conversation\n"
                    "- A coding or technical question\n"
                    "- A creative writing request\n"
                    "- A math or logic problem\n"
                    "- A question about timeless general knowledge\n"
                    "- An opinion or advice request\n\n"
                    "Respond with ONLY the single word 'browser', 'finance', 'research', or 'chat'. Nothing else."
                ),
            },
            {
                "role": "user",
                "content": message,
            },
        ]

        # Use a lightning-fast 8B model for classification to minimize latency
        fast_model = self.config.default_model
        if self.active_provider == "nvidia":
            fast_model = "meta/llama-3.1-8b-instruct"

        result = ""
        async for chunk in self.nvidia_client.chat_completion(
            classification_prompt,
            model=fast_model,
            stream=False,
            max_tokens=8,
            temperature=0.0,
        ):
            result += chunk

        intent = result.strip().lower().rstrip(".")

        # Map 'browser' to internal 'browser_task' intent name
        if intent == "browser":
            logger.info(f"LLM classified intent as 'browser_task' for: {message[:60]}")
            return "browser_task"

        if intent in ("finance", "research", "chat"):
            logger.info(f"LLM classified intent as '{intent}' for: {message[:60]}")
            return intent

        # If LLM returns something unexpected, default to research for safety
        logger.warning(f"LLM returned unexpected intent '{result}', defaulting to 'research'")
        return "research"

    def _build_messages(
        self,
        message: str,
        context: List[Dict[str, Any]],
        history: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """Build message list with system prompt, context, and history.

        Args:
            message: Current user message
            context: Relevant semantic context from memory
            history: Recent conversation history

        Returns:
            List of messages for LLM
        """
        now = datetime.now().strftime("%B %d, %Y %I:%M %p")
        system_prompt = f"""You are an intelligent AI assistant powered by NVIDIA NIM.
The current date and time is: {now}.

You have the following capabilities:
- Access to files and folders (with permission)
- Browser automation for web tasks
- Deep research with source verification
- Long-term memory of conversations and tasks

Guidelines:
- Be helpful, concise, and proactive
- When performing actions, explain what you're doing step by step
- Ask for clarification when needed
- Always prioritize user privacy and security
- Format responses with markdown when helpful"""

        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

        # Add semantic context if relevant (deduplicate with history)
        if context:
            history_contents = {h.get("content", "") for h in history}
            extra_context = [
                c for c in context
                if isinstance(c, dict) and c.get("content", "") not in history_contents
            ]
            if extra_context:
                ctx_text = "Relevant context from memory:\n"
                for ctx in extra_context[:3]:
                    role = ctx.get("role", "unknown")
                    content = ctx.get("content", "")
                    ctx_text += f"[{role}]: {content}\n"
                messages.append({"role": "system", "content": ctx_text})

        # Add recent conversation history (excludes the current message which is in history)
        for msg in history:
            if msg.get("content") != message:  # avoid duplicate of current message
                messages.append(msg)

        # Add current user message
        messages.append({"role": "user", "content": message})

        return messages

    # ─────────────────────────────────────────────────────────────────────────
    # Intent handlers
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_chat(self, messages: List[Dict[str, str]]) -> AsyncIterator[str]:
        """Handle standard chat interaction."""
        # Inject task-specific system prompt if active
        if self.task_system_prompt:
            system_msg = {"role": "system", "content": self.task_system_prompt}
            # Prepend system message (or replace existing system message)
            if messages and messages[0].get("role") == "system":
                messages = [system_msg] + messages[1:]
            else:
                messages = [system_msg] + messages

        full_response = ""
        try:
            async for chunk in self.nvidia_client.chat_completion(
                messages,
                model=self.config.default_model,
            ):
                full_response += chunk
                yield chunk

            await self.memory.add_message(
                "assistant",
                full_response,
                session_id=self.current_session_id,
            )
        except Exception as e:
            logger.error(f"Error in chat completion: {e}")
            raise

    async def _handle_file_operation(
        self,
        message: str,
        messages: List[Dict[str, str]],
    ) -> AsyncIterator[str]:
        """Handle file system operations using LLM to parse intent."""
        yield "Analyzing file operation request...\n\n"

        # Ask LLM for a structured action plan
        plan_messages = messages + [
            {
                "role": "system",
                "content": (
                    "The user wants a file operation. Respond with ONLY a JSON object "
                    "(no markdown, no explanation) with these fields:\n"
                    '{"action": "read|write|list|search|delete", '
                    '"path": "relative or absolute path", '
                    '"content": "content if writing (optional)", '
                    '"pattern": "glob pattern if searching (optional)"}\n'
                    "Use relative paths when possible. Default to current directory."
                ),
            },
        ]

        plan_json = ""
        try:
            async for chunk in self.nvidia_client.chat_completion(
                plan_messages, model=self.config.default_model,
                stream=False, max_tokens=256, temperature=0.1,
            ):
                plan_json = chunk
        except Exception as e:
            logger.error(f"LLM file planning failed: {e}")
            yield "I couldn't plan the file operation. Let me answer your question instead.\n\n"
            async for chunk in self._handle_chat(messages):
                yield chunk
            return

        # Parse JSON plan
        action_plan = self._parse_json_response(plan_json)
        if not action_plan or "action" not in action_plan:
            yield "I couldn't determine the file operation. Let me answer your question instead.\n\n"
            async for chunk in self._handle_chat(messages):
                yield chunk
            return

        action = action_plan.get("action", "").lower()
        path = action_plan.get("path", ".")
        content = action_plan.get("content", "")
        pattern = action_plan.get("pattern", "*")

        yield f"**Action**: `{action}` on `{path}`\n\n"

        # Execute file operation
        result_text = ""
        try:
            fs = self.files

            if action == "read":
                # Request permission if needed
                if not fs.check_permission(path, FileAction.READ):
                    await fs.request_permission(path, PermissionType.READ, recursive=True)
                file_content = await fs.read_file(path)
                result_text = f"**File content of `{path}`:**\n\n```\n{file_content[:3000]}\n```"
                if len(file_content) > 3000:
                    result_text += f"\n\n*(truncated — file has {len(file_content)} chars total)*"

            elif action == "list":
                if not fs.check_permission(path, FileAction.READ):
                    await fs.request_permission(path, PermissionType.READ, recursive=True)
                file_infos = await fs.list_directory(path)
                lines = [f"**Contents of `{path}`:**\n"]
                for fi in file_infos[:50]:
                    icon = "📁" if fi.is_directory else "📄"
                    size = f" ({fi.size:,} bytes)" if not fi.is_directory else ""
                    lines.append(f"{icon} `{fi.name}`{size}")
                if len(file_infos) > 50:
                    lines.append(f"\n*(and {len(file_infos) - 50} more)*")
                result_text = "\n".join(lines)

            elif action == "search":
                if not fs.check_permission(path, FileAction.READ):
                    await fs.request_permission(path, PermissionType.READ, recursive=True)
                found = await fs.search_files(pattern, path)
                lines = [f"**Search results for `{pattern}` in `{path}`:**\n"]
                for f_path in found[:30]:
                    lines.append(f"- `{f_path}`")
                if len(found) > 30:
                    lines.append(f"*(and {len(found) - 30} more)*")
                result_text = "\n".join(lines)

            elif action == "write":
                if not fs.check_permission(path, FileAction.WRITE):
                    await fs.request_permission(path, PermissionType.WRITE, recursive=True)
                await fs.write_file(path, content)
                result_text = f"✅ Successfully wrote to `{path}`"

            elif action == "delete":
                if not fs.check_permission(path, FileAction.DELETE):
                    yield (
                        f"⚠️ Permission required to delete `{path}`. "
                        "Please grant write access in the Files panel.\n"
                    )
                    return
                await fs.delete_file(path)
                result_text = f"✅ Deleted `{path}`"

            else:
                result_text = f"Unknown action: {action}"

        except PermissionError as e:
            result_text = (
                f"⚠️ **Permission denied**: {e}\n\n"
                "Please grant access to this path in the Files panel (sidebar → Files → Add Folder)."
            )
        except FileNotFoundError as e:
            result_text = f"❌ **File not found**: {e}"
        except Exception as e:
            logger.error(f"File operation error: {e}")
            result_text = f"❌ **Error**: {str(e)}"

        yield result_text + "\n\n"

        # Store result in memory
        await self.memory.add_message(
            "assistant",
            result_text,
            session_id=self.current_session_id,
        )

        # If reading, offer LLM analysis
        if action == "read" and result_text and "File content" in result_text:
            yield "---\n\n**Analysis:**\n"
            analysis_messages = messages + [
                {
                    "role": "assistant",
                    "content": result_text,
                },
                {
                    "role": "user",
                    "content": "Please provide a brief summary or analysis of this file content.",
                },
            ]
            async for chunk in self.nvidia_client.chat_completion(
                analysis_messages, model=self.config.default_model,
                max_tokens=512,
            ):
                yield chunk

    async def _handle_browser_task(
        self,
        message: str,
        messages: List[Dict[str, str]],
    ) -> AsyncIterator[str]:
        """Handle browser automation tasks via BrowserSubAgent."""
        yield "🌐 Launching browser agent...\n\n"

        try:
            browser = await self.get_browser()

            result_text = ""
            async for event in browser.execute_task_stream(message):
                event_type = event.get("type")

                if event_type == "plan":
                    yield f"📋 {event.get('message', '')}\n\n"

                elif event_type == "action":
                    yield f"{event.get('message', '')}\n"

                elif event_type == "result":
                    data = event.get("data", {})
                    result_text = data.get("result", "Task completed.")
                    steps = data.get("steps_taken", 0)
                    final_url = data.get("final_url", "")

                    yield f"\n---\n\n"
                    yield f"✅ **Browser task complete** ({steps} steps)\n\n"
                    if final_url:
                        yield f"**Final URL:** `{final_url}`\n\n"
                    yield f"**Result:**\n{result_text}\n"

                elif event_type == "error":
                    error_msg = event.get("message", "Unknown error")
                    yield f"\n❌ **Browser error:** {error_msg}\n\n"
                    yield "Let me provide a text-based answer instead:\n\n"
                    async for chunk in self._handle_chat(messages):
                        yield chunk
                    return

            # Store result in memory
            if result_text:
                await self.memory.add_message(
                    "assistant",
                    result_text,
                    session_id=self.current_session_id,
                )

        except Exception as e:
            logger.error(f"Browser task failed: {e}")
            yield f"❌ Browser initialization failed: {e}\n\n"
            yield "Let me provide a text-based answer instead:\n\n"
            async for chunk in self._handle_chat(messages):
                yield chunk

    async def _handle_research(
        self,
        message: str,
        messages: List[Dict[str, str]],
    ) -> AsyncIterator[str]:
        """Handle deep research tasks."""
        yield f"🔍 Starting research on: **{message}**\n\n"
        yield "Searching the web...\n"

        try:
            result = await self.research.deep_research(
                message,
                nvidia_client=self.nvidia_client,
                max_sources=5,
                model=self.config.default_model,
            )

            yield f"\n✅ Found **{len(result.sources)}** sources\n\n"

            # Show sources
            if result.sources:
                yield "**Sources consulted:**\n"
                for i, src in enumerate(result.sources, 1):
                    yield f"{i}. [{src.title}]({src.url})\n"
                yield "\n---\n\n"

            # Show synthesized answer
            if result.synthesized_answer:
                yield "**Research Summary:**\n\n"
                yield result.synthesized_answer
            else:
                yield "No synthesis available — showing raw snippets:\n\n"
                for src in result.sources:
                    yield f"**{src.title}**\n{src.snippet}\n\n"

            # Store in memory
            summary = self.research.format_result_for_display(result)
            await self.memory.add_message(
                "assistant",
                summary,
                session_id=self.current_session_id,
            )

        except Exception as e:
            logger.error(f"Research error: {e}")
            yield f"❌ Research failed: {e}\n\nLet me answer from my knowledge instead:\n\n"
            async for chunk in self._handle_chat(messages):
                yield chunk

    async def _handle_finance(
        self,
        message: str,
        messages: List[Dict[str, str]],
    ) -> AsyncIterator[str]:
        """Handle financial market data queries via Twelve Data API."""
        yield f"📈 Fetching live market data...\n\n"

        try:
            engine = FinanceEngine()
            quote, text = await engine.get_quote(
                message,
                nvidia_client=self.nvidia_client,
                model=self.config.default_model,
            )
            await engine.close()

            if quote:
                yield text
            else:
                # text contains the error message
                yield text
                yield "\n\nLet me try a general web search instead...\n\n"
                async for chunk in self._handle_research(message, messages):
                    yield chunk
                return

            # Store in memory
            await self.memory.add_message(
                "assistant",
                text,
                session_id=self.current_session_id,
            )

        except Exception as e:
            logger.error(f"Finance query error: {e}")
            yield f"❌ Market data fetch failed: {e}\n\n"
            yield "Falling back to web search...\n\n"
            async for chunk in self._handle_research(message, messages):
                yield chunk

    # ─────────────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────────────

    def _parse_json_response(self, text: str) -> Optional[Dict]:
        """Extract and parse JSON from LLM response.

        Handles responses that may have markdown code blocks or extra text.
        """
        if not text:
            return None

        # Try direct parse first
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Extract from markdown code block
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Extract bare JSON object
        match = re.search(r"\{[\s\S]+\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning(f"Failed to parse JSON from: {text[:200]}")
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Session management
    # ─────────────────────────────────────────────────────────────────────────

    async def set_session(self, session_id: str):
        """Switch to a different session."""
        self.current_session_id = session_id
        await self.memory.create_session(session_id)
        logger.info(f"Switched to session: {session_id}")

    async def new_session(self) -> str:
        """Create a new session and return its ID."""
        import uuid
        session_id = str(uuid.uuid4())
        await self.memory.create_session(session_id)
        self.current_session_id = session_id
        logger.info(f"Created new session: {session_id}")
        return session_id

    async def _auto_title_session(self, message: str):
        """Auto-generate a session title from the first user message.

        Only titles sessions that still have the default 'Session xxxx' name.
        Uses the LLM to generate a concise, descriptive title.
        """
        try:
            sessions = await self.memory.get_sessions(limit=50)
            current = next(
                (s for s in sessions if s["id"] == self.current_session_id), None
            )
            if not current:
                return
            title = current.get("title", "")
            # Only auto-title if still using default name
            if title and not title.startswith("Session "):
                return

            # Ask LLM to generate a short descriptive title
            system_prompt = (
                "You are a chat title generator. Analyze the user's message.\n\n"
                "Rules:\n"
                "- Output ONLY a 3-5 word title.\n"
                "- Make it short, descriptive, and engaging.\n"
                "- Extract the core topic, action, or question.\n"
                "- Use Title Case.\n"
                "- Do NOT use quotation marks or punctuation at the end.\n"
            )
            
            try:
                result = ""
                async for chunk in self.nvidia_client.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                    model=self.config.default_model,
                    stream=False,
                    max_tokens=15,
                    temperature=0.3,
                ):
                    result += chunk
                
                short_title = result.strip().strip('"\'').rstrip('.')
            except Exception as llm_err:
                logger.warning(f"LLM auto-title failed, falling back to substring: {llm_err}")
                # Fallback to simple substring
                short_title = message.strip()
                if len(short_title) > 40:
                    short_title = short_title[:40].rsplit(" ", 1)[0] + "…"

            if short_title:
                await self.memory.update_session_title(
                    self.current_session_id, short_title
                )
        except Exception as e:
            logger.debug(f"Auto-title failed (non-critical): {e}")

    async def get_sessions(self) -> List[Dict[str, Any]]:
        """Get list of sessions."""
        return await self.memory.get_sessions()

    async def clear_current_session(self):
        """Clear the current session."""
        await self.memory.clear_session(self.current_session_id)
        logger.info(f"Cleared current session: {self.current_session_id}")

    async def validate_api_key(self, api_key: str) -> bool:
        """Validate an API key."""
        client = NVIDIAClient(
            api_key=api_key,
            base_url=self.config.nvidia_base_url,
        )
        try:
            is_valid = await client.validate_api_key()
            await client.close()
            return is_valid
        except Exception:
            return False

    async def close(self):
        """Cleanup and close all resources."""
        logger.info("Closing agent orchestrator")

        for task in self.active_tasks.values():
            task.cancel()

        await self.memory.close()

        if self.nvidia_client:
            await self.nvidia_client.close()

        if self._browser:
            await self._browser.shutdown()

        if self._research:
            await self._research.close()

        logger.info("Agent orchestrator closed")
