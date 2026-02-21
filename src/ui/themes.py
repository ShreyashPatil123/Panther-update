"""UI themes and styles — luxury panther obsidian-black + glowing orange resin.

Inspired by black crystal tiles with luminescent orange resin veins,
panther-themed sleek design language, and premium glassmorphism effects.
"""

# ── Panther Dark (default) ──────────────────────────────────────────────────
DARK_COLORS = {
    "background": "#0A0A0A",        # obsidian black
    "surface": "#121215",           # sidebar / input area — slightly warm
    "surface_variant": "#1a1712",   # hover states — warm dark
    "surface_elevated": "#161410",  # cards / elevated surfaces
    "primary": "#FF6B35",           # glowing orange resin
    "primary_variant": "#FF8C42",   # lighter orange
    "primary_muted": "rgba(255, 107, 53, 0.12)",  # subtle orange tint
    "secondary": "#FFB347",         # amber glow
    "accent_gold": "#FFD700",       # golden shimmer
    "text": "#f0ece8",              # warm white
    "text_secondary": "#8a8078",    # warm muted
    "text_tertiary": "#5a5248",     # very muted warm
    "border": "#1e1a14",            # warm subtle borders
    "border_focus": "#FF6B35",      # focused input border — orange
    "error": "#FF4500",             # red-orange
    "success": "#FF8C42",           # orange pulse (replaces green)
    "warning": "#FFA500",           # amber
    "user_message_bg": "#1a1510",   # warm dark user pill
    "ai_message_bg": "transparent", # no background for AI
    "input_bg": "#0f0e0c",         # deep warm input bg
    "scrollbar_bg": "transparent",
    "scrollbar_handle": "#2a2218",
    "glow": "rgba(255, 107, 53, 0.25)",  # orange glow for shadows
}

# ── Light theme (unchanged, for completeness) ──────────────────────────────
LIGHT_COLORS = {
    "background": "#faf8f5",
    "surface": "#ffffff",
    "surface_variant": "#f5f0ea",
    "surface_elevated": "#ffffff",
    "primary": "#FF6B35",
    "primary_variant": "#e55a25",
    "primary_muted": "rgba(255, 107, 53, 0.08)",
    "secondary": "#FFB347",
    "accent_gold": "#FFD700",
    "text": "#1a1410",
    "text_secondary": "#6a6058",
    "text_tertiary": "#9a9088",
    "border": "#e8e0d8",
    "border_focus": "#FF6B35",
    "error": "#d32f2f",
    "success": "#e55a25",
    "warning": "#f57c00",
    "user_message_bg": "#fff3e8",
    "ai_message_bg": "transparent",
    "input_bg": "#ffffff",
    "scrollbar_bg": "transparent",
    "scrollbar_handle": "#d0c8c0",
    "glow": "rgba(255, 107, 53, 0.15)",
}


def get_stylesheet(c: dict) -> str:
    """Generate QSS stylesheet from color palette."""
    return f"""
    /* ═══════════════════════════════════════════════════════════════════
       GLOBAL — Panther Orange Resin Theme
       ═══════════════════════════════════════════════════════════════════ */
    QMainWindow {{
        background-color: {c["background"]};
        color: {c["text"]};
    }}
    QWidget {{
        background-color: {c["background"]};
        color: {c["text"]};
        font-family: 'Inter', 'Segoe UI', -apple-system, sans-serif;
    }}

    /* ═══ SIDEBAR — frosted glass with orange accent ════════════════════ */
    QFrame#sidebar {{
        background-color: {c["surface"]};
        border-right: 1px solid {c["border"]};
    }}

    /* ═══ CHAT AREA ═════════════════════════════════════════════════════ */
    QScrollArea#chatArea {{
        background-color: {c["background"]};
        border: none;
    }}

    /* ═══ MESSAGE BUBBLES ═══════════════════════════════════════════════ */
    QFrame#userMessage {{
        background-color: {c["user_message_bg"]};
        border-radius: 16px;
        border: 1px solid {c["border"]};
    }}
    QFrame#aiMessage {{
        background-color: transparent;
        border: none;
    }}

    /* ═══ INPUT AREA ════════════════════════════════════════════════════ */
    QFrame#inputArea {{
        background-color: {c["background"]};
        border-top: none;
    }}

    QTextEdit#messageInput {{
        background-color: {c["input_bg"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 14px;
        padding: 10px 16px;
        font-size: 14px;
        selection-background-color: {c["primary"]};
    }}
    QTextEdit#messageInput:focus {{
        border: 1px solid {c["primary"]};
    }}

    /* ═══ BUTTONS ═══════════════════════════════════════════════════════ */
    QPushButton {{
        background-color: {c["primary"]};
        color: #0A0A0A;
        border: none;
        border-radius: 12px;
        padding: 8px 18px;
        font-weight: 600;
        font-size: 13px;
    }}
    QPushButton:hover {{
        background-color: {c["primary_variant"]};
    }}
    QPushButton:pressed {{
        background-color: {c["primary"]};
    }}
    QPushButton:disabled {{
        background-color: {c["surface_variant"]};
        color: {c["text_tertiary"]};
    }}

    /* Secondary / ghost button */
    QPushButton#secondary {{
        background-color: transparent;
        color: {c["text"]};
        border: 1px solid {c["border"]};
    }}
    QPushButton#secondary:hover {{
        background-color: {c["surface_variant"]};
        border-color: {c["primary"]};
    }}

    /* Sidebar navigation */
    QPushButton#sidebarButton {{
        background-color: transparent;
        color: {c["text_secondary"]};
        border: none;
        border-radius: 10px;
        padding: 10px 14px;
        text-align: left;
        font-size: 13px;
        font-weight: 500;
    }}
    QPushButton#sidebarButton:hover {{
        background-color: {c["surface_variant"]};
        color: {c["text"]};
    }}
    QPushButton#sidebarButton:checked {{
        background-color: {c["primary_muted"]};
        color: {c["primary"]};
    }}

    /* ═══ LABELS ════════════════════════════════════════════════════════ */
    QLabel {{
        color: {c["text"]};
        background: transparent;
    }}
    QLabel#title {{
        font-size: 16px;
        font-weight: 700;
        color: {c["primary"]};
        letter-spacing: -0.3px;
    }}
    QLabel#subtitle {{
        font-size: 13px;
        color: {c["text_secondary"]};
    }}

    /* ═══ SCROLLBARS (ultra-thin, warm) ═════════════════════════════════ */
    QScrollBar:vertical {{
        background-color: transparent;
        width: 6px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background-color: {c["scrollbar_handle"]};
        min-height: 40px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {c["primary"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}

    /* ═══ COMBO BOX ═════════════════════════════════════════════════════ */
    QComboBox {{
        background-color: {c["surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
        padding: 8px 32px 8px 12px;
        min-height: 32px;
        font-size: 13px;
    }}
    QComboBox:hover {{
        border-color: {c["primary"]};
    }}
    QComboBox:focus {{
        border: 1px solid {c["primary"]};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 28px;
        border: none;
        background: transparent;
    }}
    QComboBox::down-arrow {{
        width: 10px;
        height: 10px;
        image: none;
    }}
    QComboBox QAbstractItemView {{
        background-color: {c["surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        selection-background-color: {c["primary"]};
        selection-color: #0A0A0A;
        outline: none;
        padding: 4px;
        border-radius: 10px;
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 30px;
        padding: 6px 10px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: {c["surface_variant"]};
    }}

    /* ═══ LINE EDIT ═════════════════════════════════════════════════════ */
    QLineEdit {{
        background-color: {c["surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
        padding: 8px 12px;
        font-size: 13px;
    }}
    QLineEdit:focus {{
        border: 1px solid {c["primary"]};
    }}

    /* ═══ CHECKBOXES ════════════════════════════════════════════════════ */
    QCheckBox {{
        color: {c["text"]};
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 5px;
        border: 1px solid {c["border"]};
        background-color: {c["surface"]};
    }}
    QCheckBox::indicator:checked {{
        background-color: {c["primary"]};
        border-color: {c["primary"]};
    }}

    /* ═══ GROUP BOX ═════════════════════════════════════════════════════ */
    QGroupBox {{
        border: 1px solid {c["border"]};
        border-radius: 12px;
        margin-top: 14px;
        padding-top: 14px;
        font-weight: 600;
        color: {c["text"]};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 8px;
    }}

    /* ═══ DIALOGS ═══════════════════════════════════════════════════════ */
    QDialog {{
        background-color: {c["background"]};
        color: {c["text"]};
    }}

    /* ═══ PROGRESS BAR ═════════════════════════════════════════════════ */
    QProgressBar {{
        border: none;
        border-radius: 5px;
        background-color: {c["surface_variant"]};
        text-align: center;
        color: {c["text"]};
    }}
    QProgressBar::chunk {{
        background-color: {c["primary"]};
        border-radius: 5px;
    }}

    /* ═══ TAB WIDGET ════════════════════════════════════════════════════ */
    QTabWidget::pane {{
        border: 1px solid {c["border"]};
        background-color: {c["background"]};
        border-radius: 10px;
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {c["text_secondary"]};
        padding: 10px 20px;
        border: none;
        font-weight: 500;
    }}
    QTabBar::tab:selected {{
        color: {c["primary"]};
        border-bottom: 2px solid {c["primary"]};
    }}
    QTabBar::tab:hover:!selected {{
        color: {c["text"]};
    }}

    /* ═══ SPIN BOX ══════════════════════════════════════════════════════ */
    QSpinBox, QDoubleSpinBox {{
        background-color: {c["surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
        padding: 6px 10px;
        font-size: 13px;
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {c["primary"]};
    }}
    """


def apply_dark_theme(app):
    """Apply dark theme to QApplication."""
    stylesheet = get_stylesheet(DARK_COLORS)
    app.setStyleSheet(stylesheet)


def apply_light_theme(app):
    """Apply light theme to QApplication."""
    stylesheet = get_stylesheet(LIGHT_COLORS)
    app.setStyleSheet(stylesheet)
