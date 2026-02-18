"""Agent Orchestrator - Central brain that coordinates all capabilities."""
import asyncio
import json
import re
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger

from src.api.nvidia_client import NVIDIAClient
from src.capabilities.files import FileAction, PermissionType
from src.config import Settings
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

        logger.info("Agent Orchestrator initialized")

    async def initialize(self):
        """Initialize all subsystems."""
        logger.info("Initializing agent orchestrator")
        await self.memory.initialize()

        # Initialize API client if key is available
        if self.config.nvidia_api_key:
            self.set_api_key(self.config.nvidia_api_key)

        logger.info("Agent orchestrator initialized successfully")

    def set_api_key(self, api_key: str):
        """Set NVIDIA API key and initialize client."""
        self.nvidia_client = NVIDIAClient(
            api_key=api_key,
            base_url=self.config.nvidia_base_url,
        )
        logger.info("NVIDIA API client initialized")

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
            self._browser = BrowserController()
            await self._browser.initialize()
            logger.info("BrowserController initialized")
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
            elif intent == "research":
                async for chunk in self._handle_research(message, messages):
                    yield chunk
            else:
                async for chunk in self._handle_chat(messages):
                    yield chunk

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            yield f"Sorry, I encountered an error: {str(e)}"

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
        """Classify user intent.

        Args:
            message: User message

        Returns:
            Intent string: 'file_operation' | 'browser_task' | 'research' | 'chat'
        """
        message_lower = message.lower()

        # File operation indicators
        file_keywords = [
            "open file", "read file", "write file", "save file", "delete file",
            "create file", "edit file", "list files", "list folder", "show files",
            "directory", "folder contents", "file system", "read the file",
            "open the file", "show me the file", "what's in", "contents of",
        ]

        # Browser task indicators
        browser_keywords = [
            "browse", "open browser", "navigate to", "go to website", "go to http",
            "search the web", "search online", "look up online", "open a tab",
            "visit the site", "click on", "take a screenshot", "web search",
            "search google", "search bing",
        ]

        # Research indicators
        research_keywords = [
            "research", "investigate", "find information about", "look up",
            "search for information", "analyze", "deep dive", "comprehensive overview",
            "what is", "explain to me", "tell me about", "find out about",
            "gather information",
        ]

        # Check for explicit patterns first
        if any(kw in message_lower for kw in file_keywords):
            return "file_operation"
        if any(kw in message_lower for kw in browser_keywords):
            return "browser_task"
        if any(kw in message_lower for kw in research_keywords):
            return "research"

        return "chat"

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
        system_prompt = """You are an intelligent AI assistant powered by NVIDIA NIM.
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
                plan_messages, stream=False, max_tokens=256, temperature=0.1
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
                analysis_messages, max_tokens=512
            ):
                yield chunk

    async def _handle_browser_task(
        self,
        message: str,
        messages: List[Dict[str, str]],
    ) -> AsyncIterator[str]:
        """Handle browser automation tasks."""
        yield "Planning browser actions...\n\n"

        # Ask LLM for the URL and what to do
        plan_messages = messages + [
            {
                "role": "system",
                "content": (
                    "The user wants a browser task. Respond with ONLY a JSON object "
                    "(no markdown) with:\n"
                    '{"url": "full URL to navigate to", '
                    '"action": "navigate|search|extract|screenshot", '
                    '"search_query": "query if searching (optional)", '
                    '"extract_selector": "CSS selector to extract (optional)"}\n'
                    "For web searches, use https://www.google.com/search?q=QUERY"
                ),
            },
        ]

        plan_json = ""
        try:
            async for chunk in self.nvidia_client.chat_completion(
                plan_messages, stream=False, max_tokens=256, temperature=0.1
            ):
                plan_json = chunk
        except Exception as e:
            logger.error(f"LLM browser planning failed: {e}")
            async for chunk in self._handle_chat(messages):
                yield chunk
            return

        action_plan = self._parse_json_response(plan_json)
        if not action_plan or "url" not in action_plan:
            yield "I couldn't determine the browser action. Let me answer instead.\n\n"
            async for chunk in self._handle_chat(messages):
                yield chunk
            return

        url = action_plan.get("url", "")
        browser_action = action_plan.get("action", "navigate")
        search_query = action_plan.get("search_query", "")
        extract_selector = action_plan.get("extract_selector", "body")

        yield f"**Navigating to**: `{url}`\n\n"

        try:
            browser = await self.get_browser()

            # Navigate to URL
            await browser.navigate(url)
            yield "✅ Page loaded\n\n"

            extracted_text = ""
            if browser_action in ("extract", "search", "navigate"):
                # Take screenshot
                screenshot_bytes = await browser.take_screenshot()
                yield f"📸 Screenshot captured ({len(screenshot_bytes):,} bytes)\n\n"

                # Extract page text
                extracted_text = await browser.get_text("body")
                preview = extracted_text[:1000] if extracted_text else "No text found"
                yield f"**Page content preview:**\n```\n{preview}\n```\n\n"

        except Exception as e:
            logger.error(f"Browser error: {e}")
            yield f"❌ Browser error: {e}\n\n"
            yield "Let me provide a text-based answer instead:\n\n"
            async for chunk in self._handle_chat(messages):
                yield chunk
            return

        # Summarize with LLM
        if extracted_text:
            yield "---\n\n**Summary:**\n"
            summary_messages = messages + [
                {
                    "role": "assistant",
                    "content": f"I navigated to {url} and found:\n{extracted_text[:2000]}",
                },
                {
                    "role": "user",
                    "content": (
                        f"Based on the page content from {url}, please answer: {message}"
                    ),
                },
            ]
            full_response = ""
            async for chunk in self.nvidia_client.chat_completion(
                summary_messages, max_tokens=1024
            ):
                full_response += chunk
                yield chunk

            await self.memory.add_message(
                "assistant",
                full_response,
                session_id=self.current_session_id,
            )

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
