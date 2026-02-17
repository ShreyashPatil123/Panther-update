"""Tasks Panel - Active and completed task tracking UI."""
import asyncio
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from loguru import logger


class TasksPanel(QWidget):
    """Task status viewer and management panel."""

    def __init__(self, task_planner=None, parent=None):
        super().__init__(parent)
        self.task_planner = task_planner
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._refresh_tasks)
        self._refresh_timer.start(1000)  # Refresh every second
        self._setup_ui()

    def _setup_ui(self):
        """Setup tasks panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        header_layout = QHBoxLayout()
        header = QLabel("Task Management")
        header.setStyleSheet("font-size: 20px; font-weight: bold;")
        header_layout.addWidget(header)
        header_layout.addStretch()

        self.active_count = QLabel("0 active")
        self.active_count.setStyleSheet("color: #76b900; font-size: 13px;")
        header_layout.addWidget(self.active_count)
        layout.addLayout(header_layout)

        # Description
        desc = QLabel(
            "Complex multi-step tasks appear here with real-time progress tracking."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 13px;")
        layout.addWidget(desc)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #404040;")
        layout.addWidget(sep)

        # Splitter: task list (left) + task detail (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: tasks list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)

        active_label = QLabel("Tasks")
        active_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        left_layout.addWidget(active_label)

        self.tasks_list = QListWidget()
        self.tasks_list.setMinimumWidth(220)
        self.tasks_list.currentRowChanged.connect(self._on_task_selected)
        left_layout.addWidget(self.tasks_list)

        # Controls
        btn_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel Task")
        self.cancel_btn.setObjectName("secondary")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_selected)
        btn_layout.addWidget(self.cancel_btn)
        left_layout.addLayout(btn_layout)

        splitter.addWidget(left_widget)

        # Right: task detail
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)

        detail_label = QLabel("Task Details")
        detail_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        right_layout.addWidget(detail_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)

        # Task steps detail
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText(
            "Select a task to see its steps...\n\n"
            "Tasks are created when the agent plans complex multi-step operations."
        )
        self.detail_text.setStyleSheet("font-family: monospace; font-size: 12px;")
        right_layout.addWidget(self.detail_text)

        splitter.addWidget(right_widget)
        splitter.setSizes([240, 560])
        layout.addWidget(splitter)

    def _refresh_tasks(self):
        """Refresh task list from planner."""
        if not self.task_planner:
            return

        all_tasks = self.task_planner.get_all_tasks()
        active = [t for t in all_tasks if not t.is_complete]
        self.active_count.setText(f"{len(active)} active")

        # Rebuild list
        current_ids = set()
        for i in range(self.tasks_list.count()):
            item = self.tasks_list.item(i)
            if item:
                current_ids.add(item.data(Qt.ItemDataRole.UserRole))

        new_ids = {t.task_id for t in all_tasks}
        if current_ids != new_ids:
            selected_id = None
            current_item = self.tasks_list.currentItem()
            if current_item:
                selected_id = current_item.data(Qt.ItemDataRole.UserRole)

            self.tasks_list.clear()
            for task in reversed(all_tasks):  # newest first
                status_icons = {
                    "pending": "○",
                    "in_progress": "⟳",
                    "completed": "✓",
                    "failed": "✗",
                    "paused": "⏸",
                }
                icon = status_icons.get(task.status.value, "?")
                label = f"{icon} {task.goal[:40]}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, task.task_id)
                self.tasks_list.addItem(item)

                # Restore selection
                if task.task_id == selected_id:
                    self.tasks_list.setCurrentItem(item)

    def _on_task_selected(self, row: int):
        """Show task detail for selected task."""
        item = self.tasks_list.item(row)
        if not item:
            self.cancel_btn.setEnabled(False)
            return

        task_id = item.data(Qt.ItemDataRole.UserRole)
        if not task_id or not self.task_planner:
            return

        # Find task
        all_tasks = self.task_planner.get_all_tasks()
        task = next((t for t in all_tasks if t.task_id == task_id), None)
        if not task:
            return

        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(task.progress_pct)

        # Enable cancel for active tasks
        self.cancel_btn.setEnabled(not task.is_complete)

        # Show detail
        self.detail_text.setPlainText(task.get_summary())

    def _cancel_selected(self):
        """Cancel the selected task."""
        item = self.tasks_list.currentItem()
        if not item or not self.task_planner:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        if task_id:
            self.task_planner.cancel_task(task_id)
            self._refresh_tasks()

    def set_task_planner(self, planner):
        """Set the task planner."""
        self.task_planner = planner
