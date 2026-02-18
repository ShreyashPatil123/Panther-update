"""Files Panel - File system browser and permission management UI."""
import asyncio
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from src.capabilities.files import PermissionType


class FilesPanel(QWidget):
    """File system browser with permission management."""

    permission_requested = pyqtSignal(str, str)  # path, permission_type

    def __init__(self, files_manager=None, parent=None):
        super().__init__(parent)
        self.files_manager = files_manager
        self._setup_ui()
        self._refresh_allowed_paths()

    def _setup_ui(self):
        """Setup files panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        header = QLabel("File System Access")
        header.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(header)

        # Description
        desc = QLabel(
            "Manage which folders the agent can access. "
            "Click 'Add Folder' to grant permissions."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 13px;")
        layout.addWidget(desc)

        # Add folder button
        add_btn = QPushButton("+ Add Folder")
        add_btn.setFixedHeight(36)
        add_btn.clicked.connect(self._add_folder)
        layout.addWidget(add_btn)

        # Splitter: left = allowed paths, right = file browser
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: allowed paths list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)

        left_label = QLabel("Allowed Folders")
        left_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        left_layout.addWidget(left_label)

        self.paths_list = QListWidget()
        self.paths_list.setMinimumWidth(220)
        self.paths_list.currentRowChanged.connect(self._on_path_selected)
        left_layout.addWidget(self.paths_list)

        # Revoke button
        revoke_btn = QPushButton("Remove Access")
        revoke_btn.setObjectName("secondary")
        revoke_btn.clicked.connect(self._revoke_selected)
        left_layout.addWidget(revoke_btn)

        splitter.addWidget(left_widget)

        # Right: file tree / content viewer
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)

        right_label = QLabel("Contents")
        right_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        right_layout.addWidget(right_label)

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["Name", "Size", "Type"])
        self.file_tree.setColumnWidth(0, 260)
        self.file_tree.setColumnWidth(1, 100)
        self.file_tree.itemDoubleClicked.connect(self._on_file_double_clicked)
        right_layout.addWidget(self.file_tree)

        # File content preview
        preview_label = QLabel("Preview")
        preview_label.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 8px;")
        right_layout.addWidget(preview_label)

        self.content_preview = QTextEdit()
        self.content_preview.setReadOnly(True)
        self.content_preview.setMaximumHeight(180)
        self.content_preview.setPlaceholderText("Double-click a file to preview it...")
        self.content_preview.setStyleSheet("font-family: monospace; font-size: 12px;")
        right_layout.addWidget(self.content_preview)

        splitter.addWidget(right_widget)
        splitter.setSizes([240, 560])
        layout.addWidget(splitter)

    def _refresh_allowed_paths(self):
        """Refresh the list of allowed paths."""
        self.paths_list.clear()
        if self.files_manager is None:
            # Show default paths as demo
            default_paths = [
                ("~/Documents", "RW"),
                ("~/Downloads", "R"),
                ("~/Desktop", "R"),
            ]
            for path, perm in default_paths:
                item = QListWidgetItem(f"📁 {path}  [{perm}]")
                self.paths_list.addItem(item)
            return

        asyncio.create_task(self._async_refresh_allowed_paths())

    async def _async_refresh_allowed_paths(self):
        """Load allowed paths asynchronously."""
        try:
            paths = await self.files_manager.get_allowed_paths()
            self.paths_list.clear()
            for p in paths:
                item = QListWidgetItem(f"📁 {p}  [RW]")
                item.setData(Qt.ItemDataRole.UserRole, str(p))
                self.paths_list.addItem(item)
        except Exception as e:
            logger.error(f"Failed to refresh paths: {e}")

    def _add_folder(self):
        """Open folder dialog to add a new permitted path."""
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to Allow Access",
            str(Path.home()),
        )
        if path and self.files_manager:
            asyncio.create_task(self.files_manager.request_permission(
                path, PermissionType.READ, recursive=True
            ))
            self._refresh_allowed_paths()
            logger.info(f"Added folder permission: {path}")
        elif path:
            # No manager yet, just show in list
            item = QListWidgetItem(f"📁 {path}  [R]")
            self.paths_list.addItem(item)

    def _revoke_selected(self):
        """Revoke permission for the selected path."""
        current = self.paths_list.currentItem()
        if not current:
            return
        path = current.data(Qt.ItemDataRole.UserRole)
        if path and self.files_manager:
            asyncio.create_task(self.files_manager.revoke_permission(
                path, PermissionType.READ
            ))
            self._refresh_allowed_paths()

    def _on_path_selected(self, row: int):
        """Show files in the selected path."""
        item = self.paths_list.item(row)
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            asyncio.create_task(self._load_directory(path))

    async def _load_directory(self, path: str):
        """Load directory contents into tree."""
        self.file_tree.clear()
        if not self.files_manager:
            return
        try:
            file_infos = await self.files_manager.list_directory(path)
            for fi in file_infos[:200]:
                icon = "📁" if fi.is_directory else "📄"
                size_str = f"{fi.size:,}" if not fi.is_directory else ""
                file_type = "Directory" if fi.is_directory else (fi.mime_type or "File")
                item = QTreeWidgetItem([f"{icon} {fi.name}", size_str, file_type])
                item.setData(0, Qt.ItemDataRole.UserRole, fi.path)
                self.file_tree.addTopLevelItem(item)
        except Exception as e:
            logger.error(f"Failed to load directory {path}: {e}")

    def _on_file_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Preview file content."""
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and self.files_manager:
            asyncio.create_task(self._preview_file(path))

    async def _preview_file(self, path: str):
        """Load file preview."""
        try:
            content = await self.files_manager.read_file(path)
            preview = content[:2000]
            if len(content) > 2000:
                preview += f"\n\n... ({len(content) - 2000} more chars)"
            self.content_preview.setPlainText(preview)
        except Exception as e:
            self.content_preview.setPlainText(f"Error reading file: {e}")

    def set_files_manager(self, manager):
        """Set the file system manager."""
        self.files_manager = manager
        self._refresh_allowed_paths()
