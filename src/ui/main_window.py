"""Main window for NVIDIA AI Agent."""
import asyncio
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from src.core.agent import AgentOrchestrator
from src.ui.settings_dialog import SettingsDialog
from src.ui.widgets import MessageBubble, TypingIndicator


class Sidebar(QWidget):
    """Sidebar widget for navigation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(260)
        self._setup_ui()

    def _setup_ui(self):
        """Setup sidebar UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # App title
        title = QLabel("NVIDIA AI Agent")
        title.setObjectName("title")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 8px;")
        layout.addWidget(title)

        # New chat button
        self.new_chat_btn = QPushButton("+ New Chat")
        self.new_chat_btn.setObjectName("secondary")
        self.new_chat_btn.setStyleSheet(
            "QPushButton { padding: 10px; font-weight: bold; }"
        )
        layout.addWidget(self.new_chat_btn)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: #404040; margin: 8px 0;")
        layout.addWidget(separator)

        # Navigation buttons
        nav_label = QLabel("NAVIGATION")
        nav_label.setStyleSheet("color: #888; font-size: 11px; padding: 8px;")
        layout.addWidget(nav_label)

        self.chat_btn = self._create_nav_button("Chat", True)
        self.files_btn = self._create_nav_button("Files", False)
        self.browser_btn = self._create_nav_button("Browser", False)
        self.memory_btn = self._create_nav_button("Memory", False)
        self.tasks_btn = self._create_nav_button("Tasks", False)

        layout.addWidget(self.chat_btn)
        layout.addWidget(self.files_btn)
        layout.addWidget(self.browser_btn)
        layout.addWidget(self.memory_btn)
        layout.addWidget(self.tasks_btn)

        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setStyleSheet("color: #404040; margin: 8px 0;")
        layout.addWidget(separator2)

        # Settings button
        self.settings_btn = self._create_nav_button("Settings", False)
        layout.addWidget(self.settings_btn)

        # Spacer
        layout.addStretch()

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(
            "color: #76b900; font-size: 12px; padding: 8px;"
        )
        layout.addWidget(self.status_label)

    def _create_nav_button(self, text: str, checked: bool) -> QPushButton:
        """Create a navigation button."""
        btn = QPushButton(text)
        btn.setObjectName("sidebarButton")
        btn.setCheckable(True)
        btn.setChecked(checked)
        return btn

    def set_status(self, status: str, is_error: bool = False):
        """Update status label."""
        self.status_label.setText(status)
        color = "#ff5252" if is_error else "#76b900"
        self.status_label.setStyleSheet(f"color: {color}; font-size: 12px; padding: 8px;")


class ChatWidget(QWidget):
    """Chat interface widget."""

    message_sent = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._is_typing = False

    def _setup_ui(self):
        """Setup chat UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scroll area for messages
        scroll = QScrollArea()
        scroll.setObjectName("chatArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        # Container for messages
        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(20, 20, 20, 20)
        self.messages_layout.setSpacing(16)
        self.messages_layout.addStretch()

        scroll.setWidget(self.messages_container)
        layout.addWidget(scroll)

        # Store scroll widget reference
        self.scroll_area = scroll

        # Input area
        input_frame = QFrame()
        input_frame.setObjectName("inputArea")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(20, 16, 20, 16)
        input_layout.setSpacing(12)

        # Message input
        self.message_input = QTextEdit()
        self.message_input.setObjectName("messageInput")
        self.message_input.setPlaceholderText("Type a message...")
        self.message_input.setMaximumHeight(120)
        self.message_input.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.message_input.keyPressEvent = self._handle_key_press
        input_layout.addWidget(self.message_input)

        # Send button
        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedSize(80, 40)
        self.send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_btn)

        layout.addWidget(input_frame)

        # Typing indicator (hidden by default)
        self.typing_indicator = TypingIndicator()
        self.typing_indicator.setVisible(False)

    def _handle_key_press(self, event):
        """Handle key press in message input."""
        if event.key() == Qt.Key.Key_Return and not event.modifiers():
            self._send_message()
        else:
            QTextEdit.keyPressEvent(self.message_input, event)

    def _send_message(self):
        """Send message."""
        text = self.message_input.toPlainText().strip()
        if text and not self._is_typing:
            self.message_sent.emit(text)
            self.add_message(text, is_user=True)
            self.message_input.clear()

    def add_message(self, text: str, is_user: bool = False):
        """Add a message to the chat."""
        bubble = MessageBubble(text, is_user)
        # Insert before stretch
        self.messages_layout.insertWidget(
            self.messages_layout.count() - 1,
            bubble,
        )
        self._scroll_to_bottom()

    def add_typing_indicator(self):
        """Show typing indicator."""
        self._is_typing = True
        self.messages_layout.insertWidget(
            self.messages_layout.count() - 1,
            self.typing_indicator,
        )
        self.typing_indicator.setVisible(True)
        self._scroll_to_bottom()

    def remove_typing_indicator(self):
        """Hide typing indicator."""
        self._is_typing = False
        self.typing_indicator.setVisible(False)
        self.typing_indicator.setParent(None)

    def clear_chat(self):
        """Clear all messages."""
        # Remove all widgets except stretch
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _scroll_to_bottom(self):
        """Scroll to bottom of chat."""
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def set_enabled(self, enabled: bool):
        """Enable/disable input."""
        self.message_input.setEnabled(enabled)
        self.send_btn.setEnabled(enabled)


class PlaceholderWidget(QWidget):
    """Placeholder widget for unimplemented features."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel(f"{title}\n\nComing in Phase 2")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 18px; color: #666;")
        layout.addWidget(label)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, orchestrator: AgentOrchestrator, parent=None):
        super().__init__(parent)
        self.orchestrator = orchestrator
        self._setup_ui()
        self._connect_signals()

        # Start with settings if no API key
        if not orchestrator.is_ready:
            self._show_settings()

    def _setup_ui(self):
        """Setup main window UI."""
        self.setWindowTitle("NVIDIA AI Agent")
        self.setMinimumSize(1000, 700)
        self.resize(1400, 900)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main layout
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)

        # Content area
        self.content_stack = QStackedWidget()

        # Chat widget
        self.chat_widget = ChatWidget()
        self.content_stack.addWidget(self.chat_widget)

        # Placeholder widgets
        self.content_stack.addWidget(PlaceholderWidget("Files"))
        self.content_stack.addWidget(PlaceholderWidget("Browser"))
        self.content_stack.addWidget(PlaceholderWidget("Memory"))
        self.content_stack.addWidget(PlaceholderWidget("Tasks"))

        # Settings widget (placeholder, actual dialog)
        self.content_stack.addWidget(PlaceholderWidget("Settings"))

        main_layout.addWidget(self.content_stack)

    def _connect_signals(self):
        """Connect UI signals."""
        # Sidebar navigation
        self.sidebar.chat_btn.clicked.connect(lambda: self._switch_view(0))
        self.sidebar.files_btn.clicked.connect(lambda: self._switch_view(1))
        self.sidebar.browser_btn.clicked.connect(lambda: self._switch_view(2))
        self.sidebar.memory_btn.clicked.connect(lambda: self._switch_view(3))
        self.sidebar.tasks_btn.clicked.connect(lambda: self._switch_view(4))
        self.sidebar.settings_btn.clicked.connect(self._show_settings)
        self.sidebar.new_chat_btn.clicked.connect(self._new_chat)

        # Chat
        self.chat_widget.message_sent.connect(self._on_message_sent)

    def _switch_view(self, index: int):
        """Switch content view."""
        self.content_stack.setCurrentIndex(index)

        # Update sidebar buttons
        buttons = [
            self.sidebar.chat_btn,
            self.sidebar.files_btn,
            self.sidebar.browser_btn,
            self.sidebar.memory_btn,
            self.sidebar.tasks_btn,
        ]
        for i, btn in enumerate(buttons):
            btn.setChecked(i == index)

    def _show_settings(self):
        """Show settings dialog."""
        dialog = SettingsDialog(self.orchestrator, self)
        if dialog.exec():
            # Refresh if settings changed
            self._update_status()

    def _new_chat(self):
        """Start a new chat session."""
        # Create new session
        asyncio.create_task(self._create_new_session())

    async def _create_new_session(self):
        """Create new session asynchronously."""
        session_id = await self.orchestrator.new_session()
        self.chat_widget.clear_chat()
        self._update_status()
        logger.info(f"Created new session: {session_id}")

    def _update_status(self):
        """Update sidebar status."""
        if self.orchestrator.is_ready:
            self.sidebar.set_status("Connected")
        else:
            self.sidebar.set_status("API Key Required", is_error=True)

    def _on_message_sent(self, message: str):
        """Handle user message."""
        if not self.orchestrator.is_ready:
            self.chat_widget.add_message(
                "Please configure your NVIDIA API key in Settings first.",
                is_user=False,
            )
            return

        # Start processing
        self.chat_widget.set_enabled(False)
        self.chat_widget.add_typing_indicator()

        # Process message asynchronously
        asyncio.create_task(self._process_message(message))

    async def _process_message(self, message: str):
        """Process message with agent."""
        response_text = ""
        try:
            async for chunk in self.orchestrator.process_message(message):
                response_text += chunk
                # Update UI with streaming response
                await self._update_response(response_text)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            response_text = f"Error: {str(e)}"
            await self._update_response(response_text, is_error=True)
        finally:
            self.chat_widget.remove_typing_indicator()
            self.chat_widget.set_enabled(True)

    async def _update_response(self, text: str, is_error: bool = False):
        """Update response in UI."""
        # Remove typing indicator temporarily
        self.chat_widget.remove_typing_indicator()

        # Add/update message
        # For simplicity, we add a new message each time (streaming simulation)
        # In production, you'd update the existing message bubble
        self.chat_widget.add_message(text, is_user=False)

    def closeEvent(self, event):
        """Handle window close."""
        # Cleanup
        asyncio.create_task(self.orchestrator.close())
        event.accept()
