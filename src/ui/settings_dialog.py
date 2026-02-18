"""Settings dialog for NVIDIA AI Agent."""
import asyncio
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from src.core.agent import AgentOrchestrator
from src.utils.secure_storage import SecureStorage


class SettingsDialog(QDialog):
    """Settings dialog for configuration."""

    settings_changed = pyqtSignal()

    def __init__(self, orchestrator: AgentOrchestrator, parent=None):
        super().__init__(parent)
        self.orchestrator = orchestrator
        self.setWindowTitle("Settings")
        self.setMinimumSize(600, 500)
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """Setup dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # API tab
        self.api_tab = self._create_api_tab()
        self.tabs.addTab(self.api_tab, "API")

        # Model tab
        self.model_tab = self._create_model_tab()
        self.tabs.addTab(self.model_tab, "Model")

        # Memory tab
        self.memory_tab = self._create_memory_tab()
        self.tabs.addTab(self.memory_tab, "Memory")

        # Button box
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self._apply_settings
        )
        layout.addWidget(self.button_box)

    def _create_api_tab(self) -> QWidget:
        """Create API settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing(12)

        # API Key
        api_key_layout = QHBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Enter your NVIDIA API key")
        api_key_layout.addWidget(self.api_key_input)

        self.show_key_btn = QPushButton("Show")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.toggled.connect(self._toggle_api_key_visibility)
        api_key_layout.addWidget(self.show_key_btn)

        layout.addRow("NVIDIA API Key:", api_key_layout)

        # Test connection button
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._test_connection)
        layout.addRow("", self.test_btn)

        # Base URL
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText(
            "https://integrate.api.nvidia.com/v1"
        )
        layout.addRow("Base URL:", self.base_url_input)

        # Status label
        self.status_label = QLabel("Not configured")
        self.status_label.setStyleSheet("color: #ff5252;")
        layout.addRow("Status:", self.status_label)

        return widget

    def _create_model_tab(self) -> QWidget:
        """Create model settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing(12)

        # Model selection
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems([
            "meta/llama-3.1-8b-instruct",
            "meta/llama-3.1-70b-instruct",
            "meta/llama-3.1-405b-instruct",
            "meta/llama-3.3-70b-instruct",
            "mistralai/mistral-large-2-instruct",
            "mistralai/mistral-7b-instruct-v0.3",
            "google/gemma-2-27b-it",
            "nvidia/nemotron-4-340b-instruct",
        ])
        layout.addRow("Model:", self.model_combo)

        # Temperature
        self.temp_spin = QSpinBox()
        self.temp_spin.setRange(0, 100)
        self.temp_spin.setValue(70)
        self.temp_spin.setSuffix("%")
        layout.addRow("Temperature:", self.temp_spin)

        # Max tokens
        self.tokens_spin = QSpinBox()
        self.tokens_spin.setRange(256, 8192)
        self.tokens_spin.setSingleStep(256)
        self.tokens_spin.setValue(4096)
        layout.addRow("Max Tokens:", self.tokens_spin)

        return widget

    def _create_memory_tab(self) -> QWidget:
        """Create memory settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        # Storage location
        storage_group = QGroupBox("Storage")
        storage_layout = QFormLayout(storage_group)

        db_path_layout = QHBoxLayout()
        self.db_path_input = QLineEdit()
        self.db_path_input.setReadOnly(True)
        db_path_layout.addWidget(self.db_path_input)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_db_path)
        db_path_layout.addWidget(browse_btn)

        storage_layout.addRow("Database Path:", db_path_layout)
        layout.addWidget(storage_group)

        # Memory options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self.encrypt_check = QCheckBox("Encrypt local storage")
        self.encrypt_check.setChecked(True)
        options_layout.addWidget(self.encrypt_check)

        self.local_check = QCheckBox("Local processing only")
        options_layout.addWidget(self.local_check)

        layout.addWidget(options_group)

        # Clear memory button
        clear_btn = QPushButton("Clear All Memory")
        clear_btn.setStyleSheet(
            "QPushButton { background-color: #ff5252; color: white; }"
        )
        clear_btn.clicked.connect(self._clear_memory)
        layout.addWidget(clear_btn)

        layout.addStretch()

        return widget

    def _load_settings(self):
        """Load current settings."""
        config = self.orchestrator.config

        # Load API key from secure storage
        stored_key = SecureStorage.get_api_key()
        if stored_key:
            self.api_key_input.setText(stored_key)
            self.status_label.setText("Configured")
            self.status_label.setStyleSheet("color: #4caf50;")

        # Base URL
        self.base_url_input.setText(config.nvidia_base_url)

        # Database path
        self.db_path_input.setText(str(config.db_path))

        # Model
        model_index = self.model_combo.findText(config.default_model)
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)
        else:
            self.model_combo.setCurrentText(config.default_model)

    def _toggle_api_key_visibility(self, checked: bool):
        """Toggle API key visibility."""
        if checked:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_key_btn.setText("Hide")
        else:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_key_btn.setText("Show")

    def _browse_db_path(self):
        """Browse for database path."""
        path = QFileDialog.getExistingDirectory(
            self, "Select Database Directory", str(Path.home())
        )
        if path:
            self.db_path_input.setText(str(Path(path) / "agent.db"))

    def _test_connection(self):
        """Test API connection."""
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Warning", "Please enter an API key")
            return

        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing...")
        self.status_label.setText("Testing...")
        self.status_label.setStyleSheet("color: #ffc107;")

        # Test asynchronously
        asyncio.create_task(self._do_test_connection(api_key))

    async def _do_test_connection(self, api_key: str):
        """Perform connection test using health check."""
        from src.api.nvidia_client import NVIDIAClient

        base_url = self.base_url_input.text().strip() or "https://integrate.api.nvidia.com/v1"
        client = NVIDIAClient(api_key=api_key, base_url=base_url)
        try:
            health = await client.check_health()

            if health["ok"]:
                latency = health["latency_ms"]
                models = health["model_count"]
                self.status_label.setText(
                    f"Connected ({latency:.0f}ms, {models} models)"
                )
                self.status_label.setStyleSheet("color: #4caf50;")
                QMessageBox.information(
                    self,
                    "Success",
                    f"API connection successful!\n\n"
                    f"Latency: {latency:.0f}ms\n"
                    f"Available models: {models}",
                )
            else:
                error = health.get("error", "Unknown error")
                self.status_label.setText(f"Failed: {error[:40]}")
                self.status_label.setStyleSheet("color: #ff5252;")
                QMessageBox.critical(
                    self,
                    "Connection Failed",
                    f"Could not connect to NVIDIA NIM API.\n\n"
                    f"Error: {error}\n\n"
                    f"Please verify:\n"
                    f"• Your API key is correct\n"
                    f"• The base URL is correct\n"
                    f"• You have internet connectivity",
                )
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)[:50]}")
            self.status_label.setStyleSheet("color: #ff5252;")
            QMessageBox.critical(self, "Error", f"Connection failed: {str(e)}")
        finally:
            await client.close()
            self.test_btn.setEnabled(True)
            self.test_btn.setText("Test Connection")

    def _clear_memory(self):
        """Clear all memory."""
        reply = QMessageBox.question(
            self,
            "Confirm",
            "Are you sure you want to clear all memory? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            asyncio.create_task(self._do_clear_memory())

    async def _do_clear_memory(self):
        """Clear memory asynchronously."""
        try:
            await self.orchestrator.memory.clear_session()
            QMessageBox.information(self, "Success", "All memory cleared!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to clear memory: {str(e)}")

    def _apply_settings(self):
        """Apply settings without closing dialog."""
        self._save_settings()
        QMessageBox.information(self, "Success", "Settings applied!")

    def _save_settings(self):
        """Save settings."""
        # Save API key
        api_key = self.api_key_input.text().strip()
        if api_key:
            SecureStorage.store_api_key(api_key)
            self.orchestrator.set_api_key(api_key)

        # Save base URL
        base_url = self.base_url_input.text().strip()
        if base_url:
            self.orchestrator.config.nvidia_base_url = base_url

        # Save model selection
        model = self.model_combo.currentText().strip()
        if model:
            self.orchestrator.config.default_model = model

        # Update status
        if self.orchestrator.is_ready:
            self.status_label.setText("Configured")
            self.status_label.setStyleSheet("color: #4caf50;")

        self.settings_changed.emit()
        logger.info("Settings saved")

    def accept(self):
        """Handle OK button."""
        self._save_settings()
        super().accept()
