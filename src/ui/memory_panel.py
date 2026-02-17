"""Memory Panel - Conversation history and semantic memory viewer."""
import asyncio
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from loguru import logger


class MemoryPanel(QWidget):
    """Memory and conversation history viewer."""

    session_selected = pyqtSignal(str)  # session_id

    def __init__(self, memory_system=None, parent=None):
        super().__init__(parent)
        self.memory_system = memory_system
        self._setup_ui()

    def _setup_ui(self):
        """Setup memory panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        header = QLabel("Memory & History")
        header.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(header)

        # Semantic search
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search memories semantically...")
        self.search_input.returnPressed.connect(self._do_search)
        search_layout.addWidget(self.search_input)

        search_btn = QPushButton("Search")
        search_btn.setFixedWidth(80)
        search_btn.clicked.connect(self._do_search)
        search_layout.addWidget(search_btn)

        layout.addLayout(search_layout)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: sessions list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)

        sessions_label = QLabel("Conversation Sessions")
        sessions_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        left_layout.addWidget(sessions_label)

        self.sessions_list = QListWidget()
        self.sessions_list.setMinimumWidth(220)
        self.sessions_list.currentRowChanged.connect(self._on_session_selected)
        left_layout.addWidget(self.sessions_list)

        # Session controls
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("secondary")
        refresh_btn.clicked.connect(self._load_sessions)
        btn_layout.addWidget(refresh_btn)

        clear_btn = QPushButton("Clear Selected")
        clear_btn.setObjectName("secondary")
        clear_btn.clicked.connect(self._clear_selected_session)
        btn_layout.addWidget(clear_btn)
        left_layout.addLayout(btn_layout)

        splitter.addWidget(left_widget)

        # Right: conversation messages + search results
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)

        self.messages_label = QLabel("Messages")
        self.messages_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        right_layout.addWidget(self.messages_label)

        self.messages_text = QTextEdit()
        self.messages_text.setReadOnly(True)
        self.messages_text.setPlaceholderText("Select a session to view its messages...")
        right_layout.addWidget(self.messages_text)

        splitter.addWidget(right_widget)
        splitter.setSizes([240, 560])
        layout.addWidget(splitter)

        # Load sessions on init
        asyncio.create_task(self._async_load_sessions())

    def _load_sessions(self):
        """Refresh sessions list."""
        asyncio.create_task(self._async_load_sessions())

    async def _async_load_sessions(self):
        """Load sessions from memory system."""
        self.sessions_list.clear()
        if not self.memory_system:
            return
        try:
            sessions = await self.memory_system.get_sessions()
            for session in sessions:
                session_id = session.get("session_id", "unknown")
                created = session.get("created_at", "")
                title = session.get("title") or session_id[:12]
                label = f"💬 {title}"
                if created:
                    # Show short date
                    label += f"  {str(created)[:10]}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, session_id)
                self.sessions_list.addItem(item)
        except Exception as e:
            logger.error(f"Failed to load sessions: {e}")

    def _on_session_selected(self, row: int):
        """Show messages for selected session."""
        item = self.sessions_list.item(row)
        if not item:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if session_id:
            asyncio.create_task(self._load_messages(session_id))

    async def _load_messages(self, session_id: str):
        """Load messages for a session."""
        if not self.memory_system:
            return
        try:
            messages = await self.memory_system.get_recent_messages(
                limit=50, session_id=session_id
            )
            self.messages_label.setText(f"Messages ({len(messages)})")

            text_parts = []
            for msg in messages:
                role = msg.get("role", "?").upper()
                content = msg.get("content", "")
                timestamp = str(msg.get("timestamp", ""))[:19]
                sep = "─" * 40
                text_parts.append(f"{sep}\n[{role}] {timestamp}\n{content}\n")

            self.messages_text.setPlainText("\n".join(text_parts))
        except Exception as e:
            logger.error(f"Failed to load messages: {e}")

    def _clear_selected_session(self):
        """Clear messages for selected session."""
        item = self.sessions_list.currentItem()
        if not item:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if session_id and self.memory_system:
            asyncio.create_task(self._do_clear_session(session_id))

    async def _do_clear_session(self, session_id: str):
        """Clear session messages."""
        try:
            await self.memory_system.clear_session(session_id)
            self.messages_text.setPlainText("Session cleared.")
            await self._async_load_sessions()
        except Exception as e:
            logger.error(f"Failed to clear session: {e}")

    def _do_search(self):
        """Execute semantic search."""
        query = self.search_input.text().strip()
        if query:
            asyncio.create_task(self._async_search(query))

    async def _async_search(self, query: str):
        """Run semantic search."""
        if not self.memory_system:
            return
        try:
            results = await self.memory_system.search_memory(query, limit=10)
            self.messages_label.setText(f"Search Results for: '{query}'")
            text_parts = []
            for r in results:
                role = r.get("role", "?").upper()
                content = r.get("content", "")
                sep = "─" * 40
                text_parts.append(f"{sep}\n[{role}] (semantic match)\n{content}\n")
            if not text_parts:
                self.messages_text.setPlainText("No results found.")
            else:
                self.messages_text.setPlainText("\n".join(text_parts))
        except Exception as e:
            logger.error(f"Search failed: {e}")
            self.messages_text.setPlainText(f"Search error: {e}")

    def set_memory_system(self, memory):
        """Set the memory system."""
        self.memory_system = memory
        self._load_sessions()
