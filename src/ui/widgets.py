"""Custom UI widgets — panther orange resin theme."""
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from src.ui.chat_renderer import render_markdown, render_user_message


class MessageBubble(QFrame):
    """Message bubble widget for chat.

    User messages: styled plain-text bubble (right-aligned).
    AI messages: rich HTML via QTextBrowser with markdown, code, thinking (left-aligned).
    """

    def __init__(self, text: str, is_user: bool = False, parent=None):
        super().__init__(parent)
        self.text = text
        self.is_user = is_user
        self._setup_ui()

    def _setup_ui(self):
        """Setup message bubble UI."""
        self.setObjectName("userMessage" if self.is_user else "aiMessage")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background: transparent;")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        if self.is_user:
            # ── User message: right-aligned pill ──
            main_layout.addSpacerItem(
                QSpacerItem(100, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            )

            self.container = QFrame()
            self.container.setObjectName("userMessage")
            self.container.setStyleSheet("""
                QFrame#userMessage {
                    background-color: #1e1a14;
                    border-radius: 16px;
                    border: 1px solid #2a2218;
                    padding: 0;
                    max-width: 700px;
                }
            """)

            container_layout = QVBoxLayout(self.container)
            container_layout.setContentsMargins(16, 12, 16, 12)
            container_layout.setSpacing(0)

            self.label = QLabel()
            self.label.setWordWrap(True)
            self.label.setTextFormat(Qt.TextFormat.RichText)
            self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.label.setStyleSheet("""
                QLabel {
                    color: #f0ece8;
                    font-size: 14px;
                    line-height: 1.5;
                    background: transparent;
                }
            """)
            self.label.setText(render_user_message(self.text))
            container_layout.addWidget(self.label)

            main_layout.addWidget(self.container)

        else:
            # ── AI message: full-width rich HTML ──
            self.container = QFrame()
            self.container.setObjectName("aiMessage")
            self.container.setStyleSheet("""
                QFrame#aiMessage {
                    background: transparent;
                    border: none;
                    padding: 0;
                }
            """)

            container_layout = QVBoxLayout(self.container)
            container_layout.setContentsMargins(8, 4, 8, 4)
            container_layout.setSpacing(0)

            # Role label — orange resin accent
            role_label = QLabel("✦ Assistant")
            role_label.setStyleSheet("""
                QLabel {
                    color: #FF6B35;
                    font-size: 12px;
                    font-weight: bold;
                    margin-bottom: 4px;
                    background: transparent;
                }
            """)
            container_layout.addWidget(role_label)

            # Rich text browser
            self.text_browser = QTextBrowser()
            self.text_browser.setOpenExternalLinks(False)
            self.text_browser.anchorClicked.connect(
                lambda url: QDesktopServices.openUrl(url)
            )
            self.text_browser.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            self.text_browser.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            self.text_browser.setStyleSheet("""
                QTextBrowser {
                    background: transparent;
                    border: none;
                    color: #e8e0d8;
                    font-family: 'Inter', 'Segoe UI', sans-serif;
                    font-size: 14px;
                    selection-background-color: #FF6B35;
                }
            """)
            self.text_browser.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )

            # Set initial content
            if self.text:
                self.text_browser.setHtml(render_markdown(self.text))

            # Auto-resize to content
            self.text_browser.document().contentsChanged.connect(self._adjust_height)
            self._adjust_height()

            container_layout.addWidget(self.text_browser)

            main_layout.addWidget(self.container)

            # Right spacer for AI messages (leave some right margin)
            main_layout.addSpacerItem(
                QSpacerItem(40, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
            )

    def _adjust_height(self):
        """Auto-resize QTextBrowser to fit content without scrollbar."""
        if hasattr(self, "text_browser"):
            doc_height = self.text_browser.document().size().toSize().height()
            self.text_browser.setFixedHeight(max(doc_height + 10, 30))

    def set_text(self, text: str):
        """Update message text."""
        self.text = text
        if self.is_user:
            self.label.setText(render_user_message(text))
        else:
            self.text_browser.setHtml(render_markdown(text))
            self._adjust_height()


class TypingIndicator(QFrame):
    """Typing indicator with animated orange dots."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dots = 0
        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self):
        """Setup typing indicator UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        # Container — warm dark with orange tint
        container = QFrame()
        container.setStyleSheet(
            """
            QFrame {
                background-color: #1a1510;
                border-radius: 14px;
                border: 1px solid #2a2218;
                padding: 8px 16px;
            }
        """
        )

        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(12, 8, 12, 8)
        container_layout.setSpacing(6)

        # Dots — orange resin
        self.dot_labels = []
        for i in range(3):
            dot = QLabel("")
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(
                f"""
                QLabel {{
                    background-color: {'#FF6B35' if i == 0 else '#3a2818'};
                    border-radius: 4px;
                }}
            """
            )
            container_layout.addWidget(dot)
            self.dot_labels.append(dot)

        layout.addWidget(container)
        layout.addStretch()

        self.setStyleSheet("background: transparent;")
        self.setFrameShape(QFrame.Shape.NoFrame)

    def _setup_timer(self):
        """Setup animation timer."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(400)

    def _animate(self):
        """Animate typing dots with orange resin glow."""
        self._dots = (self._dots + 1) % 4

        for i, dot in enumerate(self.dot_labels):
            if i < self._dots:
                dot.setStyleSheet(
                    """
                    QLabel {
                        background-color: #FF6B35;
                        border-radius: 4px;
                    }
                """
                )
            else:
                dot.setStyleSheet(
                    """
                    QLabel {
                        background-color: #3a2818;
                        border-radius: 4px;
                    }
                """
                )

    def showEvent(self, event):
        """Handle show event."""
        super().showEvent(event)
        self.timer.start()

    def hideEvent(self, event):
        """Handle hide event."""
        super().hideEvent(event)
        self.timer.stop()


class SessionItem(QWidget):
    """Session item widget for sidebar."""

    def __init__(self, title: str, timestamp: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.timestamp = timestamp
        self._setup_ui()

    def _setup_ui(self):
        """Setup session item UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        # Title
        self.title_label = QLabel(self.title)
        self.title_label.setStyleSheet("font-weight: 500; font-size: 13px; color: #f0ece8;")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        # Timestamp
        self.time_label = QLabel(self.timestamp)
        self.time_label.setStyleSheet("color: #8a8078; font-size: 11px;")
        layout.addWidget(self.time_label)

        self.setStyleSheet(
            """
            QWidget {
                background: transparent;
                border-radius: 8px;
            }
            QWidget:hover {
                background: #1a1712;
            }
        """
        )


class CodeBlock(QFrame):
    """Code block widget with copy button."""

    def __init__(self, code: str, language: str = "", parent=None):
        super().__init__(parent)
        self.code = code
        self.language = language
        self._setup_ui()

    def _setup_ui(self):
        """Setup code block UI."""
        self.setStyleSheet(
            """
            QFrame {
                background-color: #0f0e0c;
                border-radius: 10px;
                border: 1px solid #2a2218;
            }
        """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)

        # Header with language and copy button
        header = QHBoxLayout()

        if self.language:
            lang_label = QLabel(self.language)
            lang_label.setStyleSheet("color: #FF6B35; font-size: 12px; font-weight: 600;")
            header.addWidget(lang_label)

        header.addStretch()

        copy_btn = QPushButton("Copy")
        copy_btn.setFixedWidth(60)
        copy_btn.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                color: #8a8078;
                border: 1px solid #2a2218;
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #1a1510;
                color: #FFB347;
                border-color: #FF6B35;
            }
        """
        )
        copy_btn.clicked.connect(self._copy_code)
        header.addWidget(copy_btn)

        layout.addLayout(header)

        # Code text
        self.code_label = QLabel(self.code)
        self.code_label.setWordWrap(True)
        self.code_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.code_label.setStyleSheet(
            """
            QLabel {
                color: #e8e0d8;
                font-family: 'Cascadia Code', 'Consolas', 'Monaco', monospace;
                font-size: 13px;
                line-height: 1.5;
            }
        """
        )
        layout.addWidget(self.code_label)

    def _copy_code(self):
        """Copy code to clipboard."""
        from PyQt6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        clipboard.setText(self.code)

        # Visual feedback
        sender = self.sender()
        if sender:
            original_text = sender.text()
            sender.setText("Copied!")
            QTimer.singleShot(1500, lambda: sender.setText(original_text))
