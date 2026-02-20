"""Main window for NVIDIA AI Agent — panther orange resin theme."""
import asyncio
import os
from typing import Dict, List, Optional

import httpx

from PyQt6.QtCore import Qt, QEvent, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
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
from src.core.model_router import TaskCategory, get_all_presets, get_task_preset
from src.ui.settings_dialog import SettingsDialog
from src.ui.widgets import MessageBubble, TypingIndicator
from src.ui.panther_buttons import PantherSendButton, PantherMicButton, PantherAttachButton


class Sidebar(QWidget):
    """Sidebar — minimal, premium navigation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(240)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(6)

        # ── Brand / logo area ──
        brand = QLabel("⬢ NVIDIA AI")
        brand.setObjectName("title")
        brand.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #FF6B35; "
            "padding: 4px 6px; letter-spacing: -0.5px;"
        )
        layout.addWidget(brand)

        layout.addSpacing(8)

        # ── New Chat button ──
        self.new_chat_btn = QPushButton("＋  New chat")
        self.new_chat_btn.setObjectName("secondary")
        self.new_chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_chat_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #f0ece8;
                border: 1px solid #2a2218;
                border-radius: 10px;
                padding: 10px 14px;
                font-weight: 600;
                font-size: 13px;
                text-align: left;
            }
            QPushButton:hover {
                background: #1a1510;
                border-color: #FF6B35;
                color: #ffffff;
            }
        """)
        layout.addWidget(self.new_chat_btn)

        layout.addSpacing(4)

        # ── Navigation ──
        self.chat_btn = self._create_nav_button("💬  Chat", True)
        self.files_btn = self._create_nav_button("📂  Files", False)
        self.browser_btn = self._create_nav_button("🌐  Browse", False)
        self.memory_btn = self._create_nav_button("🧠  Memory", False)
        self.tasks_btn = self._create_nav_button("☑  Tasks", False)

        for btn in [self.chat_btn, self.files_btn, self.browser_btn,
                     self.memory_btn, self.tasks_btn]:
            layout.addWidget(btn)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2a2218; max-height: 1px; margin: 8px 0;")
        layout.addWidget(sep)

        # ── Settings ──
        self.settings_btn = self._create_nav_button("⚙  Settings", False)
        layout.addWidget(self.settings_btn)

        # ── Spacer → pushes status to bottom ──
        layout.addStretch()

        # ── Model indicator ──
        self.model_label = QLabel("")
        self.model_label.setWordWrap(True)
        self.model_label.setStyleSheet(
            "color: #5a5248; font-size: 11px; padding: 2px 6px;"
        )
        layout.addWidget(self.model_label)

        # ── Status ──
        self.status_label = QLabel("● Ready")
        self.status_label.setStyleSheet(
            "color: #FF6B35; font-size: 11px; padding: 4px 6px; font-weight: 500;"
        )
        layout.addWidget(self.status_label)

    def _create_nav_button(self, text: str, checked: bool) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("sidebarButton")
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def set_status(self, status: str, is_error: bool = False):
        self.status_label.setText(status)
        color = "#FF4500" if is_error else "#FF6B35"
        self.status_label.setStyleSheet(
            f"color: {color}; font-size: 11px; padding: 4px 6px; font-weight: 500;"
        )

    def set_model(self, model: str):
        short = model.split("/")[-1] if "/" in model else model
        self.model_label.setText(f"Model: {short}")


class ChatWidget(QWidget):
    """Chat interface widget."""

    message_sent = pyqtSignal(str)
    message_sent_with_attachments = pyqtSignal(str, list)  # (text, [filepaths])
    voice_requested = pyqtSignal()
    task_selected = pyqtSignal(str)  # emits TaskCategory value string

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._is_typing = False
        self._current_ai_bubble: Optional[MessageBubble] = None
        self._pending_attachments: List[str] = []  # file paths awaiting send

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
        self.messages_layout.setContentsMargins(28, 24, 28, 24)
        self.messages_layout.setSpacing(20)
        self.messages_layout.addStretch()

        scroll.setWidget(self.messages_container)
        layout.addWidget(scroll)

        # Store scroll widget reference
        self.scroll_area = scroll

        # ── Task preset pills (above input) ─────────────────────────────
        task_strip = QFrame()
        task_strip.setObjectName("taskStrip")
        task_strip.setStyleSheet("""
            QFrame#taskStrip {
                background: transparent;
                border: none;
                padding: 0;
            }
        """)
        task_layout = QHBoxLayout(task_strip)
        task_layout.setContentsMargins(32, 6, 32, 2)
        task_layout.setSpacing(5)

        self._task_buttons: Dict[str, QPushButton] = {}
        self._active_task: Optional[str] = None

        for category, preset in get_all_presets().items():
            btn = QPushButton(f"{preset.emoji} {preset.label}")
            btn.setCheckable(True)
            btn.setToolTip(f"{preset.description}\nModel: {preset.model}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #8a8078;
                    border: 1px solid #2a2218;
                    border-radius: 12px;
                    padding: 4px 10px;
                    font-size: 11px;
                    min-height: 22px;
                }
                QPushButton:hover {
                    background: #1a1510;
                    color: #f0ece8;
                    border-color: #FF6B35;
                }
                QPushButton:checked {
                    background: rgba(255, 107, 53, 0.15);
                    color: #FF6B35;
                    border-color: #FF6B35;
                    font-weight: 600;
                }
            """)
            btn.clicked.connect(
                lambda checked, cat=category.value: self._on_task_btn_clicked(cat)
            )
            task_layout.addWidget(btn)
            self._task_buttons[category.value] = btn

        # Clear button
        clear_btn = QPushButton("✕")
        clear_btn.setToolTip("Reset to default model")
        clear_btn.setFixedSize(24, 24)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #5a5248;
                border: 1px solid #2a2218;
                border-radius: 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(255, 69, 0, 0.1);
                color: #FF4500;
                border-color: #FF4500;
            }
        """)
        clear_btn.clicked.connect(lambda: self._on_task_btn_clicked(None))
        task_layout.addWidget(clear_btn)
        task_layout.addStretch()
        layout.addWidget(task_strip)

        # ── Attachment preview strip (hidden by default) ────────────────
        self._attachment_strip = QFrame()
        self._attachment_strip.setStyleSheet("""
            QFrame {
                background: #0f0e0c;
                border: 1px solid #2a2218;
                border-bottom: none;
                border-radius: 12px 12px 0 0;
                padding: 4px 8px;
            }
        """)
        self._attachment_layout = QHBoxLayout(self._attachment_strip)
        self._attachment_layout.setContentsMargins(12, 6, 12, 6)
        self._attachment_layout.setSpacing(6)
        self._attachment_layout.addStretch()
        self._attachment_strip.setVisible(False)
        layout.addWidget(self._attachment_strip)

        # ── Input area ────────────────────────────────────────────────────
        input_frame = QFrame()
        input_frame.setObjectName("inputArea")
        input_frame.setStyleSheet("""
            QFrame#inputArea {
                background: transparent;
                border: none;
            }
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(28, 8, 28, 16)
        input_layout.setSpacing(8)

        # Attach button (panther eye)
        self.attach_btn = PantherAttachButton()
        self.attach_btn.clicked.connect(self._on_attach_clicked)
        input_layout.addWidget(self.attach_btn)

        # Voice button (panther mic)
        self.voice_btn = PantherMicButton()
        self.voice_btn.clicked.connect(self._on_voice_clicked)
        input_layout.addWidget(self.voice_btn)

        # Message input
        self.message_input = QTextEdit()
        self.message_input.setObjectName("messageInput")
        self.message_input.setPlaceholderText("Message NVIDIA AI…")
        self.message_input.setMaximumHeight(100)
        self.message_input.setStyleSheet("""
            QTextEdit#messageInput {
                background-color: #0f0e0c;
                color: #f0ece8;
                border: 1px solid #2a2218;
                border-radius: 14px;
                padding: 10px 16px;
                font-size: 14px;
                font-family: 'Inter', 'Segoe UI', sans-serif;
                selection-background-color: #FF6B35;
            }
            QTextEdit#messageInput:focus {
                border: 1px solid #FF6B35;
            }
        """)
        self.message_input.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.message_input.keyPressEvent = self._handle_key_press
        input_layout.addWidget(self.message_input)

        # Send button (panther head)
        self.send_btn = PantherSendButton()
        self.send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_btn)

        layout.addWidget(input_frame)

        # Voice recording indicator (hidden by default)
        self.voice_indicator = QLabel("🐆  Recording… click mic to stop")
        self.voice_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voice_indicator.setStyleSheet(
            "background: rgba(255,107,53,0.08); color: #FF6B35; "
            "padding: 8px; font-size: 12px; border: none;"
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
        """Send message (with optional attachments)."""
        text = self.message_input.toPlainText().strip()
        if text and not self._is_typing:
            if self._pending_attachments:
                # Show attachment info in the user bubble
                names = [os.path.basename(f) for f in self._pending_attachments]
                display = text + "\n" + " ".join(f"📎 {n}" for n in names)
                self.add_message(display, is_user=True)
                self.message_sent_with_attachments.emit(
                    text, list(self._pending_attachments)
                )
                self._clear_attachments()
            else:
                self.message_sent.emit(text)
                self.add_message(text, is_user=True)
            self.message_input.clear()

    # ── Attachment helpers ─────────────────────────────────────────────────

    def _on_attach_clicked(self):
        """Open file dialog to select attachments."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Attach Files",
            "",
            "All Supported Files (*.jpg *.jpeg *.png *.gif *.webp *.bmp "
            "*.pdf *.docx *.txt *.md *.csv *.json *.py *.js *.ts *.java *.cpp "
            "*.c *.h *.html *.css *.sql *.xml *.yaml *.yml *.toml *.log "
            "*.mp4 *.avi *.mov *.mkv *.webm);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp);;"
            "Documents (*.pdf *.docx *.txt *.md *.csv *.json);;"
            "Code (*.py *.js *.ts *.java *.cpp *.c *.h *.html *.css *.sql);;"
            "Videos (*.mp4 *.avi *.mov *.mkv *.webm);;"
            "All Files (*)",
        )
        for filepath in files:
            if filepath not in self._pending_attachments:
                self._pending_attachments.append(filepath)
                self._add_attachment_pill(filepath)

    def _add_attachment_pill(self, filepath: str):
        """Add a visual pill for an attached file."""
        from src.core.file_processor import classify_file, FileType

        name = os.path.basename(filepath)
        ftype = classify_file(filepath)
        icons = {
            FileType.IMAGE: "🖼️",
            FileType.VIDEO: "🎬",
            FileType.DOCUMENT: "📄",
            FileType.TEXT: "📝",
        }
        icon = icons.get(ftype, "📁")

        pill = QFrame()
        pill.setStyleSheet("""
            QFrame {
                background: #1a1510;
                border: 1px solid #2a2218;
                border-radius: 8px;
                padding: 2px 6px;
            }
        """)
        pill_layout = QHBoxLayout(pill)
        pill_layout.setContentsMargins(4, 2, 4, 2)
        pill_layout.setSpacing(4)

        label = QLabel(f"{icon} {name}")
        label.setStyleSheet(
            "color: #b8a898; font-size: 11px; background: transparent; border: none;"
        )
        pill_layout.addWidget(label)

        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(16, 16)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #5a5248;
                border: none;
                font-size: 10px;
            }
            QPushButton:hover {
                color: #FF4500;
            }
        """)
        remove_btn.clicked.connect(lambda: self._remove_attachment(filepath, pill))
        pill_layout.addWidget(remove_btn)

        # Insert before the stretch at the end
        self._attachment_layout.insertWidget(
            self._attachment_layout.count() - 1, pill
        )
        self._attachment_strip.setVisible(True)
        # Morph attach button to panther eye
        if hasattr(self.attach_btn, 'set_has_files'):
            self.attach_btn.set_has_files(True)

    def _remove_attachment(self, filepath: str, pill: QFrame):
        """Remove an attachment pill."""
        if filepath in self._pending_attachments:
            self._pending_attachments.remove(filepath)
        pill.deleteLater()
        if not self._pending_attachments:
            self._attachment_strip.setVisible(False)
            # Revert to paperclip
            if hasattr(self.attach_btn, 'set_has_files'):
                self.attach_btn.set_has_files(False)

    def _clear_attachments(self):
        """Remove all attachment pills after sending."""
        self._pending_attachments.clear()
        # Remove all pills (everything except the stretch)
        while self._attachment_layout.count() > 1:
            item = self._attachment_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._attachment_strip.setVisible(False)
        # Revert attach button to paperclip
        if hasattr(self.attach_btn, 'set_has_files'):
            self.attach_btn.set_has_files(False)

    def _on_voice_clicked(self):
        """Handle voice button click."""
        self.voice_requested.emit()

    def _on_task_btn_clicked(self, category_value: Optional[str]):
        """Handle task preset button click."""
        # Uncheck all buttons first
        for btn in self._task_buttons.values():
            btn.setChecked(False)

        if category_value is None or category_value == self._active_task:
            # Clear / toggle off
            self._active_task = None
            self.task_selected.emit("")
        else:
            # Activate
            self._active_task = category_value
            self._task_buttons[category_value].setChecked(True)
            self.task_selected.emit(category_value)

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
        self._gemini_client = None
        self._gemini_session_task = None
        self._mic_stream = None
        self._app_in_background = False
        self._screen_frame_callback = None  # bound callback for Gemini Live (legacy)
        self._screen_ocr_callback = None  # OCR text callback for Gemini Live

        # Initialize screen capture service
        from src.capabilities.screen_capture import ScreenCaptureService

        self._screen_service = ScreenCaptureService(
            monitor=orchestrator.config.screen_capture_monitor,
            interval=orchestrator.config.screen_capture_interval,
        )
        self._screen_service.vision_enabled = orchestrator.config.screen_capture_vision
        self._screen_service.gemini_enabled = orchestrator.config.screen_capture_gemini

        self._setup_ui()
        self._connect_signals()
        self._update_status()

        # Start screen capture loop (only captures when app is in background + enabled)
        if self._screen_service.is_available:
            self._screen_service.start()

        # Listen for application-wide focus changes
        app = QApplication.instance()
        if app:
            app.applicationStateChanged.connect(self._on_app_state_changed)

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
        self.chat_widget.message_sent_with_attachments.connect(
            self._on_message_sent_with_attachments
        )
        self.chat_widget.voice_requested.connect(self._on_voice_requested)
        self.chat_widget.task_selected.connect(self._on_task_selected)

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
            self._reload_screen_settings()

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

        # Check if screen context should be injected
        screen_b64 = None
        if (
            self.orchestrator.config.screen_capture_vision
            and self._app_in_background
            and self._screen_service.is_available
        ):
            screen_b64 = self._screen_service.get_latest_base64()

        if screen_b64:
            # Route through attachment flow with screen context
            self.chat_widget.add_message(
                message + "\n🖥️ [Screen context included]", is_user=True
            )
            self.chat_widget.set_enabled(False)
            self.chat_widget.add_typing_indicator()
            self.sidebar.set_status("● Processing with screen context...")
            asyncio.create_task(
                self._process_message_with_screen(message, screen_b64)
            )
            return

        # Disable input during processing
        self.chat_widget.set_enabled(False)
        self.chat_widget.add_typing_indicator()

        # Show active task mode in status
        if self.orchestrator.active_task_category:
            cat = self.orchestrator.active_task_category
            preset = get_task_preset(cat)
            self.sidebar.set_status(f"● {preset.emoji} {preset.label} mode...")
        else:
            self.sidebar.set_status("● Processing...")

        # Process message asynchronously
        asyncio.create_task(self._process_message(message))

    def _on_message_sent_with_attachments(self, message: str, attachments: list):
        """Handle user message with file attachments."""
        if not self.orchestrator.is_ready:
            self.chat_widget.add_message(
                "Please configure your NVIDIA API key in Settings first.",
                is_user=False,
            )
            return

        # Disable input during processing
        self.chat_widget.set_enabled(False)
        self.chat_widget.add_typing_indicator()

        n = len(attachments)
        self.sidebar.set_status(f"● Processing {n} attachment{'s' if n > 1 else ''}...")

        asyncio.create_task(
            self._process_message_with_attachments(message, attachments)
        )

    def _on_task_selected(self, category_value: str):
        """Handle task preset button selection."""
        if not category_value:
            # Reset to default
            self.orchestrator.set_task_category(None)
            self.orchestrator.config.default_model = "meta/llama-3.1-8b-instruct"
            self.sidebar.set_model(self.orchestrator.config.default_model)
            self.sidebar.set_status("● Default mode")
            self.chat_widget.add_message(
                "🔄 Switched back to **default mode** (meta/llama-3.1-8b-instruct)",
                is_user=False,
            )
            return

        try:
            category = TaskCategory(category_value)
        except ValueError:
            return

        preset = get_task_preset(category)
        self.orchestrator.set_task_category(category)
        self.sidebar.set_model(preset.model)
        self.sidebar.set_status(f"● {preset.emoji} {preset.label} mode")

        # Notification bubble
        short_model = preset.model.split('/')[-1]
        self.chat_widget.add_message(
            f"{preset.emoji} **{preset.label} mode activated**\n"
            f"Model: `{short_model}`\n"
            f"{preset.description}",
            is_user=False,
        )

    async def _process_message(self, message: str):
        """Process message with agent using proper streaming (single bubble)."""
        import time
        response_text = ""
        ai_bubble: Optional[MessageBubble] = None
        last_render_time = 0.0
        RENDER_INTERVAL = 0.12  # seconds — throttle markdown re-renders

        try:
            self.sidebar.set_status("● Waiting for API...")

            async for chunk in self.orchestrator.process_message(message):
                response_text += chunk

                if ai_bubble is None:
                    # Remove typing indicator and create AI bubble on first chunk
                    self.chat_widget.remove_typing_indicator()
                    ai_bubble = self.chat_widget.begin_ai_response()
                    self.sidebar.set_status("● Streaming response...")

                # Throttle rendering to avoid lag during fast streaming
                now = time.monotonic()
                if now - last_render_time >= RENDER_INTERVAL:
                    self.chat_widget.update_ai_response(response_text)
                    last_render_time = now

                # Yield control to event loop for UI updates
                await asyncio.sleep(0)

            # Final render with complete text
            if ai_bubble is not None:
                self.chat_widget.update_ai_response(response_text)
                self.chat_widget.finish_ai_response()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error processing message: {e}")
            if ai_bubble is None:
                self.chat_widget.remove_typing_indicator()
                ai_bubble = self.chat_widget.begin_ai_response()
            status_code = e.response.status_code
            if status_code == 401:
                error_msg = "Invalid API key. Please update it in Settings."
            elif status_code == 429:
                error_msg = "Rate limited by NVIDIA API. Please wait a moment and try again."
            elif status_code == 404:
                error_msg = (
                    f"Model not found. The model '{self.orchestrator.config.default_model}' "
                    "may not be available. Try changing the model in Settings."
                )
            else:
                error_msg = f"API error (HTTP {status_code}): {e}"
            self.chat_widget.update_ai_response(f"Error: {error_msg}")

        except httpx.ConnectError:
            logger.error("Connection error processing message")
            if ai_bubble is None:
                self.chat_widget.remove_typing_indicator()
                ai_bubble = self.chat_widget.begin_ai_response()
            self.chat_widget.update_ai_response(
                "Connection failed. Please check your internet connection "
                "and the API base URL in Settings."
            )

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            if ai_bubble is None:
                self.chat_widget.remove_typing_indicator()
                ai_bubble = self.chat_widget.begin_ai_response()
            self.chat_widget.update_ai_response(f"Error: {str(e)}")

        finally:
            if ai_bubble is None:
                # No response at all — remove typing indicator
                self.chat_widget.remove_typing_indicator()
                self.chat_widget.add_message("No response received.", is_user=False)

            self.chat_widget.finish_ai_response()
            self.chat_widget.set_enabled(True)
            self._update_status()

    async def _process_message_with_attachments(
        self, message: str, attachments: List[str]
    ):
        """Process message with file attachments using multimodal API."""
        import time
        response_text = ""
        ai_bubble: Optional[MessageBubble] = None
        last_render_time = 0.0
        RENDER_INTERVAL = 0.12

        try:
            self.sidebar.set_status("● Analyzing attachments...")

            async for chunk in self.orchestrator.process_message_with_attachments(
                message, attachments
            ):
                response_text += chunk

                if ai_bubble is None:
                    self.chat_widget.remove_typing_indicator()
                    ai_bubble = self.chat_widget.begin_ai_response()
                    self.sidebar.set_status("● Streaming response...")

                now = time.monotonic()
                if now - last_render_time >= RENDER_INTERVAL:
                    self.chat_widget.update_ai_response(response_text)
                    last_render_time = now

                await asyncio.sleep(0)

            if ai_bubble is not None:
                self.chat_widget.update_ai_response(response_text)
                self.chat_widget.finish_ai_response()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error processing attachment message: {e}")
            if ai_bubble is None:
                self.chat_widget.remove_typing_indicator()
                ai_bubble = self.chat_widget.begin_ai_response()
            status_code = e.response.status_code
            if status_code == 401:
                error_msg = "Invalid API key. Please update it in Settings."
            elif status_code == 429:
                error_msg = "Rate limited. Please wait and try again."
            elif status_code == 404:
                error_msg = "Vision model not found. Try a different model."
            else:
                error_msg = f"API error (HTTP {status_code}): {e}"
            self.chat_widget.update_ai_response(f"Error: {error_msg}")

        except Exception as e:
            logger.error(f"Error processing attachment message: {e}")
            if ai_bubble is None:
                self.chat_widget.remove_typing_indicator()
                ai_bubble = self.chat_widget.begin_ai_response()
            self.chat_widget.update_ai_response(f"Error: {str(e)}")

        finally:
            if ai_bubble is None:
                self.chat_widget.remove_typing_indicator()
                self.chat_widget.add_message("No response received.", is_user=False)

            self.chat_widget.finish_ai_response()
            self.chat_widget.set_enabled(True)
            self._update_status()

    async def _process_message_with_screen(self, message: str, screen_b64: str):
        """Process message with screen context injected as a vision model image."""
        import time

        response_text = ""
        ai_bubble: Optional[MessageBubble] = None
        last_render_time = 0.0
        RENDER_INTERVAL = 0.12

        try:
            self.sidebar.set_status("● Analyzing screen...")

            async for chunk in self.orchestrator.process_message_with_screen(
                message, screen_b64
            ):
                response_text += chunk

                if ai_bubble is None:
                    self.chat_widget.remove_typing_indicator()
                    ai_bubble = self.chat_widget.begin_ai_response()
                    self.sidebar.set_status("● Streaming response...")

                now = time.monotonic()
                if now - last_render_time >= RENDER_INTERVAL:
                    self.chat_widget.update_ai_response(response_text)
                    last_render_time = now

                await asyncio.sleep(0)

            if ai_bubble is not None:
                self.chat_widget.update_ai_response(response_text)
                self.chat_widget.finish_ai_response()

        except Exception as e:
            logger.error(f"Error processing message with screen: {e}")
            if ai_bubble is None:
                self.chat_widget.remove_typing_indicator()
                ai_bubble = self.chat_widget.begin_ai_response()
            self.chat_widget.update_ai_response(f"Error: {str(e)}")

        finally:
            if ai_bubble is None:
                self.chat_widget.remove_typing_indicator()
                self.chat_widget.add_message("No response received.", is_user=False)

            self.chat_widget.finish_ai_response()
            self.chat_widget.set_enabled(True)
            self._update_status()

    # ─────────────────────────────────────────────────────────────────────
    # Gemini Live voice session
    # ─────────────────────────────────────────────────────────────────────

    def _on_voice_requested(self):
        """Handle voice mic button click — toggle Gemini Live session."""
        if self._is_recording:
            # Stop: tear down session
            self._is_recording = False
            asyncio.create_task(self._stop_gemini_session())
        else:
            # Start: check for Google API key, then launch session
            google_key = self._get_google_api_key()
            if not google_key:
                self.chat_widget.add_message(
                    "Google API key required for voice conversations. "
                    "Please add it in Settings > API tab.",
                    is_user=False,
                )
                self.chat_widget.voice_btn.setChecked(False)
                return
            self._is_recording = True
            self.chat_widget.set_voice_recording(True)
            asyncio.create_task(self._start_gemini_session(google_key))

    def _get_google_api_key(self):
        """Retrieve Google API key from keyring or config."""
        from src.utils.secure_storage import SecureStorage

        key = SecureStorage.get_google_api_key()
        if key:
            return key
        if self.orchestrator.config.google_api_key:
            return self.orchestrator.config.google_api_key
        return None

    async def _start_gemini_session(self, api_key: str):
        """Start full-duplex Gemini Live voice session."""
        import sounddevice as sd
        from src.api.gemini_live_client import (
            GeminiLiveClient,
            GeminiLiveConfig,
            GeminiLiveState,
        )

        try:
            self.sidebar.set_status("● Connecting to Gemini Live...")
            self.chat_widget.voice_indicator.setText("🐆  Connecting...")
            self.chat_widget.voice_indicator.setVisible(True)

            config = GeminiLiveConfig()
            self._gemini_client = GeminiLiveClient(api_key, config)

            # Wire state changes to UI updates
            self._gemini_client.on_state_change(self._on_gemini_state_change)

            await self._gemini_client.connect()

            # Update UI for active state
            self.chat_widget.voice_indicator.setText(
                "🐆  Gemini Live active — speak naturally, click mic to stop"
            )
            self.sidebar.set_status("● Gemini Live active")

            # Start mic input stream (16kHz, mono, int16)
            chunk_samples = int(
                config.input_sample_rate * config.chunk_duration_ms / 1000
            )
            audio_queue = asyncio.Queue()

            def mic_callback(indata, frames, time_info, status):
                if status:
                    logger.warning(f"Mic status: {status}")
                audio_queue.put_nowait(indata.copy().flatten())

            self._mic_stream = sd.InputStream(
                samplerate=config.input_sample_rate,
                channels=config.channels,
                dtype="int16",
                blocksize=chunk_samples,
                callback=mic_callback,
            )
            self._mic_stream.start()

            # Register OCR text callback if Gemini screen sharing is enabled
            if (
                self.orchestrator.config.screen_capture_gemini
                and self._screen_service.is_available
            ):
                def _on_ocr_text(text: str):
                    if self._gemini_client and self._is_recording:
                        asyncio.create_task(
                            self._gemini_client.send_text(
                                f"[Real-time screen context]: {text}"
                            )
                        )

                self._screen_ocr_callback = _on_ocr_text
                self._screen_service.on_ocr_text(_on_ocr_text)

            # Launch send + play + OCR tasks concurrently
            send_task = asyncio.create_task(
                self._gemini_send_loop(audio_queue)
            )
            play_task = asyncio.create_task(
                self._gemini_play_loop(config.output_sample_rate)
            )

            tasks = [send_task, play_task]

            # Add OCR loop if screen sharing enabled
            if (
                self.orchestrator.config.screen_capture_gemini
                and self._screen_service.is_available
            ):
                ocr_task = asyncio.create_task(self._gemini_ocr_loop())
                tasks.append(ocr_task)

            self._gemini_session_task = asyncio.gather(
                *tasks, return_exceptions=True
            )

            # Wait until session ends (user clicks stop or error)
            await self._gemini_session_task

        except Exception as e:
            logger.error(f"Gemini Live session error: {e}")
            error_msg = str(e)
            if "not installed" in error_msg:
                self.chat_widget.add_message(
                    "google-genai package not installed. "
                    "Run: pip install google-genai",
                    is_user=False,
                )
            elif "Invalid Google API key" in error_msg:
                self.chat_widget.add_message(
                    "Invalid Google API key. Please update it in Settings.",
                    is_user=False,
                )
            elif "PortAudio" in error_msg or "sounddevice" in error_msg:
                self.chat_widget.add_message(
                    "Microphone access denied or unavailable. "
                    "Please check your system audio settings.",
                    is_user=False,
                )
            else:
                self.chat_widget.add_message(
                    f"Voice session error: {error_msg}",
                    is_user=False,
                )
        finally:
            await self._cleanup_gemini()
            self._is_recording = False
            self.chat_widget.set_voice_recording(False)
            self._update_status()

    async def _gemini_send_loop(self, audio_queue: asyncio.Queue):
        """Continuously send mic audio to Gemini Live."""
        from src.api.gemini_live_client import GeminiLiveState

        while self._is_recording and self._gemini_client:
            if self._gemini_client.state != GeminiLiveState.ACTIVE:
                break
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.2)
                await self._gemini_client.send_audio(chunk)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Gemini send loop error: {e}")
                break

    async def _gemini_play_loop(self, output_sample_rate: int):
        """Continuously play audio received from Gemini Live."""
        import sounddevice as sd
        from src.api.gemini_live_client import GeminiLiveState

        while self._is_recording and self._gemini_client:
            if self._gemini_client.state != GeminiLiveState.ACTIVE:
                break
            try:
                async for audio_chunk in self._gemini_client.receive_audio():
                    if not self._is_recording:
                        break
                    # Play audio chunk (blocking call wrapped in executor)
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda c=audio_chunk, sr=output_sample_rate: sd.play(
                            c, sr, blocking=True
                        ),
                    )
            except Exception as e:
                logger.error(f"Gemini play loop error: {e}")
                break

    async def _gemini_ocr_loop(self):
        """Periodically capture screen, run OCR via NVIDIA, inject text into Gemini."""
        import base64 as b64_mod

        from src.api.gemini_live_client import GeminiLiveState

        while self._is_recording and self._gemini_client:
            if self._gemini_client.state != GeminiLiveState.ACTIVE:
                break

            # Only capture when app is in background
            if not self._app_in_background:
                await asyncio.sleep(1)
                continue

            try:
                # Capture screenshot in background thread
                frame = await asyncio.to_thread(
                    self._screen_service.capture_once,
                    self._screen_service.monitor,
                )
                if frame is None:
                    await asyncio.sleep(self._screen_service.interval)
                    continue

                # Run OCR via NVIDIA NIM vision model
                screen_b64 = b64_mod.b64encode(frame).decode("ascii")
                ocr_text = await self.orchestrator.extract_text_from_screen(screen_b64)

                if ocr_text:
                    # Dedup + fire callbacks (sends to Gemini via registered callback)
                    self._screen_service.set_ocr_text(ocr_text)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Gemini OCR loop error: {e}")

            await asyncio.sleep(self._screen_service.interval)

    async def _stop_gemini_session(self):
        """Stop Gemini Live session gracefully."""
        self._is_recording = False
        if self._gemini_session_task and not self._gemini_session_task.done():
            self._gemini_session_task.cancel()
            try:
                await self._gemini_session_task
            except asyncio.CancelledError:
                pass
        await self._cleanup_gemini()

    async def _cleanup_gemini(self):
        """Clean up all Gemini Live resources."""
        # Unregister screen frame callback (legacy)
        if self._screen_frame_callback:
            self._screen_service.remove_frame_callback(self._screen_frame_callback)
            self._screen_frame_callback = None

        # Unregister OCR text callback
        if self._screen_ocr_callback:
            self._screen_service.remove_ocr_callback(self._screen_ocr_callback)
            self._screen_ocr_callback = None

        if self._mic_stream:
            try:
                self._mic_stream.stop()
                self._mic_stream.close()
            except Exception:
                pass
            self._mic_stream = None

        if self._gemini_client:
            try:
                await self._gemini_client.disconnect()
            except Exception:
                pass
            self._gemini_client = None

        self._gemini_session_task = None
        self.chat_widget.voice_indicator.setVisible(False)

    def _on_gemini_state_change(self, state):
        """Handle Gemini Live state transitions for UI updates."""
        from src.api.gemini_live_client import GeminiLiveState

        if state == GeminiLiveState.CONNECTING:
            self.sidebar.set_status("● Connecting to Gemini...")
        elif state == GeminiLiveState.ACTIVE:
            self.sidebar.set_status("● Gemini Live active")
        elif state == GeminiLiveState.ERROR:
            error = (
                self._gemini_client.error_message
                if self._gemini_client
                else "Unknown"
            )
            self.sidebar.set_status(f"Voice error: {str(error)[:30]}")
        elif state == GeminiLiveState.IDLE:
            self._update_status()

    # ─────────────────────────────────────────────────────────────────────
    # Background detection & screen capture
    # ─────────────────────────────────────────────────────────────────────

    def changeEvent(self, event):
        """Detect window minimize / restore for background mode."""
        if event.type() == QEvent.Type.WindowStateChange:
            is_bg = self.isMinimized() or not self.isActiveWindow()
            self._on_app_background_changed(is_bg)
        super().changeEvent(event)

    def _on_app_state_changed(self, state):
        """Handle application-wide focus changes."""
        is_bg = state != Qt.ApplicationState.ApplicationActive
        self._on_app_background_changed(is_bg)

    def _on_app_background_changed(self, is_background: bool):
        """Update screen capture when app foreground/background state changes."""
        if is_background == self._app_in_background:
            return  # no change
        self._app_in_background = is_background
        self._screen_service.set_app_in_background(is_background)

        config = self.orchestrator.config
        screen_enabled = config.screen_capture_vision or config.screen_capture_gemini

        if not screen_enabled:
            return

        if is_background:
            self.sidebar.set_status("● Screen reading: ACTIVE")
        else:
            # Show brief pause notice then revert to normal status
            if self._is_recording:
                self.sidebar.set_status("● Gemini Live active (screen paused)")
            else:
                self.sidebar.set_status("● Screen reading: PAUSED")
                QTimer.singleShot(2000, self._update_status)

    def _reload_screen_settings(self):
        """Refresh screen service settings from config (called after settings save)."""
        config = self.orchestrator.config
        self._screen_service.vision_enabled = config.screen_capture_vision
        self._screen_service.gemini_enabled = config.screen_capture_gemini
        self._screen_service.monitor = config.screen_capture_monitor
        self._screen_service.interval = config.screen_capture_interval

    def closeEvent(self, event):
        """Handle window close."""
        self._screen_service.stop()
        if self._gemini_client:
            asyncio.create_task(self._cleanup_gemini())
        asyncio.create_task(self.orchestrator.close())
        event.accept()
