"""Custom UI widgets for the application."""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)


class MessageBubble(QFrame):
    """Message bubble widget for chat."""

    def __init__(self, text: str, is_user: bool = False, parent=None):
        super().__init__(parent)
        self.text = text
        self.is_user = is_user
        self._setup_ui()

    def _setup_ui(self):
        """Setup message bubble UI."""
        # Set object name for styling
        self.setObjectName("userMessage" if self.is_user else "aiMessage")

        # Main layout
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # Spacer for alignment
        if self.is_user:
            main_layout.addSpacerItem(
                QSpacerItem(100, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            )

        # Message container
        self.container = QFrame()
        self.container.setObjectName("userMessage" if self.is_user else "aiMessage")
        self.container.setStyleSheet(
            f"""
            QFrame#userMessage {{
                background-color: #2d3748;
                border-radius: 12px;
                padding: 12px;
                max-width: 700px;
            }}
            QFrame#aiMessage {{
                background-color: #1e3a5f;
                border-radius: 12px;
                padding: 12px;
                max-width: 700px;
            }}
        """
        )

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 10, 12, 10)
        container_layout.setSpacing(4)

        # Message text
        self.label = QLabel(self.text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.label.setStyleSheet(
            f"""
            QLabel {{
                color: {'white' if self.is_user else '#e0e0e0'};
                font-size: 14px;
                line-height: 1.5;
            }}
        """
        )
        container_layout.addWidget(self.label)

        main_layout.addWidget(self.container)

        # Spacer for alignment
        if not self.is_user:
            main_layout.addSpacerItem(
                QSpacerItem(100, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            )

        self.setLayout(main_layout)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background: transparent;")

    def set_text(self, text: str):
        """Update message text."""
        self.text = text
        self.label.setText(text)


class TypingIndicator(QFrame):
    """Typing indicator with animated dots."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dots = 0
        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self):
        """Setup typing indicator UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        # Container
        container = QFrame()
        container.setStyleSheet(
            """
            QFrame {
                background-color: #1e3a5f;
                border-radius: 12px;
                padding: 8px 16px;
            }
        """
        )

        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(12, 8, 12, 8)
        container_layout.setSpacing(4)

        # Dots
        self.dot_labels = []
        for i in range(3):
            dot = QLabel("")
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(
                f"""
                QLabel {{
                    background-color: {'#76b900' if i == 0 else '#555'};
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
        """Animate typing dots."""
        self._dots = (self._dots + 1) % 4

        for i, dot in enumerate(self.dot_labels):
            if i < self._dots:
                dot.setStyleSheet(
                    """
                    QLabel {
                        background-color: #76b900;
                        border-radius: 4px;
                    }
                """
                )
            else:
                dot.setStyleSheet(
                    """
                    QLabel {
                        background-color: #555;
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
        self.title_label.setStyleSheet("font-weight: 500; font-size: 13px;")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        # Timestamp
        self.time_label = QLabel(self.timestamp)
        self.time_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.time_label)

        self.setStyleSheet(
            """
            QWidget {
                background: transparent;
                border-radius: 6px;
            }
            QWidget:hover {
                background: #3d3d3d;
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
                background-color: #1a1a1a;
                border-radius: 8px;
                border: 1px solid #333;
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
            lang_label.setStyleSheet("color: #888; font-size: 12px;")
            header.addWidget(lang_label)

        header.addStretch()

        copy_btn = QPushButton("Copy")
        copy_btn.setFixedWidth(60)
        copy_btn.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                color: #888;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #333;
                color: #fff;
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
                color: #e0e0e0;
                font-family: 'Consolas', 'Monaco', monospace;
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
