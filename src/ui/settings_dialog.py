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

        # Screen tab
        self.screen_tab = self._create_screen_tab()
        self.tabs.addTab(self.screen_tab, "Screen")

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
        self.status_label.setStyleSheet("color: #FF4500;")
        layout.addRow("Status:", self.status_label)

        # --- Separator ---
        from PyQt6.QtWidgets import QFrame
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: #2a2218; max-height: 1px; margin: 12px 0;")
        layout.addRow("", separator)

        # Google API Key
        google_key_layout = QHBoxLayout()
        self.google_api_key_input = QLineEdit()
        self.google_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.google_api_key_input.setPlaceholderText("Enter your Google API key")
        google_key_layout.addWidget(self.google_api_key_input)

        self.show_google_key_btn = QPushButton("Show")
        self.show_google_key_btn.setCheckable(True)
        self.show_google_key_btn.toggled.connect(self._toggle_google_key_visibility)
        google_key_layout.addWidget(self.show_google_key_btn)

        layout.addRow("Google API Key:", google_key_layout)

        # Helper note
        google_note = QLabel("Used for Gemini Live voice conversations")
        google_note.setStyleSheet("color: #8a8078; font-size: 11px; padding-left: 2px;")
        layout.addRow("", google_note)

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
            # --- Meta Llama ---
            "meta/llama-3.1-8b-instruct",
            "meta/llama-3.1-70b-instruct",
            "meta/llama-3.1-405b-instruct",
            "meta/llama-3.2-1b-instruct",
            "meta/llama-3.2-3b-instruct",
            "meta/llama-3.2-11b-vision-instruct",
            "meta/llama-3.2-90b-vision-instruct",
            "meta/llama-3.3-70b-instruct",
            "meta/llama-4-maverick-17b-128e-instruct",
            "meta/llama-4-scout-17b-16e-instruct",
            "meta/llama-guard-4-12b",
            "meta/llama3-70b-instruct",
            "meta/llama3-8b-instruct",
            # --- Mistral ---
            "mistralai/devstral-2-123b-instruct-2512",
            "mistralai/magistral-small-2506",
            "mistralai/mamba-codestral-7b-v0.1",
            "mistralai/mathstral-7b-v0.1",
            "mistralai/ministral-14b-instruct-2512",
            "mistralai/mistral-7b-instruct-v0.2",
            "mistralai/mistral-7b-instruct-v0.3",
            "mistralai/mistral-large-3-675b-instruct-2512",
            "mistralai/mistral-medium-3-instruct",
            "mistralai/mistral-nemotron",
            "mistralai/mistral-small-24b-instruct",
            "mistralai/mistral-small-3.1-24b-instruct-2503",
            "mistralai/mixtral-8x7b-instruct-v0.1",
            "mistralai/mixtral-8x22b-instruct-v0.1",
            # --- Google ---
            "google/gemma-2-2b-it",
            "google/gemma-2-9b-it",
            "google/gemma-2-27b-it",
            "google/gemma-3-1b-it",
            "google/gemma-3-4b-it",
            "google/gemma-3-12b-it",
            "google/gemma-3-27b-it",
            "google/gemma-3n-e2b-it",
            "google/gemma-3n-e4b-it",
            "google/gemma-7b",
            "google/shieldgemma-9b",
            # --- NVIDIA ---
            "nvidia/llama-3.1-nemoguard-8b-content-safety",
            "nvidia/llama-3.1-nemoguard-8b-topic-control",
            "nvidia/llama-3.1-nemotron-70b-reward",
            "nvidia/llama-3.1-nemotron-nano-4b-v1.1",
            "nvidia/llama-3.1-nemotron-nano-8b-v1",
            "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
            "nvidia/llama-3.1-nemotron-safety-guard-8b-v3",
            "nvidia/llama-3.3-nemotron-super-49b-v1",
            "nvidia/llama-3.3-nemotron-super-49b-v1.5",
            "nvidia/llama3-chatqa-1.5-8b",
            "nvidia/nemotron-3-nano-30b-a3b",
            "nvidia/nemotron-4-mini-hindi-4b-instruct",
            "nvidia/nemotron-content-safety-reasoning-4b",
            "nvidia/nemotron-mini-4b-instruct",
            "nvidia/nvidia-nemotron-nano-9b-v2",
            "nvidia/riva-translate-4b-instruct-v1.1",
            "nvidia/usdcode-llama-3.1-70b-instruct",
            # --- Deepseek ---
            "deepseek-ai/deepseek-r1-distill-llama-8b",
            "deepseek-ai/deepseek-r1-distill-qwen-14b",
            "deepseek-ai/deepseek-r1-distill-qwen-32b",
            "deepseek-ai/deepseek-v3.1",
            "deepseek-ai/deepseek-v3.1-terminus",
            "deepseek-ai/deepseek-v3.2",
            # --- Qwen ---
            "qwen/qwen2-7b-instruct",
            "qwen/qwen2.5-7b-instruct",
            "qwen/qwen2.5-coder-32b-instruct",
            "qwen/qwen2.5-coder-7b-instruct",
            "qwen/qwen3-235b-a22b",
            "qwen/qwen3-coder-480b-a35b-instruct",
            "qwen/qwen3-next-80b-a3b-instruct",
            "qwen/qwen3-next-80b-a3b-thinking",
            "qwen/qwq-32b",
            # --- Microsoft ---
            "microsoft/phi-3-medium-128k-instruct",
            "microsoft/phi-3-medium-4k-instruct",
            "microsoft/phi-3-mini-128k-instruct",
            "microsoft/phi-3-mini-4k-instruct",
            "microsoft/phi-3-small-128k-instruct",
            "microsoft/phi-3-small-8k-instruct",
            "microsoft/phi-3.5-mini-instruct",
            "microsoft/phi-3.5-vision-instruct",
            "microsoft/phi-4-mini-flash-reasoning",
            "microsoft/phi-4-mini-instruct",
            "microsoft/phi-4-multimodal-instruct",
            # --- Moonshot ---
            "moonshotai/kimi-k2-instruct",
            "moonshotai/kimi-k2-instruct-0905",
            "moonshotai/kimi-k2-thinking",
            # --- OpenAI (open-source) ---
            "openai/gpt-oss-20b",
            "openai/gpt-oss-120b",
            # --- MiniMax ---
            "minimaxai/minimax-m2",
            "minimaxai/minimax-m2.1",
            # --- AI21 Labs ---
            "ai21labs/jamba-1.5-mini-instruct",
            # --- Abacus AI ---
            "abacusai/dracarys-llama-3.1-70b-instruct",
            # --- IBM ---
            "ibm/granite-3.3-8b-instruct",
            "ibm/granite-guardian-3.0-8b",
            # --- Stepfun ---
            "stepfun-ai/step-3.5-flash",
            # --- Z-AI (Zhipu) ---
            "z-ai/glm4.7",
            "z-ai/glm5",
            # --- ByteDance ---
            "bytedance/seed-oss-36b-instruct",
            # --- Tiiuae ---
            "tiiuae/falcon3-7b-instruct",
            # --- Upstage ---
            "upstage/solar-10.7b-instruct",
            # --- Baichuan ---
            "baichuan-inc/baichuan2-13b-chat",
            # --- THU ---
            "thudm/chatglm3-6b",
            # --- Sarvamai ---
            "sarvamai/sarvam-m",
            # --- Rakuten ---
            "rakuten/rakutenai-7b-chat",
            "rakuten/rakutenai-7b-instruct",
            # --- Igenius ---
            "igenius/italia_10b_instruct_16k",
            # --- Stockmark ---
            "stockmark/stockmark-2-100b-instruct",
            # --- Speakleash ---
            "speakleash/bielik-11b-v2.3-instruct",
            "speakleash/bielik-11b-v2.6-instruct",
            # --- Other ---
            "gotocompany/gemma-2-9b-cpt-sahabatai-instruct",
            "institute-of-science-tokyo/llama-3.1-swallow-70b-instruct-v0.1",
            "institute-of-science-tokyo/llama-3.1-swallow-8b-instruct-v0.1",
            "marin/marin-8b-instruct",
            "mediatek/breeze-7b-instruct",
            "opengpt-x/teuken-7b-instruct-commercial-v0.4",
            "tokyotech-llm/llama-3-swallow-70b-instruct-v0.1",
            "utter-project/eurollm-9b-instruct",
            "yentinglin/llama-3-taiwan-70b-instruct",
        ])
        self.model_combo.setMaxVisibleItems(20)
        self.model_combo.setMaxCount(200)

        # Add search/filter completer for easy model lookup
        from PyQt6.QtCore import Qt as QtCore_Qt
        from PyQt6.QtWidgets import QCompleter
        completer = QCompleter([
            self.model_combo.itemText(i) for i in range(self.model_combo.count())
        ])
        completer.setCaseSensitivity(QtCore_Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(QtCore_Qt.MatchFlag.MatchContains)
        self.model_combo.setCompleter(completer)

        layout.addRow("Model:", self.model_combo)

        # Temperature
        self.temp_spin = QSpinBox()
        self.temp_spin.setRange(0, 100)
        self.temp_spin.setValue(70)
        self.temp_spin.setSuffix("%")
        layout.addRow("Temperature:", self.temp_spin)

        # Max tokens
        self.tokens_spin = QSpinBox()
        self.tokens_spin.setRange(256, 32768)
        self.tokens_spin.setSingleStep(256)
        self.tokens_spin.setValue(4096)
        layout.addRow("Max Tokens:", self.tokens_spin)

        return widget

    def _create_screen_tab(self) -> QWidget:
        """Create screen access settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        # Screen Access group
        access_group = QGroupBox("Screen Access")
        access_layout = QVBoxLayout(access_group)

        self.screen_vision_check = QCheckBox("Allow screen reading for vision models")
        self.screen_vision_check.setChecked(False)
        access_layout.addWidget(self.screen_vision_check)

        self.screen_gemini_check = QCheckBox("Allow screen sharing during Gemini Live")
        self.screen_gemini_check.setChecked(False)
        access_layout.addWidget(self.screen_gemini_check)

        layout.addWidget(access_group)

        # Capture Settings group
        capture_group = QGroupBox("Capture Settings")
        capture_layout = QFormLayout(capture_group)

        # Monitor selection
        self.monitor_combo = QComboBox()
        self._populate_monitors()
        capture_layout.addRow("Monitor:", self.monitor_combo)

        # Capture interval
        self.capture_interval_spin = QSpinBox()
        self.capture_interval_spin.setRange(1, 10)
        self.capture_interval_spin.setValue(3)
        self.capture_interval_spin.setSuffix(" seconds")
        capture_layout.addRow("Capture interval:", self.capture_interval_spin)

        layout.addWidget(capture_group)

        # Privacy note
        privacy_note = QLabel(
            "Screen is only accessed when this app is running in the background.\n"
            "Screenshots are never saved to disk \u2014 processed in memory only."
        )
        privacy_note.setStyleSheet("color: #8a8078; font-size: 11px; padding: 4px;")
        privacy_note.setWordWrap(True)
        layout.addWidget(privacy_note)

        # Info button
        info_btn = QPushButton("What can this app see?")
        info_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #FF8C42; "
            "border: 1px solid #2a2218; padding: 6px; }"
            "QPushButton:hover { border-color: #FF8C42; }"
        )
        info_btn.clicked.connect(self._show_screen_info)
        layout.addWidget(info_btn)

        # Test button
        test_btn = QPushButton("Test screen capture")
        test_btn.setStyleSheet(
            "QPushButton { background-color: #1e1a14; color: #FF8C42; "
            "border: 1px solid #2a2218; padding: 6px; }"
            "QPushButton:hover { border-color: #FF8C42; background-color: #2a2218; }"
        )
        test_btn.clicked.connect(self._test_screen_capture)
        layout.addWidget(test_btn)

        # OCR info
        ocr_note = QLabel(
            "OCR is powered by your NVIDIA NIM vision model.\n"
            "Screen is only read when this app is in the background."
        )
        ocr_note.setStyleSheet("color: #8a8078; font-size: 11px; padding: 4px;")
        ocr_note.setWordWrap(True)
        layout.addWidget(ocr_note)

        layout.addStretch()

        return widget

    def _populate_monitors(self):
        """Populate monitor dropdown from available screens."""
        self.monitor_combo.clear()
        try:
            from src.capabilities.screen_capture import ScreenCaptureService

            service = ScreenCaptureService()
            monitors = service.available_monitors()
            for mon in monitors:
                self.monitor_combo.addItem(mon["name"], mon["index"])
        except Exception:
            self.monitor_combo.addItem("Primary", 0)

    def _show_screen_info(self):
        """Show info dialog explaining screen access behavior."""
        QMessageBox.information(
            self,
            "Screen Access Information",
            "When enabled, this app can capture your screen ONLY while it is "
            "minimized or unfocused.\n\n"
            "The moment you bring the app to the foreground, screen capture "
            "stops immediately.\n\n"
            "Screenshots are processed in memory and never saved to disk.\n\n"
            "For vision models: the screenshot is sent as an image to the AI "
            "model with your message.\n\n"
            "For Gemini Live: screenshots are processed by your NVIDIA NIM "
            "vision model to extract text (OCR), which is then sent as context "
            "to Gemini during your voice session.\n\n"
            "You can stop screen capture at any time by disabling it here or "
            "bringing the app to focus.",
        )

    def _test_screen_capture(self):
        """Take a test screenshot and show results (with optional OCR)."""
        from src.capabilities.screen_capture import ScreenCaptureService

        monitor_idx = self.monitor_combo.currentData() or 0
        service = ScreenCaptureService(monitor=monitor_idx)
        # Temporarily allow capture for test (bypass background check)
        service._app_in_background = True
        frame = service.capture_once()

        if frame is None:
            QMessageBox.warning(
                self,
                "Test Failed",
                "Could not capture screen. Make sure mss and Pillow are installed.",
            )
            return

        size_kb = len(frame) / 1024
        msg = (
            f"Screenshot captured successfully!\n\n"
            f"Size: {size_kb:.1f} KB\n"
            f"Format: JPEG (in-memory, not saved to disk)\n\n"
        )

        # Check if NVIDIA API is available for OCR test
        if self.orchestrator and self.orchestrator.is_ready:
            msg += (
                "NVIDIA API is configured. To test OCR, enable screen reading\n"
                "and minimize the app, then send a message."
            )
        else:
            msg += "Configure NVIDIA API key to test OCR text extraction."

        QMessageBox.information(self, "Screen Capture Test", msg)

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
            "QPushButton { background-color: #FF4500; color: white; }"
        )
        clear_btn.clicked.connect(self._clear_memory)
        layout.addWidget(clear_btn)

        layout.addStretch()

        return widget

    def _load_settings(self):
        """Load current settings."""
        config = self.orchestrator.config

        # Load API key: prefer keyring, fall back to .env
        stored_key = SecureStorage.get_api_key()
        if stored_key:
            self.api_key_input.setText(stored_key)
            self.status_label.setText("Configured (from secure storage)")
            self.status_label.setStyleSheet("color: #FF8C42;")
        elif config.nvidia_api_key and config.nvidia_api_key != "your_api_key_here":
            self.api_key_input.setText(config.nvidia_api_key)
            self.status_label.setText("Configured (from .env)")
            self.status_label.setStyleSheet("color: #FF8C42;")

        # Load Google API key: prefer keyring, fall back to .env
        stored_google_key = SecureStorage.get_google_api_key()
        if stored_google_key:
            self.google_api_key_input.setText(stored_google_key)
        elif config.google_api_key:
            self.google_api_key_input.setText(config.google_api_key)

        # Base URL
        self.base_url_input.setText(config.nvidia_base_url)

        # Screen capture settings
        self.screen_vision_check.setChecked(config.screen_capture_vision)
        self.screen_gemini_check.setChecked(config.screen_capture_gemini)
        monitor_index = self.monitor_combo.findData(config.screen_capture_monitor)
        if monitor_index >= 0:
            self.monitor_combo.setCurrentIndex(monitor_index)
        self.capture_interval_spin.setValue(config.screen_capture_interval)

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

    def _toggle_google_key_visibility(self, checked: bool):
        """Toggle Google API key visibility."""
        if checked:
            self.google_api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_google_key_btn.setText("Hide")
        else:
            self.google_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_google_key_btn.setText("Show")

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
        self.status_label.setStyleSheet("color: #FFA500;")

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
                self.status_label.setStyleSheet("color: #FF8C42;")
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
                self.status_label.setStyleSheet("color: #FF4500;")
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
            self.status_label.setStyleSheet("color: #FF4500;")
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
        api_key = self.api_key_input.text().strip()
        base_url = self.base_url_input.text().strip()

        # Update base URL first (before recreating client)
        if base_url:
            self.orchestrator.config.nvidia_base_url = base_url

        # Save API key to secure storage and (re)initialize the client
        if api_key:
            SecureStorage.store_api_key(api_key)
            # set_api_key will use the current config.nvidia_base_url
            self.orchestrator.set_api_key(api_key)
            # Also write to .env so it persists across sessions
            self._update_env_file("NVIDIA_API_KEY", api_key)

        if base_url:
            self._update_env_file("NVIDIA_BASE_URL", base_url)

        # Save Google API key
        google_key = self.google_api_key_input.text().strip()
        if google_key:
            SecureStorage.store_google_api_key(google_key)
            self.orchestrator.config.google_api_key = google_key
            self._update_env_file("GOOGLE_API_KEY", google_key)

        # Save screen capture settings
        config = self.orchestrator.config
        config.screen_capture_vision = self.screen_vision_check.isChecked()
        config.screen_capture_gemini = self.screen_gemini_check.isChecked()
        config.screen_capture_monitor = self.monitor_combo.currentData() or 0
        config.screen_capture_interval = self.capture_interval_spin.value()
        self._update_env_file(
            "SCREEN_CAPTURE_VISION", str(config.screen_capture_vision).lower()
        )
        self._update_env_file(
            "SCREEN_CAPTURE_GEMINI", str(config.screen_capture_gemini).lower()
        )
        self._update_env_file("SCREEN_CAPTURE_MONITOR", str(config.screen_capture_monitor))
        self._update_env_file("SCREEN_CAPTURE_INTERVAL", str(config.screen_capture_interval))

        # Save model selection
        model = self.model_combo.currentText().strip()
        if model:
            self.orchestrator.config.default_model = model
            self._update_env_file("DEFAULT_MODEL", model)

        # Update status
        if self.orchestrator.is_ready:
            self.status_label.setText("Configured")
            self.status_label.setStyleSheet("color: #FF8C42;")

        self.settings_changed.emit()
        logger.info("Settings saved")

    def _update_env_file(self, key: str, value: str):
        """Update a key in the .env file, or add it if missing."""
        from pathlib import Path

        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        try:
            if env_path.exists():
                lines = env_path.read_text(encoding="utf-8").splitlines()
            else:
                lines = []

            found = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                    lines[i] = f"{key}={value}"
                    found = True
                    break

            if not found:
                lines.append(f"{key}={value}")

            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not update .env file: {e}")

    def accept(self):
        """Handle OK button."""
        self._save_settings()
        super().accept()
