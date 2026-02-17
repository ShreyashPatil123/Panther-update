"""Agent Orchestrator - Central brain that coordinates all capabilities."""
import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger

from src.api.nvidia_client import NVIDIAClient
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

        # Capabilities (initialized lazily)
        self._browser = None
        self._files = None
        self._speech = None
        self._research = None

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
        """Set NVIDIA API key and initialize client.

        Args:
            api_key: NVIDIA API key
        """
        self.nvidia_client = NVIDIAClient(
            api_key=api_key,
            base_url=self.config.nvidia_base_url,
        )
        logger.info("NVIDIA API client initialized")

    @property
    def is_ready(self) -> bool:
        """Check if agent is ready to process messages."""
        return self.nvidia_client is not None

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

            # Retrieve relevant context
            context = await self.memory.get_relevant_context(
                message,
                limit=5,
                session_id=self.current_session_id,
            )

            # Build messages for LLM
            messages = self._build_messages(message, context)

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
                # Standard chat
                async for chunk in self._handle_chat(messages):
                    yield chunk

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            yield f"Sorry, I encountered an error: {str(e)}"

    async def _classify_intent(self, message: str) -> str:
        """Classify user intent using rules (can be enhanced with ML).

        Args:
            message: User message

        Returns:
            Intent classification
        """
        message_lower = message.lower()

        # File operation indicators
        file_keywords = [
            "open",
            "read",
            "file",
            "folder",
            "document",
            "save",
            "write",
            "create file",
            "edit",
            "folder",
            "directory",
        ]

        # Browser task indicators
        browser_keywords = [
            "browse",
            "website",
            "web",
            "open browser",
            "navigate",
            "search the web",
            "go to",
            "visit",
            "click",
            "screenshot",
        ]

        # Research indicators
        research_keywords = [
            "research",
            "investigate",
            "find information",
            "look up",
            "search for",
            "analyze",
            "study",
            "deep dive",
            "comprehensive",
        ]

        # Simple keyword matching (can be replaced with LLM classification)
        if any(word in message_lower for word in file_keywords):
            return "file_operation"
        elif any(word in message_lower for word in browser_keywords):
            return "browser_task"
        elif any(word in message_lower for word in research_keywords):
            return "research"

        return "chat"

    def _build_messages(
        self,
        message: str,
        context: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """Build message list with system prompt and context.

        Args:
            message: Current user message
            context: Relevant context from memory

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
- When performing actions, explain what you're doing
- Ask for clarification when needed
- Always prioritize user privacy and security"""

        messages = [{"role": "system", "content": system_prompt}]

        # Add relevant context
        if context:
            context_text = "\n\nRelevant context from previous conversations:\n"
            for ctx in context:
                role = ctx.get("role", "unknown")
                content = ctx.get("content", "")
                context_text += f"[{role}]: {content}\n"
            messages.append({"role": "system", "content": context_text})

        # Add recent conversation history
        # This could be optimized to fetch from memory

        # Add current message
        messages.append({"role": "user", "content": message})

        return messages

    async def _handle_chat(self, messages: List[Dict[str, str]]) -> AsyncIterator[str]:
        """Handle standard chat interaction.

        Args:
            messages: Messages for LLM

        Yields:
            Response chunks
        """
        full_response = ""

        try:
            async for chunk in self.nvidia_client.chat_completion(messages):
                full_response += chunk
                yield chunk

            # Store response in memory
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
        """Handle file system operations.

        Args:
            message: User message
            messages: Messages for LLM

        Yields:
            Response chunks
        """
        yield "I understand you want to perform a file operation. "
        yield "File system capabilities will be implemented in Phase 2.\n\n"

        # For now, just do a regular chat
        async for chunk in self._handle_chat(messages):
            yield chunk

    async def _handle_browser_task(
        self,
        message: str,
        messages: List[Dict[str, str]],
    ) -> AsyncIterator[str]:
        """Handle browser automation tasks.

        Args:
            message: User message
            messages: Messages for LLM

        Yields:
            Response chunks
        """
        yield "I understand you want me to perform a browser task. "
        yield "Browser automation will be implemented in Phase 2.\n\n"

        # For now, just do a regular chat
        async for chunk in self._handle_chat(messages):
            yield chunk

    async def _handle_research(
        self,
        message: str,
        messages: List[Dict[str, str]],
    ) -> AsyncIterator[str]:
        """Handle research tasks.

        Args:
            message: User message
            messages: Messages for LLM

        Yields:
            Response chunks
        """
        yield "I understand you want me to perform research. "
        yield "Research capabilities will be implemented in Phase 2.\n\n"

        # For now, just do a regular chat
        async for chunk in self._handle_chat(messages):
            yield chunk

    async def set_session(self, session_id: str):
        """Switch to a different session.

        Args:
            session_id: Session identifier
        """
        self.current_session_id = session_id
        await self.memory.create_session(session_id)
        logger.info(f"Switched to session: {session_id}")

    async def new_session(self) -> str:
        """Create a new session.

        Returns:
            New session ID
        """
        import uuid

        session_id = str(uuid.uuid4())
        await self.memory.create_session(session_id)
        self.current_session_id = session_id
        logger.info(f"Created new session: {session_id}")
        return session_id

    async def get_sessions(self) -> List[Dict[str, Any]]:
        """Get list of sessions.

        Returns:
            List of session information
        """
        return await self.memory.get_sessions()

    async def clear_current_session(self):
        """Clear the current session."""
        await self.memory.clear_session(self.current_session_id)
        logger.info(f"Cleared current session: {self.current_session_id}")

    async def validate_api_key(self, api_key: str) -> bool:
        """Validate an API key.

        Args:
            api_key: API key to validate

        Returns:
            True if valid, False otherwise
        """
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

        # Cancel active tasks
        for task in self.active_tasks.values():
            task.cancel()

        # Close memory
        await self.memory.close()

        # Close NVIDIA client
        if self.nvidia_client:
            await self.nvidia_client.close()

        logger.info("Agent orchestrator closed")
