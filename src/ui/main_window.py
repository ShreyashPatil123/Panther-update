"""Main window for NVIDIA AI Agent — PANTHER Grok-style redesign."""
import asyncio
import os
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from PyQt6.QtCore import Qt, QEvent, QTimer, pyqtSignal, pyqtSlot, QPoint
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
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
from src.ui.panther_buttons import PantherSendButton, PantherAttachButton


# ── Category items built from real TaskPresets ─────────────────────────────
def _build_category_items():
    """Build category dropdown items from model_router presets."""
    items = []
    for cat, preset in get_all_presets().items():
        short_model = preset.model.split("/")[-1] if "/" in preset.model else preset.model
        items.append({
            "id": cat.value,
            "icon": preset.emoji,
            "label": preset.label,
            "desc": preset.description,
            "model": short_model,
            "task": cat.value,
        })
    return items

CATEGORY_ITEMS = _build_category_items()


# ═══════════════════════════════════════════════════════════════════════════
# CategoryPopup — floating dropdown for model/category selection
# ═══════════════════════════════════════════════════════════════════════════

class CategoryPopup(QFrame):
    """Floating popup for category selection — auto-selects best model."""

    category_changed = pyqtSignal(dict)  # emits selected item dict

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._selected_id = "chat"
        self._item_widgets: Dict[str, QLabel] = {}  # id → checkmark label
        self._row_buttons: Dict[str, QPushButton] = {}  # id → row button
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedWidth(340)
        self.setStyleSheet("""
            CategoryPopup {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1e1e1e, stop:1 #161616);
                border: 1px solid #2a2a2a;
                border-radius: 16px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 10, 6, 10)
        layout.setSpacing(2)

        # Header
        hdr = QLabel("  SELECT CATEGORY")
        hdr.setStyleSheet(
            "color: #555; font-size: 10px; font-weight: 600; "
            "letter-spacing: 1.5px; "
            "background: transparent; padding: 4px 10px 6px;"
        )
        layout.addWidget(hdr)

        for item in CATEGORY_ITEMS:
            row = self._make_row(item)
            layout.addWidget(row)

    def _make_row(self, item: dict) -> QPushButton:
        btn = QPushButton()
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(54)

        lay = QHBoxLayout(btn)
        lay.setContentsMargins(14, 6, 14, 6)
        lay.setSpacing(10)

        # Icon
        icon = QLabel(item["icon"])
        icon.setFixedWidth(24)
        icon.setStyleSheet("font-size: 17px; background: transparent; border: none;")
        lay.addWidget(icon)

        # Text column: label + model name
        col = QVBoxLayout()
        col.setSpacing(1)
        title = QLabel(item["label"])
        title.setStyleSheet(
            "color: #e8e8e8; font-size: 13px; font-weight: 600; "
            "background: transparent; border: none; letter-spacing: 0.2px;"
        )
        col.addWidget(title)
        model_lbl = QLabel(item.get("model", item["desc"]))
        model_lbl.setStyleSheet(
            "color: #666; font-size: 10px; background: transparent; "
            "border: none; font-family: 'JetBrains Mono', 'Consolas', monospace;"
        )
        col.addWidget(model_lbl)
        lay.addLayout(col)

        lay.addStretch()

        # Checkmark
        active = item["id"] == self._selected_id
        check = QLabel("✓" if active else "")
        check.setFixedWidth(20)
        check.setStyleSheet(
            "color: #FF6B35; font-size: 15px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        self._item_widgets[item["id"]] = check
        lay.addWidget(check)

        self._apply_row_style(btn, active)
        self._row_buttons[item["id"]] = btn
        btn.clicked.connect(lambda _, i=item: self._select(i))
        return btn

    def _apply_row_style(self, btn: QPushButton, active: bool):
        if active:
            btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 rgba(255,107,53,0.12), stop:1 rgba(255,107,53,0.04));
                    border: none; border-radius: 12px;
                    border-left: 2px solid #FF6B35;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 rgba(255,107,53,0.18), stop:1 rgba(255,107,53,0.08));
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none; border-radius: 12px;
                    border-left: 2px solid transparent;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,0.05);
                }
            """)

    def _select(self, item: dict):
        self._selected_id = item["id"]
        for iid, lbl in self._item_widgets.items():
            is_active = iid == self._selected_id
            lbl.setText("✓" if is_active else "")
            if iid in self._row_buttons:
                self._apply_row_style(self._row_buttons[iid], is_active)
        self.category_changed.emit(item)
        self.hide()

    @property
    def selected(self) -> dict:
        for it in CATEGORY_ITEMS:
            if it["id"] == self._selected_id:
                return it
        return CATEGORY_ITEMS[0]

    @property
    def selected_label(self) -> str:
        return self.selected["label"]


# ═══════════════════════════════════════════════════════════════════════════
# Sidebar — Grok-style navigation
# ═══════════════════════════════════════════════════════════════════════════

class Sidebar(QWidget):
    """Left sidebar with search, navigation, and history."""

    session_clicked = pyqtSignal(str)   # emits session_id
    session_deleted = pyqtSignal(str)   # emits session_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(250)
        self._history_buttons: Dict[str, QPushButton] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 10)
        layout.setSpacing(4)

        # ── Panther brand (image) ──
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(6, 0, 0, 0)
        panther_img = QLabel()
        img_path = str(Path(__file__).resolve().parent.parent.parent / "PANTHER.jpeg")
        pix = QPixmap(img_path)
        if not pix.isNull():
            panther_img.setPixmap(
                pix.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
        else:
            panther_img.setText("🐆")  # fallback
        panther_img.setStyleSheet("background: transparent;")
        brand_label = QLabel("PANTHER")
        brand_label.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #e8e8e8; "
            "background: transparent; padding-left: 6px;"
        )
        brand_row.addWidget(panther_img)
        brand_row.addWidget(brand_label)
        brand_row.addStretch()
        layout.addLayout(brand_row)
        layout.addSpacing(10)

        # ── Navigation buttons ──
        self.chat_btn = self._nav("💬  Chat", True)
        layout.addWidget(self.chat_btn)
        layout.addSpacing(4)

        # ── History ──
        hist_hdr = QLabel("History")
        hist_hdr.setStyleSheet(
            "color: #777; font-size: 12px; font-weight: 600; padding: 4px 14px; "
            "background: transparent; letter-spacing: 0.5px;"
        )
        layout.addWidget(hist_hdr)

        hist_scroll = QScrollArea()
        hist_scroll.setWidgetResizable(True)
        hist_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        hist_scroll.setFrameShape(QFrame.Shape.NoFrame)
        hist_scroll.setStyleSheet("background: transparent; border: none;")

        hist_container = QWidget()
        hist_lay = QVBoxLayout(hist_container)
        hist_lay.setContentsMargins(0, 0, 0, 0)
        hist_lay.setSpacing(0)

        # Empty-state label (shown when no sessions exist)
        self._empty_label = QLabel("No conversations yet")
        self._empty_label.setStyleSheet(
            "color: #555; font-size: 12px; padding: 10px 14px; background: transparent;"
        )
        hist_lay.addWidget(self._empty_label)

        self._history_layout = hist_lay
        hist_lay.addStretch()
        hist_scroll.setWidget(hist_container)
        layout.addWidget(hist_scroll)

        # ── Bottom bar ──
        bottom = QFrame()
        bottom.setStyleSheet("background: transparent;")
        bottom_lay = QHBoxLayout(bottom)
        bottom_lay.setContentsMargins(8, 4, 8, 4)

        # New Chat button
        self.new_chat_btn = QPushButton("☆")
        self.new_chat_btn.setObjectName("sidebarIconBtn")
        self.new_chat_btn.setFixedSize(30, 30)
        self.new_chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_chat_btn.setToolTip("New Chat")
        self.new_chat_btn.setStyleSheet(
            "QPushButton#sidebarIconBtn { background: transparent; border: none; font-size: 16px; "
            "border-radius: 6px; color: #888; } QPushButton#sidebarIconBtn:hover { background: #1a1a1a; color: #fff; }"
        )
        bottom_lay.addWidget(self.new_chat_btn)
        bottom_lay.addStretch()

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("sidebarSettingsBtn")
        self.settings_btn.setFixedSize(30, 30)
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setStyleSheet(
            "QPushButton#sidebarSettingsBtn { background: transparent; color: #fff; border: none; "
            "font-size: 18px; border-radius: 6px; } "
            "QPushButton#sidebarSettingsBtn:hover { background: #1a1a1a; color: #e8a025; }"
        )
        bottom_lay.addWidget(self.settings_btn)
        layout.addWidget(bottom)

        # ── Hidden functional elements (used by MainWindow) ──
        self.model_label = QLabel("")
        self.model_label.setVisible(False)
        self.status_label = QLabel("● Ready")
        self.status_label.setVisible(False)

        # Backward-compat aliases for MainWindow._connect_signals
        self.voice_nav_btn = self.chat_btn
        self.imagine_btn = self.chat_btn
        self.projects_btn = self.chat_btn
        self.memory_btn = self.chat_btn
        self.tasks_btn = self.chat_btn

    def _nav(self, text: str, checked: bool) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("sidebarButton")
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    # Public helpers (called by MainWindow)
    def set_status(self, status: str, is_error: bool = False):
        self.status_label.setText(status)

    def set_model(self, model: str):
        short = model.split("/")[-1] if "/" in model else model
        self.model_label.setText(f"Model: {short}")

    def load_history(self, sessions: list):
        """Populate the history section with real session data.

        Args:
            sessions: List of session dicts with 'id', 'title', 'updated_at'.
        """
        # Remove old history buttons
        for btn in list(self._history_buttons.values()):
            self._history_layout.removeWidget(btn)
            btn.deleteLater()
        self._history_buttons.clear()

        # Show/hide empty label
        self._empty_label.setVisible(len(sessions) == 0)

        # Add items (sessions already ordered by updated_at DESC from MemorySystem)
        for sess in sessions:
            self._add_history_item(sess["id"], sess.get("title") or "Untitled")

    def _add_history_item(self, session_id: str, title: str):
        """Create a single history button for a session."""
        # Truncate long titles
        display = title if len(title) <= 30 else title[:28] + "…"
        btn = QPushButton(display)
        btn.setObjectName("historyItem")
        btn.setToolTip(title)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton#historyItem {
                background: transparent; color: #888; border: none;
                border-radius: 6px; padding: 6px 14px; font-size: 12px; text-align: left;
            }
            QPushButton#historyItem:hover { background: #171717; color: #ccc; }
        """)
        btn.clicked.connect(lambda checked, sid=session_id: self.session_clicked.emit(sid))

        # Right-click context menu for delete
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos, sid=session_id, b=btn: self._show_history_context_menu(pos, sid, b)
        )

        # Insert before the stretch at the end
        count = self._history_layout.count()
        self._history_layout.insertWidget(count - 1, btn)  # before stretch
        self._history_buttons[session_id] = btn

    def _show_history_context_menu(self, pos, session_id: str, btn: QPushButton):
        """Show right-click context menu on a history item."""
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1a1a1a; color: #ccc; border: 1px solid #333; "
            "border-radius: 6px; padding: 4px; } "
            "QMenu::item:selected { background: #2a2a2a; }"
        )
        delete_action = menu.addAction("🗑 Delete")
        action = menu.exec(btn.mapToGlobal(pos))
        if action == delete_action:
            self.session_deleted.emit(session_id)

    def highlight_session(self, session_id: str):
        """Visually highlight the active session in the history list."""
        for sid, btn in self._history_buttons.items():
            if sid == session_id:
                btn.setStyleSheet("""
                    QPushButton#historyItem {
                        background: #1a1a1a; color: #e8a025; border: none;
                        border-radius: 6px; padding: 6px 14px; font-size: 12px;
                        text-align: left; font-weight: 600;
                    }
                    QPushButton#historyItem:hover { background: #222; }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton#historyItem {
                        background: transparent; color: #888; border: none;
                        border-radius: 6px; padding: 6px 14px; font-size: 12px;
                        text-align: left;
                    }
                    QPushButton#historyItem:hover { background: #171717; color: #ccc; }
                """)


# ═══════════════════════════════════════════════════════════════════════════
# ChatWidget — hero area + inline input bar with category dropdown
# ═══════════════════════════════════════════════════════════════════════════

class ChatWidget(QWidget):
    """Chat interface — Grok-style hero + inline category dropdown."""

    message_sent = pyqtSignal(str)
    message_sent_with_attachments = pyqtSignal(str, list)
    voice_requested = pyqtSignal()
    task_selected = pyqtSignal(str)  # emits TaskCategory value string

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_typing = False
        self._current_ai_bubble: Optional[MessageBubble] = None
        self._pending_attachments: List[str] = []
        self._has_messages = False
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar (Gemini Live button) ──────────────────────────────────
        top_bar = QFrame()
        top_bar.setStyleSheet("background: transparent;")
        top_bar.setFixedHeight(40)
        top_lay = QHBoxLayout(top_bar)
        top_lay.setContentsMargins(20, 6, 20, 0)
        top_lay.addStretch()
        self.gemini_live_btn = QPushButton("✦  Gemini Live")
        self.gemini_live_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gemini_live_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a1a2e, stop:1 #16213e);
                color: #8ab4f8; border: 1px solid #2a3a5a;
                border-radius: 14px; padding: 6px 16px;
                font-size: 12px; font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #222244, stop:1 #1a2a4e);
                border-color: #4a6a9a; color: #aaccff;
            }
        """)
        top_lay.addWidget(self.gemini_live_btn)
        root.addWidget(top_bar)

        # ── Content stack: hero vs chat ──────────────────────────────────
        self._content_stack = QStackedWidget()

        # — Page 0: Hero area —
        hero = QWidget()
        hero.setStyleSheet("background: transparent;")
        hero_lay = QVBoxLayout(hero)
        hero_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_lay.setSpacing(10)

        # Panther image + title
        panther_img_label = QLabel()
        panther_img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panther_img_label.setStyleSheet("background: transparent;")
        img_path = Path(__file__).parent.parent.parent / "PANTHER.jpeg"
        if img_path.exists():
            pixmap = QPixmap(str(img_path))
            scaled = pixmap.scaledToWidth(
                280, Qt.TransformationMode.SmoothTransformation
            )
            panther_img_label.setPixmap(scaled)
        else:
            panther_img_label.setText("🐆")
            panther_img_label.setStyleSheet(
                "font-size: 72px; background: transparent;"
            )
        hero_lay.addWidget(panther_img_label)

        title = QLabel("PANTHER")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 52px; font-weight: 800; letter-spacing: 6px; "
            "color: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #c0c0c0, stop:0.5 #ffffff, stop:1 #a0a0a0); "
            "background: transparent;"
        )
        hero_lay.addWidget(title)

        hero_lay.addSpacing(60)
        self._content_stack.addWidget(hero)

        # — Page 1: Chat messages —
        chat_page = QWidget()
        chat_page.setStyleSheet("background: transparent;")
        chat_lay = QVBoxLayout(chat_page)
        chat_lay.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("chatArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(28, 24, 28, 24)
        self.messages_layout.setSpacing(20)
        self.messages_layout.addStretch()
        scroll.setWidget(self.messages_container)
        chat_lay.addWidget(scroll)
        self.scroll_area = scroll
        self._content_stack.addWidget(chat_page)

        # Start on hero
        self._content_stack.setCurrentIndex(0)
        root.addWidget(self._content_stack)

        # ── Attachment preview (hidden) ──────────────────────────────────
        self._attachment_strip = QFrame()
        self._attachment_strip.setStyleSheet("""
            QFrame {
                background: #111; border: 1px solid #222;
                border-bottom: none; border-radius: 14px 14px 0 0; padding: 4px 8px;
            }
        """)
        self._attachment_layout = QHBoxLayout(self._attachment_strip)
        self._attachment_layout.setContentsMargins(12, 6, 12, 6)
        self._attachment_layout.setSpacing(6)
        self._attachment_layout.addStretch()
        self._attachment_strip.setVisible(False)
        root.addWidget(self._attachment_strip)

        # ── Input bar ────────────────────────────────────────────────────
        input_frame = QFrame()
        input_frame.setObjectName("inputBar")
        input_frame.setStyleSheet("""
            QFrame#inputBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a1a, stop:1 #131313);
                border: 1px solid #2a2a2a;
                border-radius: 28px;
                margin: 0 50px 18px 50px;
            }
            QFrame#inputBar:hover {
                border-color: #3a3a3a;
            }
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(8, 4, 8, 4)
        input_layout.setSpacing(4)

        # Attach button
        self.attach_btn = PantherAttachButton()
        self.attach_btn.setFixedSize(36, 36)
        self.attach_btn.clicked.connect(self._on_attach_clicked)
        input_layout.addWidget(self.attach_btn)

        # Text input
        self.message_input = QTextEdit()
        self.message_input.setObjectName("messageInput")
        self.message_input.setPlaceholderText("How can I help you today?")
        self.message_input.setMaximumHeight(80)
        self.message_input.setStyleSheet("""
            QTextEdit#messageInput {
                background: transparent; color: #e8e8e8; border: none;
                padding: 8px 6px; font-size: 14px;
                font-family: 'Inter', 'Segoe UI', sans-serif;
                selection-background-color: #FF6B35;
            }
        """)
        self.message_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.message_input.keyPressEvent = self._handle_key_press
        input_layout.addWidget(self.message_input)

        # ── Category dropdown button ──
        self._category_popup = CategoryPopup(self)
        self._category_popup.category_changed.connect(self._on_category_changed)

        self._cat_btn = QPushButton("💬 Chat  ∧")
        self._cat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cat_btn.setFixedHeight(34)
        self._cat_btn.setStyleSheet("""
            QPushButton {
                background: #222; color: #ddd; border: 1px solid #333;
                border-radius: 12px; padding: 4px 14px; font-size: 12px;
                font-weight: 600; min-width: 100px;
            }
            QPushButton:hover { background: #2a2a2a; border-color: #444; }
        """)
        self._cat_btn.clicked.connect(self._show_category_popup)
        input_layout.addWidget(self._cat_btn)


        # Send button
        self.send_btn = PantherSendButton()
        self.send_btn.setFixedSize(36, 36)
        self.send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_btn)

        root.addWidget(input_frame)

        # ── Voice recording indicator (hidden) ──
        self.voice_indicator = QLabel("🐆  Gemini Live active…")
        self.voice_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voice_indicator.setStyleSheet(
            "background: rgba(138,180,248,0.08); color: #8ab4f8; "
            "padding: 8px; font-size: 12px; border: none;"
        )
        self.voice_indicator.setVisible(False)
        root.addWidget(self.voice_indicator)

        # Typing indicator (hidden)
        self.typing_indicator = TypingIndicator()
        self.typing_indicator.setVisible(False)

    # ── Category dropdown helpers ───────────────────────────────────────

    def _show_category_popup(self):
        btn_pos = self._cat_btn.mapToGlobal(QPoint(0, 0))
        popup_x = btn_pos.x() + self._cat_btn.width() // 2 - 150
        popup_y = btn_pos.y() - self._category_popup.sizeHint().height() - 8
        self._category_popup.move(popup_x, popup_y)
        self._category_popup.show()

    def _on_category_changed(self, item: dict):
        icon = item["icon"]
        label = item["label"]
        self._cat_btn.setText(f"{icon} {label}  ∧")
        task_val = item.get("task", "")
        self.task_selected.emit(task_val or "")

    # ── Key press ───────────────────────────────────────────────────────

    def _handle_key_press(self, event):
        if event.key() == Qt.Key.Key_Return and not event.modifiers():
            self._send_message()
        else:
            QTextEdit.keyPressEvent(self.message_input, event)

    # ── Send / voice ────────────────────────────────────────────────────

    def _send_message(self):
        text = self.message_input.toPlainText().strip()
        if text and not self._is_typing:
            # Switch from hero to chat on first message
            if not self._has_messages:
                self._has_messages = True
                self._content_stack.setCurrentIndex(1)

            if self._pending_attachments:
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

    def _on_voice_clicked(self):
        self.voice_requested.emit()

    # ── Attachment helpers ──────────────────────────────────────────────

    def _on_attach_clicked(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Attach Files", "",
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
        from src.core.file_processor import classify_file, FileType

        name = os.path.basename(filepath)
        ftype = classify_file(filepath)
        icons = {
            FileType.IMAGE: "🖼️", FileType.VIDEO: "🎬",
            FileType.DOCUMENT: "📄", FileType.TEXT: "📝",
        }
        icon = icons.get(ftype, "📁")

        pill = QFrame()
        pill.setStyleSheet("""
            QFrame { background: #1a1a1a; border: 1px solid #2a2a2a;
                     border-radius: 8px; padding: 2px 6px; }
        """)
        pill_lay = QHBoxLayout(pill)
        pill_lay.setContentsMargins(4, 2, 4, 2)
        pill_lay.setSpacing(4)

        lbl = QLabel(f"{icon} {name}")
        lbl.setStyleSheet(
            "color: #b0a090; font-size: 11px; background: transparent; border: none;"
        )
        pill_lay.addWidget(lbl)

        rm = QPushButton("✕")
        rm.setFixedSize(16, 16)
        rm.setCursor(Qt.CursorShape.PointingHandCursor)
        rm.setStyleSheet("""
            QPushButton { background: transparent; color: #555; border: none; font-size: 10px; }
            QPushButton:hover { color: #FF4500; }
        """)
        rm.clicked.connect(lambda: self._remove_attachment(filepath, pill))
        pill_lay.addWidget(rm)

        self._attachment_layout.insertWidget(
            self._attachment_layout.count() - 1, pill
        )
        self._attachment_strip.setVisible(True)
        if hasattr(self.attach_btn, "set_has_files"):
            self.attach_btn.set_has_files(True)

    def _remove_attachment(self, filepath: str, pill: QFrame):
        if filepath in self._pending_attachments:
            self._pending_attachments.remove(filepath)
        pill.deleteLater()
        if not self._pending_attachments:
            self._attachment_strip.setVisible(False)
            if hasattr(self.attach_btn, "set_has_files"):
                self.attach_btn.set_has_files(False)

    def _clear_attachments(self):
        self._pending_attachments.clear()
        while self._attachment_layout.count() > 1:
            item = self._attachment_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._attachment_strip.setVisible(False)
        if hasattr(self.attach_btn, "set_has_files"):
            self.attach_btn.set_has_files(False)

    # ── Voice helpers ──────────────────────────────────────────────────

    def set_voice_recording(self, is_recording: bool):
        self.voice_btn.setChecked(is_recording)
        self.voice_indicator.setVisible(is_recording)
        self.message_input.setEnabled(not is_recording)
        self.send_btn.setEnabled(not is_recording)

    def set_transcription(self, text: str):
        self.message_input.setPlainText(text)
        self.set_voice_recording(False)
        self.message_input.setFocus()

    # ── Message helpers ────────────────────────────────────────────────

    def add_message(self, text: str, is_user: bool = False):
        if not self._has_messages:
            self._has_messages = True
            self._content_stack.setCurrentIndex(1)
        bubble = MessageBubble(text, is_user)
        self.messages_layout.insertWidget(
            self.messages_layout.count() - 1, bubble
        )
        self._scroll_to_bottom()
        return bubble

    def begin_ai_response(self) -> MessageBubble:
        if not self._has_messages:
            self._has_messages = True
            self._content_stack.setCurrentIndex(1)
        bubble = MessageBubble("", is_user=False)
        self._current_ai_bubble = bubble
        self.messages_layout.insertWidget(
            self.messages_layout.count() - 1, bubble
        )
        self._scroll_to_bottom()
        return bubble

    def update_ai_response(self, text: str):
        if self._current_ai_bubble is not None:
            self._current_ai_bubble.set_text(text)
            self._scroll_to_bottom()

    def finish_ai_response(self):
        self._current_ai_bubble = None

    def add_typing_indicator(self):
        self._is_typing = True
        if not self._has_messages:
            self._has_messages = True
            self._content_stack.setCurrentIndex(1)
        self.messages_layout.insertWidget(
            self.messages_layout.count() - 1, self.typing_indicator
        )
        self.typing_indicator.setVisible(True)
        self._scroll_to_bottom()

    def remove_typing_indicator(self):
        self._is_typing = False
        self.typing_indicator.setVisible(False)
        self.typing_indicator.setParent(None)

    def clear_chat(self):
        self._current_ai_bubble = None
        self._has_messages = False
        self._content_stack.setCurrentIndex(0)
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _scroll_to_bottom(self):
        QTimer.singleShot(
            50,
            lambda: self.scroll_area.verticalScrollBar().setValue(
                self.scroll_area.verticalScrollBar().maximum()
            ),
        )

    def set_enabled(self, enabled: bool):
        self.message_input.setEnabled(enabled)
        self.send_btn.setEnabled(enabled)
        if enabled:
            self.voice_btn.setEnabled(True)


# ═══════════════════════════════════════════════════════════════════════════
# MainWindow — application shell
# ═══════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, orchestrator: AgentOrchestrator, parent=None):
        super().__init__(parent)
        self.orchestrator = orchestrator
        self._app_in_background = False

        # Screen capture
        from src.capabilities.screen_capture import ScreenCaptureService

        self._screen_service = ScreenCaptureService(
            monitor=orchestrator.config.screen_capture_monitor,
            interval=orchestrator.config.screen_capture_interval,
        )
        self._screen_service.vision_enabled = orchestrator.config.screen_capture_vision
        self._screen_service.gemini_enabled = orchestrator.config.screen_capture_gemini

        # Gemini Live speech
        from src.api.gemini_live_speech import GeminiLiveSpeechService
        from src.utils.secure_storage import SecureStorage

        google_key = (
            SecureStorage.get_google_api_key()
            or orchestrator.config.google_api_key
            or None
        )
        self._speech_service = GeminiLiveSpeechService(
            system_prompt=(
                "You are Panther, a helpful AI voice assistant. "
                "Be concise and conversational."
            ),
            api_key=google_key,
            vad_enabled=orchestrator.config.vad_enabled,
        )
        self._speech_service.status_changed.connect(self._on_speech_status)
        self._speech_service.error_occurred.connect(self._on_speech_error)
        self._speech_service.partial_transcript.connect(self._on_speech_transcript)

        self._setup_ui()
        self._connect_signals()
        self._update_status()

        if self._screen_service.is_available:
            self._screen_service.start()

        app = QApplication.instance()
        if app:
            app.applicationStateChanged.connect(self._on_app_state_changed)

        if not orchestrator.is_ready:
            self._show_settings()

        # Gemini Live: do NOT auto-start — wait for button click

        # Load real chat history into sidebar
        asyncio.ensure_future(self._refresh_sidebar_history())

    def _setup_ui(self):
        self.setWindowTitle("PANTHER")
        self.setMinimumSize(1000, 700)
        self.resize(1400, 900)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)

        # Content area
        self.content_stack = QStackedWidget()

        # 0: Chat
        self.chat_widget = ChatWidget()
        self.content_stack.addWidget(self.chat_widget)

        # 1: Memory
        from src.ui.memory_panel import MemoryPanel
        self.memory_panel = MemoryPanel(memory_system=self.orchestrator.memory)
        self.content_stack.addWidget(self.memory_panel)

        # 2: Tasks
        from src.ui.tasks_panel import TasksPanel
        self.tasks_panel = TasksPanel(
            task_planner=self.orchestrator._task_planner,
        )
        self.content_stack.addWidget(self.tasks_panel)

        main_layout.addWidget(self.content_stack)
        self.sidebar.set_model(self.orchestrator.config.default_model)

    def _connect_signals(self):
        # Sidebar nav
        self.sidebar.chat_btn.clicked.connect(lambda: self._switch_view(0))
        self.sidebar.memory_btn.clicked.connect(lambda: self._switch_view(1))
        self.sidebar.tasks_btn.clicked.connect(lambda: self._switch_view(2))
        self.sidebar.settings_btn.clicked.connect(self._show_settings)
        self.sidebar.new_chat_btn.clicked.connect(self._new_chat)

        # Chat
        self.chat_widget.message_sent.connect(self._on_message_sent)
        self.chat_widget.message_sent_with_attachments.connect(
            self._on_message_sent_with_attachments
        )
        # Gemini Live
        self.chat_widget.gemini_live_btn.clicked.connect(self._on_gemini_live_toggled)
        self.chat_widget.task_selected.connect(self._on_task_selected)

        # Session history
        self.sidebar.session_clicked.connect(self._on_session_clicked)
        self.sidebar.session_deleted.connect(self._on_session_deleted)

    def _switch_view(self, index: int):
        self.content_stack.setCurrentIndex(index)
        buttons = [
            self.sidebar.chat_btn,
            self.sidebar.memory_btn,
            self.sidebar.tasks_btn,
        ]
        for i, btn in enumerate(buttons):
            btn.setChecked(i == index)
        if index == 1:
            self.memory_panel._load_sessions()
        elif index == 2:
            if self.orchestrator._task_planner:
                self.tasks_panel.set_task_planner(self.orchestrator._task_planner)

    def _show_settings(self):
        dialog = SettingsDialog(self.orchestrator, self)
        if dialog.exec():
            self._update_status()
            self.sidebar.set_model(self.orchestrator.config.default_model)
            self._reload_screen_settings()

    def _new_chat(self):
        asyncio.create_task(self._create_new_session())

    async def _create_new_session(self):
        session_id = await self.orchestrator.new_session()
        self.chat_widget.clear_chat()
        self._update_status()
        await self._refresh_sidebar_history()
        self.sidebar.highlight_session(session_id)
        logger.info(f"Created new session: {session_id}")

    async def _refresh_sidebar_history(self):
        """Reload sessions from memory and populate the sidebar."""
        try:
            sessions = await self.orchestrator.get_sessions()
            self.sidebar.load_history(sessions)
            self.sidebar.highlight_session(self.orchestrator.current_session_id)
        except Exception as e:
            logger.error(f"Failed to refresh sidebar history: {e}")

    def _on_session_clicked(self, session_id: str):
        """Handle clicking a session in the sidebar history."""
        asyncio.ensure_future(self._switch_to_session(session_id))

    async def _switch_to_session(self, session_id: str):
        """Switch to a different session and load its messages."""
        await self.orchestrator.set_session(session_id)
        self.chat_widget.clear_chat()
        # Load existing messages into the chat
        messages = await self.orchestrator.memory.get_recent_messages(
            limit=50, session_id=session_id
        )
        for msg in messages:
            self.chat_widget.add_message(
                msg["content"], is_user=(msg["role"] == "user")
            )
        self.sidebar.highlight_session(session_id)
        self._update_status()
        logger.info(f"Switched to session: {session_id}")

    def _on_session_deleted(self, session_id: str):
        """Handle deleting a session from the sidebar."""
        asyncio.ensure_future(self._delete_session(session_id))

    async def _delete_session(self, session_id: str):
        """Delete a session and refresh the sidebar."""
        await self.orchestrator.memory.delete_session(session_id)
        # If we deleted the current session, create a new one
        if session_id == self.orchestrator.current_session_id:
            await self._create_new_session()
        else:
            await self._refresh_sidebar_history()
        logger.info(f"Deleted session: {session_id}")

    def _update_status(self):
        if self.orchestrator.is_ready:
            self.sidebar.set_status("● Connected")
        else:
            self.sidebar.set_status("API Key Required", is_error=True)

    # ── Message handling ───────────────────────────────────────────────

    def _on_message_sent(self, message: str):
        if not self.orchestrator.is_ready:
            self.chat_widget.add_message(
                "Please configure your NVIDIA API key in Settings first.",
                is_user=False,
            )
            return

        screen_b64 = None
        if (
            self.orchestrator.config.screen_capture_vision
            and self._app_in_background
            and self._screen_service.is_available
        ):
            screen_b64 = self._screen_service.get_latest_base64()

        if screen_b64:
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

        self.chat_widget.set_enabled(False)
        self.chat_widget.add_typing_indicator()

        if self.orchestrator.active_task_category:
            cat = self.orchestrator.active_task_category
            preset = get_task_preset(cat)
            self.sidebar.set_status(f"● {preset.emoji} {preset.label} mode...")
        else:
            self.sidebar.set_status("● Processing...")

        asyncio.create_task(self._process_message(message))

    def _on_message_sent_with_attachments(self, message: str, attachments: list):
        if not self.orchestrator.is_ready:
            self.chat_widget.add_message(
                "Please configure your NVIDIA API key in Settings first.",
                is_user=False,
            )
            return
        self.chat_widget.set_enabled(False)
        self.chat_widget.add_typing_indicator()
        n = len(attachments)
        self.sidebar.set_status(
            f"● Processing {n} attachment{'s' if n > 1 else ''}..."
        )
        asyncio.create_task(
            self._process_message_with_attachments(message, attachments)
        )

    def _on_task_selected(self, category_value: str):
        if not category_value:
            self.orchestrator.set_task_category(None)
            self.orchestrator.config.default_model = "meta/llama-3.1-8b-instruct"
            self.sidebar.set_model(self.orchestrator.config.default_model)
            self.sidebar.set_status("● Auto mode")
            return

        try:
            category = TaskCategory(category_value)
        except ValueError:
            return

        preset = get_task_preset(category)
        self.orchestrator.set_task_category(category)
        self.sidebar.set_model(preset.model)
        self.sidebar.set_status(f"● {preset.emoji} {preset.label} mode")

    # ── Streaming message processing ──────────────────────────────────

    async def _process_message(self, message: str):
        import time
        response_text = ""
        ai_bubble: Optional[MessageBubble] = None
        last_render_time = 0.0
        RENDER_INTERVAL = 0.12

        try:
            self.sidebar.set_status("● Waiting for API...")
            async for chunk in self.orchestrator.process_message(message):
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
            logger.error(f"HTTP error processing message: {e}")
            if ai_bubble is None:
                self.chat_widget.remove_typing_indicator()
                ai_bubble = self.chat_widget.begin_ai_response()
            sc = e.response.status_code
            if sc == 401:
                msg = "Invalid API key. Please update it in Settings."
            elif sc == 429:
                msg = "Rate limited. Please wait and try again."
            elif sc == 404:
                msg = (
                    f"Model not found. The model '{self.orchestrator.config.default_model}' "
                    "may not be available. Try changing the model in Settings."
                )
            else:
                msg = f"API error (HTTP {sc}): {e}"
            self.chat_widget.update_ai_response(f"Error: {msg}")

        except httpx.ConnectError:
            logger.error("Connection error processing message")
            if ai_bubble is None:
                self.chat_widget.remove_typing_indicator()
                ai_bubble = self.chat_widget.begin_ai_response()
            self.chat_widget.update_ai_response(
                "Connection failed. Check your internet and the API URL in Settings."
            )

        except Exception as e:
            logger.error(f"Error processing message: {e}")
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
            # Refresh sidebar history (picks up auto-title & updated_at changes)
            asyncio.ensure_future(self._refresh_sidebar_history())

    async def _process_message_with_attachments(
        self, message: str, attachments: List[str]
    ):
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
            sc = e.response.status_code
            if sc == 401:
                msg = "Invalid API key."
            elif sc == 429:
                msg = "Rate limited. Please wait."
            elif sc == 404:
                msg = "Vision model not found."
            else:
                msg = f"API error (HTTP {sc}): {e}"
            self.chat_widget.update_ai_response(f"Error: {msg}")

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

    # ── Push-to-talk voice ─────────────────────────────────────────────

    def _on_gemini_live_toggled(self):
        """Toggle Gemini Live voice conversation."""
        if self._speech_service.is_active:
            self._speech_service.stop_turn()
            self.chat_widget.voice_indicator.setVisible(False)
            self.chat_widget.gemini_live_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #1a1a2e, stop:1 #16213e);
                    color: #8ab4f8; border: 1px solid #2a3a5a;
                    border-radius: 14px; padding: 6px 16px;
                    font-size: 12px; font-weight: 600;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #222244, stop:1 #1a2a4e);
                    border-color: #4a6a9a; color: #aaccff;
                }
            """)
        else:
            # Lazy-start: open the persistent session on first click
            if not self._speech_service._running:
                self._speech_service.start_conversation()
            self._speech_service.start_turn()
            self.chat_widget.voice_indicator.setText("✦  Gemini Live is listening…")
            self.chat_widget.voice_indicator.setVisible(True)
            self.chat_widget.gemini_live_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #1a2a4e, stop:1 #223366);
                    color: #aaccff; border: 1px solid #4a6a9a;
                    border-radius: 14px; padding: 6px 16px;
                    font-size: 12px; font-weight: 600;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #223366, stop:1 #2a4488);
                    border-color: #6a8abb;
                }
            """)

    def _on_speech_status(self, status: str):
        status_map = {
            "idle": "● Ready",
            "connecting": "● Connecting to Gemini Live…",
            "listening": "● 🎤 Listening…",
            "speaking": "● 🔊 Panther speaking…",
            "error": "● Voice error",
        }
        text = status_map.get(status, f"● {status}")
        self.sidebar.set_status(text, is_error=(status == "error"))

        if status == "listening":
            self.chat_widget.voice_indicator.setText(
                "✦  Gemini Live is listening…"
            )
            self.chat_widget.voice_indicator.setVisible(True)
        elif status == "speaking":
            self.chat_widget.voice_indicator.setText("✦  Panther is speaking…")
            self.chat_widget.voice_indicator.setVisible(True)
        else:
            self.chat_widget.voice_indicator.setVisible(False)

    def _on_speech_error(self, error: str):
        self.chat_widget.add_message(f"Voice error: {error}", is_user=False)

    def _on_speech_transcript(self, text: str):
        logger.info(f"Transcript: {text}")

    # ── Background detection & screen capture ─────────────────────────

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            is_bg = self.isMinimized() or not self.isActiveWindow()
            self._on_app_background_changed(is_bg)
        super().changeEvent(event)

    def _on_app_state_changed(self, state):
        is_bg = state != Qt.ApplicationState.ApplicationActive
        self._on_app_background_changed(is_bg)

    def _on_app_background_changed(self, is_background: bool):
        if is_background == self._app_in_background:
            return
        self._app_in_background = is_background
        self._screen_service.set_app_in_background(is_background)

        config = self.orchestrator.config
        screen_enabled = config.screen_capture_vision or config.screen_capture_gemini

        if not screen_enabled:
            return

        if is_background:
            self.sidebar.set_status("● Screen reading: ACTIVE")
        else:
            if self._speech_service.is_active:
                self.sidebar.set_status("● Gemini Live active (screen paused)")
            else:
                self.sidebar.set_status("● Screen reading: PAUSED")
                QTimer.singleShot(2000, self._update_status)

    def _reload_screen_settings(self):
        config = self.orchestrator.config
        self._screen_service.vision_enabled = config.screen_capture_vision
        self._screen_service.gemini_enabled = config.screen_capture_gemini
        self._screen_service.monitor = config.screen_capture_monitor
        self._screen_service.interval = config.screen_capture_interval

    def closeEvent(self, event):
        self._screen_service.stop()
        self._speech_service.shutdown()
        asyncio.create_task(self.orchestrator.close())
        event.accept()
