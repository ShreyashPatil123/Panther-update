"""Browser Panel - Browser automation status and control UI."""
import asyncio
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
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


class BrowserPanel(QWidget):
    """Browser activity monitor and control panel."""

    def __init__(self, browser_controller=None, parent=None):
        super().__init__(parent)
        self.browser_controller = browser_controller
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._refresh_status)
        self._refresh_timer.start(2000)  # Refresh every 2s
        self._setup_ui()

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
        self.status_label.setStyleSheet("color: #76b900; font-size: 13px;")
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

        # Controls
        controls_layout = QHBoxLayout()
        self.close_browser_btn = QPushButton("Close Browser")
        self.close_browser_btn.setObjectName("secondary")
        self.close_browser_btn.clicked.connect(self._close_browser)
        controls_layout.addWidget(self.close_browser_btn)
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

    def _refresh_status(self):
        """Refresh browser status from controller."""
        if not self.browser_controller:
            return

        pages = getattr(self.browser_controller, "_pages", {})
        if pages:
            self.status_label.setText(f"● Active ({len(pages)} tab{'s' if len(pages) > 1 else ''})")
            self.status_label.setStyleSheet("color: #00d4aa; font-size: 13px;")
        else:
            self.status_label.setText("● Idle")
            self.status_label.setStyleSheet("color: #76b900; font-size: 13px;")

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
