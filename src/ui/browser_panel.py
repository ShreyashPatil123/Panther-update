"""Browser Panel - Browser automation status, control UI, and live reasoning stream."""
import asyncio
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from loguru import logger


# ── Color palette for reasoning stream events ────────────────────────────────
_EVENT_COLORS = {
    "plan":   "#A78BFA",   # Violet
    "action": "#FFB347",   # Amber
    "status": "#60A5FA",   # Blue
    "result": "#34D399",   # Green
    "error":  "#F87171",   # Red
}


class BrowserPanel(QWidget):
    """Browser activity monitor, control panel, and live reasoning stream."""

    # Thread-safe signal: emitted from async/Playwright thread,
    # received on the Qt main thread to update UI widgets.
    live_stream_signal = pyqtSignal(dict)

    def __init__(self, browser_controller=None, parent=None):
        super().__init__(parent)
        self.browser_controller = browser_controller
        self._is_paused = False

        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._refresh_status)
        self._refresh_timer.start(2000)  # Refresh every 2s

        self._setup_ui()

        # Connect the thread-safe signal to the slot
        self.live_stream_signal.connect(self._on_live_stream_event)

    def _setup_ui(self):
        """Setup browser panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        header_layout = QHBoxLayout()
        header = QLabel("Browser Automation")
        header.setStyleSheet("font-size: 20px; font-weight: bold;")
        header_layout.addWidget(header)
        header_layout.addStretch()

        self.status_label = QLabel("● Idle")
        self.status_label.setStyleSheet("color: #FF6B35; font-size: 13px;")
        header_layout.addWidget(self.status_label)

        layout.addLayout(header_layout)

        # Description
        desc = QLabel(
            "The agent uses this browser for web tasks. "
            "Active tabs and screenshots appear here."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 13px;")
        layout.addWidget(desc)

        # ── Controls row ─────────────────────────────────────────────────
        controls_layout = QHBoxLayout()

        self.close_browser_btn = QPushButton("Close Browser")
        self.close_browser_btn.setObjectName("secondary")
        self.close_browser_btn.clicked.connect(self._close_browser)
        controls_layout.addWidget(self.close_browser_btn)

        self.pause_btn = QPushButton("⏸ Pause Agent")
        self.pause_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #FF6B35; color: white; border: none;"
            "  padding: 6px 16px; border-radius: 6px; font-weight: bold;"
            "}"
            "QPushButton:hover { background-color: #E55A2B; }"
        )
        self.pause_btn.clicked.connect(self._toggle_pause)
        controls_layout.addWidget(self.pause_btn)

        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #404040;")
        layout.addWidget(sep)

        # Splitter: tabs list (left) + screenshot (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: tabs list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)

        tabs_label = QLabel("Active Tabs")
        tabs_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        left_layout.addWidget(tabs_label)

        self.tabs_list = QListWidget()
        self.tabs_list.setMinimumWidth(220)
        self.tabs_list.currentRowChanged.connect(self._on_tab_selected)
        left_layout.addWidget(self.tabs_list)

        splitter.addWidget(left_widget)

        # Right: screenshot + page info
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)

        screenshot_label = QLabel("Screenshot")
        screenshot_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        right_layout.addWidget(screenshot_label)

        # Screenshot display
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.screenshot_widget = QLabel("No screenshot available")
        self.screenshot_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screenshot_widget.setStyleSheet("color: #666; padding: 20px;")
        self.screenshot_widget.setMinimumHeight(300)
        scroll.setWidget(self.screenshot_widget)
        right_layout.addWidget(scroll)

        # Page text preview
        page_label = QLabel("Page Content")
        page_label.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 8px;")
        right_layout.addWidget(page_label)

        self.page_text = QTextEdit()
        self.page_text.setReadOnly(True)
        self.page_text.setMaximumHeight(160)
        self.page_text.setPlaceholderText("Page content will appear here...")
        right_layout.addWidget(self.page_text)

        splitter.addWidget(right_widget)
        splitter.setSizes([240, 560])
        layout.addWidget(splitter)

        # ── Live Reasoning Stream ────────────────────────────────────────
        stream_sep = QFrame()
        stream_sep.setFrameShape(QFrame.Shape.HLine)
        stream_sep.setStyleSheet("color: #404040;")
        layout.addWidget(stream_sep)

        stream_header = QHBoxLayout()
        stream_label = QLabel("Live Reasoning Stream")
        stream_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        stream_header.addWidget(stream_label)
        stream_header.addStretch()

        clear_stream_btn = QPushButton("Clear")
        clear_stream_btn.setObjectName("secondary")
        clear_stream_btn.setFixedWidth(60)
        clear_stream_btn.clicked.connect(lambda: self.reasoning_stream.clear())
        stream_header.addWidget(clear_stream_btn)

        layout.addLayout(stream_header)

        self.reasoning_stream = QTextEdit()
        self.reasoning_stream.setReadOnly(True)
        self.reasoning_stream.setMinimumHeight(140)
        self.reasoning_stream.setMaximumHeight(250)
        self.reasoning_stream.setPlaceholderText(
            "Agent reasoning steps will appear here in real-time..."
        )
        self.reasoning_stream.setStyleSheet(
            "QTextEdit {"
            "  background-color: #1A1A2E; color: #E0E0E0; font-family: 'Consolas', monospace;"
            "  font-size: 12px; border: 1px solid #333; border-radius: 6px; padding: 8px;"
            "}"
        )
        layout.addWidget(self.reasoning_stream)

    # ── Pause / Resume toggle ────────────────────────────────────────────────

    def _toggle_pause(self):
        """Toggle between paused and running states."""
        if not self.browser_controller:
            return

        if self._is_paused:
            # Resume
            self.browser_controller.resume_agent()
            self._is_paused = False
            self.pause_btn.setText("⏸ Pause Agent")
            self.pause_btn.setStyleSheet(
                "QPushButton {"
                "  background-color: #FF6B35; color: white; border: none;"
                "  padding: 6px 16px; border-radius: 6px; font-weight: bold;"
                "}"
                "QPushButton:hover { background-color: #E55A2B; }"
            )
            self._append_stream_message("status", "▶ Agent resumed by user")
        else:
            # Pause
            self.browser_controller.pause_agent()
            self._is_paused = True
            self.pause_btn.setText("▶ Resume Agent")
            self.pause_btn.setStyleSheet(
                "QPushButton {"
                "  background-color: #34D399; color: white; border: none;"
                "  padding: 6px 16px; border-radius: 6px; font-weight: bold;"
                "}"
                "QPushButton:hover { background-color: #2AB887; }"
            )
            self._append_stream_message("status", "⏸ Agent paused by user")

    # ── Live Reasoning Stream ────────────────────────────────────────────────

    def update_live_stream(self, event_dict: dict):
        """
        Thread-safe entry point: emit the signal so the slot runs on the
        Qt main thread. Call this from any thread (e.g. the Playwright loop).
        """
        self.live_stream_signal.emit(event_dict)

    def _on_live_stream_event(self, event_dict: dict):
        """Slot: receives event_dict on the Qt main thread and appends it."""
        event_type = event_dict.get("type", "action")
        message = event_dict.get("message", "")
        self._append_stream_message(event_type, message)

    def _append_stream_message(self, event_type: str, message: str):
        """Append a color-coded, timestamped message to the reasoning stream."""
        color = _EVENT_COLORS.get(event_type, "#E0E0E0")
        timestamp = datetime.now().strftime("%H:%M:%S")

        cursor = self.reasoning_stream.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Timestamp in grey
        fmt_time = QTextCharFormat()
        fmt_time.setForeground(QColor("#666"))
        cursor.insertText(f"[{timestamp}] ", fmt_time)

        # Message in event color
        fmt_msg = QTextCharFormat()
        fmt_msg.setForeground(QColor(color))
        cursor.insertText(f"{message}\n", fmt_msg)

        # Auto-scroll to bottom
        self.reasoning_stream.setTextCursor(cursor)
        self.reasoning_stream.ensureCursorVisible()

    # ── Status refresh ───────────────────────────────────────────────────────

    def _refresh_status(self):
        """Refresh browser status from controller."""
        if not self.browser_controller:
            return

        pages = getattr(self.browser_controller, "_pages", {})
        if pages:
            self.status_label.setText(f"● Active ({len(pages)} tab{'s' if len(pages) > 1 else ''})")
            self.status_label.setStyleSheet("color: #FFB347; font-size: 13px;")
        else:
            self.status_label.setText("● Idle")
            self.status_label.setStyleSheet("color: #FF6B35; font-size: 13px;")

        # Refresh tabs list
        current_tabs = set(pages.keys())
        listed_tabs = set()
        for i in range(self.tabs_list.count()):
            item = self.tabs_list.item(i)
            if item:
                listed_tabs.add(item.data(Qt.ItemDataRole.UserRole))

        if current_tabs != listed_tabs:
            self.tabs_list.clear()
            for page_id in pages:
                item = QListWidgetItem(f"🌐 {page_id}")
                item.setData(Qt.ItemDataRole.UserRole, page_id)
                self.tabs_list.addItem(item)

    def _on_tab_selected(self, row: int):
        """Show screenshot for selected tab."""
        item = self.tabs_list.item(row)
        if not item:
            return
        page_id = item.data(Qt.ItemDataRole.UserRole)
        asyncio.create_task(self._load_screenshot(page_id))

    async def _load_screenshot(self, page_id: str):
        """Load screenshot from browser page."""
        if not self.browser_controller:
            return
        try:
            screenshot_bytes = await self.browser_controller.take_screenshot(page_id=page_id)
            pixmap = QPixmap()
            pixmap.loadFromData(screenshot_bytes)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.screenshot_widget.width(),
                    400,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.screenshot_widget.setPixmap(scaled)

            # Load page text
            text = await self.browser_controller.get_text("body", page_id=page_id)
            self.page_text.setPlainText(text[:1000] if text else "")
        except Exception as e:
            logger.debug(f"Screenshot error for {page_id}: {e}")

    def _close_browser(self):
        """Close browser."""
        if self.browser_controller:
            asyncio.create_task(self._do_close_browser())

    async def _do_close_browser(self):
        """Async browser close."""
        try:
            await self.browser_controller.shutdown()
            self.tabs_list.clear()
            self.screenshot_widget.setText("Browser closed")
            self.status_label.setText("● Idle")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")

    def set_browser_controller(self, controller):
        """Set the browser controller."""
        self.browser_controller = controller

    def show_screenshot(self, screenshot_bytes: bytes):
        """Display a screenshot (called from agent during task execution)."""
        pixmap = QPixmap()
        pixmap.loadFromData(screenshot_bytes)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                800, 500,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.screenshot_widget.setPixmap(scaled)
