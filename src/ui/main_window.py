"""Main window for NVIDIA AI Agent."""
import asyncio
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
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

        self.chat_btn = self._create_nav_button("💬 Chat", True)
        self.files_btn = self._create_nav_button("📁 Files", False)
        self.browser_btn = self._create_nav_button("🌐 Browser", False)
        self.memory_btn = self._create_nav_button("🧠 Memory", False)
        self.tasks_btn = self._create_nav_button("📋 Tasks", False)

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
        self.settings_btn = self._create_nav_button("⚙ Settings", False)
        layout.addWidget(self.settings_btn)

        # Spacer
        layout.addStretch()

        # Model indicator
        self.model_label = QLabel("")
        self.model_label.setStyleSheet("color: #666; font-size: 11px; padding: 4px 8px;")
        self.model_label.setWordWrap(True)
        layout.addWidget(self.model_label)

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

    def set_model(self, model: str):
        """Show current model name."""
        short = model.split("/")[-1] if "/" in model else model
        self.model_label.setText(f"Model: {short}")


class ChatWidget(QWidget):
    """Chat interface widget."""

    message_sent = pyqtSignal(str)
    voice_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._is_typing = False
        self._current_ai_bubble: Optional[MessageBubble] = None

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
        input_layout.setSpacing(8)

        # Voice button
        self.voice_btn = QPushButton("🎤")
        self.voice_btn.setObjectName("secondary")
        self.voice_btn.setFixedSize(44, 40)
        self.voice_btn.setToolTip("Hold to speak (push-to-talk)")
        self.voice_btn.setCheckable(True)
        self.voice_btn.clicked.connect(self._on_voice_clicked)
        input_layout.addWidget(self.voice_btn)

        # Message input
        self.message_input = QTextEdit()
        self.message_input.setObjectName("messageInput")
        self.message_input.setPlaceholderText("Type a message or click 🎤 to speak...")
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

        # Voice recording indicator (hidden by default)
        self.voice_indicator = QLabel("🔴 Recording... (click mic again to send)")
        self.voice_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voice_indicator.setStyleSheet(
            "background: #3d1a1a; color: #ff5252; padding: 8px; font-size: 13px;"
        )
        self.voice_indicator.setVisible(False)
        layout.addWidget(self.voice_indicator)

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

    def _on_voice_clicked(self):
        """Handle voice button click."""
        self.voice_requested.emit()

    def set_voice_recording(self, is_recording: bool):
        """Update voice recording state in UI."""
        self.voice_btn.setChecked(is_recording)
        self.voice_indicator.setVisible(is_recording)
        self.message_input.setEnabled(not is_recording)
        self.send_btn.setEnabled(not is_recording)

    def set_transcription(self, text: str):
        """Set transcribed text in input field."""
        self.message_input.setPlainText(text)
        self.set_voice_recording(False)
        self.message_input.setFocus()

    def add_message(self, text: str, is_user: bool = False):
        """Add a new message bubble to the chat."""
        bubble = MessageBubble(text, is_user)
        self.messages_layout.insertWidget(
            self.messages_layout.count() - 1,
            bubble,
        )
        self._scroll_to_bottom()
        return bubble

    def begin_ai_response(self) -> MessageBubble:
        """Create a new AI response bubble and return it for streaming updates."""
        bubble = MessageBubble("", is_user=False)
        self._current_ai_bubble = bubble
        self.messages_layout.insertWidget(
            self.messages_layout.count() - 1,
            bubble,
        )
        self._scroll_to_bottom()
        return bubble

    def update_ai_response(self, text: str):
        """Update the current streaming AI response bubble."""
        if self._current_ai_bubble is not None:
            self._current_ai_bubble.set_text(text)
            self._scroll_to_bottom()

    def finish_ai_response(self):
        """Finalize the current AI response bubble."""
        self._current_ai_bubble = None

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
        self._current_ai_bubble = None
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
        if enabled:
            self.voice_btn.setEnabled(True)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, orchestrator: AgentOrchestrator, parent=None):
        super().__init__(parent)
        self.orchestrator = orchestrator
        self._is_recording = False
        self._speech_interface = None  # Lazy-loaded
        self._setup_ui()
        self._connect_signals()
        self._update_status()

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

        # 0: Chat widget
        self.chat_widget = ChatWidget()
        self.content_stack.addWidget(self.chat_widget)

        # 1: Files panel
        from src.ui.files_panel import FilesPanel
        self.files_panel = FilesPanel(
            files_manager=self.orchestrator._files,  # may be None, set later
        )
        self.content_stack.addWidget(self.files_panel)

        # 2: Browser panel
        from src.ui.browser_panel import BrowserPanel
        self.browser_panel = BrowserPanel(
            browser_controller=self.orchestrator._browser,  # may be None, set later
        )
        self.content_stack.addWidget(self.browser_panel)

        # 3: Memory panel
        from src.ui.memory_panel import MemoryPanel
        self.memory_panel = MemoryPanel(
            memory_system=self.orchestrator.memory,
        )
        self.content_stack.addWidget(self.memory_panel)

        # 4: Tasks panel
        from src.ui.tasks_panel import TasksPanel
        self.tasks_panel = TasksPanel(
            task_planner=self.orchestrator._task_planner,  # may be None, set later
        )
        self.content_stack.addWidget(self.tasks_panel)

        main_layout.addWidget(self.content_stack)

        # Update model label
        self.sidebar.set_model(self.orchestrator.config.default_model)

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
        self.chat_widget.voice_requested.connect(self._on_voice_requested)

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

        # Refresh panels when switching to them
        if index == 1:
            # Files panel - update manager ref if it was lazy-loaded
            if self.orchestrator._files:
                self.files_panel.set_files_manager(self.orchestrator._files)
        elif index == 2:
            # Browser panel - update controller ref
            if self.orchestrator._browser:
                self.browser_panel.set_browser_controller(self.orchestrator._browser)
        elif index == 3:
            # Memory panel - refresh sessions
            self.memory_panel._load_sessions()
        elif index == 4:
            # Tasks panel - update planner ref
            if self.orchestrator._task_planner:
                self.tasks_panel.set_task_planner(self.orchestrator._task_planner)

    def _show_settings(self):
        """Show settings dialog."""
        dialog = SettingsDialog(self.orchestrator, self)
        if dialog.exec():
            self._update_status()
            self.sidebar.set_model(self.orchestrator.config.default_model)

    def _new_chat(self):
        """Start a new chat session."""
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
            self.sidebar.set_status("● Connected")
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

        # Disable input during processing
        self.chat_widget.set_enabled(False)
        self.chat_widget.add_typing_indicator()
        self.sidebar.set_status("● Processing...")

        # Process message asynchronously
        asyncio.create_task(self._process_message(message))

    async def _process_message(self, message: str):
        """Process message with agent using proper streaming (single bubble)."""
        response_text = ""
        ai_bubble: Optional[MessageBubble] = None

        try:
            async for chunk in self.orchestrator.process_message(message):
                response_text += chunk

                if ai_bubble is None:
                    # Remove typing indicator and create AI bubble on first chunk
                    self.chat_widget.remove_typing_indicator()
                    ai_bubble = self.chat_widget.begin_ai_response()

                # Update the same bubble with accumulated text
                self.chat_widget.update_ai_response(response_text)

                # Yield control to event loop for UI updates
                await asyncio.sleep(0)

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            if ai_bubble is None:
                self.chat_widget.remove_typing_indicator()
                ai_bubble = self.chat_widget.begin_ai_response()
            self.chat_widget.update_ai_response(f"❌ Error: {str(e)}")

        finally:
            if ai_bubble is None:
                # No response at all — remove typing indicator
                self.chat_widget.remove_typing_indicator()
                self.chat_widget.add_message("No response received.", is_user=False)

            self.chat_widget.finish_ai_response()
            self.chat_widget.set_enabled(True)
            self._update_status()

    def _on_voice_requested(self):
        """Handle voice mic button click."""
        if self._is_recording:
            # Stop recording
            self._is_recording = False
            self.chat_widget.set_voice_recording(False)
        else:
            # Start recording
            self._is_recording = True
            self.chat_widget.set_voice_recording(True)
            asyncio.create_task(self._record_and_transcribe())

    async def _record_and_transcribe(self):
        """Record audio and transcribe to text."""
        try:
            # Lazy-load speech interface
            if self._speech_interface is None:
                self.sidebar.set_status("Loading speech model...")
                try:
                    from src.capabilities.speech import SpeechInterface
                    self._speech_interface = SpeechInterface()
                    logger.info("SpeechInterface loaded")
                except ImportError as e:
                    logger.error(f"Speech not available: {e}")
                    self.chat_widget.set_transcription("")
                    self.chat_widget.add_message(
                        "Speech requires faster-whisper and piper-tts to be installed.",
                        is_user=False,
                    )
                    self._is_recording = False
                    return

            self.sidebar.set_status("● Recording...")

            # Record audio (5 seconds with VAD)
            text = await self._speech_interface.listen_and_transcribe(duration=5)

            if text:
                self.chat_widget.set_transcription(text)
                logger.info(f"Transcribed: {text}")
            else:
                self.chat_widget.set_voice_recording(False)
                self.chat_widget.add_message(
                    "No speech detected. Please try again.",
                    is_user=False,
                )

        except Exception as e:
            logger.error(f"Voice recording error: {e}")
            self.chat_widget.set_voice_recording(False)
            self.chat_widget.add_message(
                f"Voice recording error: {e}",
                is_user=False,
            )
        finally:
            self._is_recording = False
            self._update_status()

    def closeEvent(self, event):
        """Handle window close."""
        asyncio.create_task(self.orchestrator.close())
        event.accept()
