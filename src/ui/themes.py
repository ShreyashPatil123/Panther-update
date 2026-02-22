"""UI themes and styles — luxury panther obsidian-black + glowing orange resin.

Industry-standard advanced QSS with:
  • Gradient backgrounds & frosted glass surfaces
  • Glowing focus borders & neon hover accents
  • Premium typography with letter-spacing
  • Ultra-refined scrollbars, inputs, and buttons
  • Subtle surface elevation hierarchy
"""

# ── Panther Dark (default) ──────────────────────────────────────────────────
DARK_COLORS = {
    "background": "#0A0A0A",        # pure black
    "surface": "#111111",           # sidebar
    "surface_variant": "#1a1a1a",   # hover states
    "surface_elevated": "#141414",  # cards / elevated
    "primary": "#FF6B35",           # glowing orange resin
    "primary_variant": "#FF8C42",   # lighter orange
    "primary_muted": "rgba(255, 107, 53, 0.12)",
    "secondary": "#FFB347",         # amber glow
    "accent_gold": "#FFD700",       # golden shimmer
    "text": "#e8e8e8",              # clean white
    "text_secondary": "#888888",    # muted
    "text_tertiary": "#555555",     # very muted
    "border": "#222222",            # subtle borders
    "border_focus": "#FF6B35",
    "error": "#FF4500",
    "success": "#FF8C42",
    "warning": "#FFA500",
    "user_message_bg": "#1a1a1a",   # dark user pill
    "ai_message_bg": "transparent",
    "input_bg": "#141414",          # input bg
    "scrollbar_bg": "transparent",
    "scrollbar_handle": "#2a2a2a",
    "glow": "rgba(255, 107, 53, 0.25)",
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
    """Generate QSS stylesheet from color palette — advanced effects."""
    return f"""
    /* ═══════════════════════════════════════════════════════════════════
       GLOBAL — Panther Premium Dark UI
       ═══════════════════════════════════════════════════════════════════ */
    QMainWindow {{
        background-color: {c["background"]};
        color: {c["text"]};
    }}
    QWidget {{
        background-color: {c["background"]};
        color: {c["text"]};
        font-family: 'Inter', 'Segoe UI', -apple-system, sans-serif;
        font-size: 13px;
    }}

    /* ═══ SIDEBAR — frosted glass panel ══════════════════════════════════ */
    QWidget#sidebar {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 #131313, stop:0.5 {c["surface"]}, stop:1 #0d0d0d
        );
        border-right: 1px solid {c["border"]};
    }}

    /* ═══ CHAT AREA ═════════════════════════════════════════════════════ */
    QScrollArea#chatArea {{
        background-color: {c["background"]};
        border: none;
    }}

    /* ═══ MESSAGE BUBBLES — elevated cards with glow ════════════════════ */
    QFrame#userMessage {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:1, y2:1,
            stop:0 #1e1e1e, stop:1 {c["user_message_bg"]}
        );
        border-radius: 18px;
        border: 1px solid #2a2a2a;
    }}
    QFrame#userMessage:hover {{
        border: 1px solid #333333;
    }}
    QFrame#aiMessage {{
        background-color: transparent;
        border: none;
    }}

    /* ═══ INPUT AREA — elevated glass panel ═════════════════════════════ */
    QFrame#inputArea {{
        background-color: {c["background"]};
        border-top: none;
    }}

    QFrame#inputFrame {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 #1a1a1a, stop:1 #141414
        );
        border: 1px solid #2a2a2a;
        border-radius: 24px;
    }}
    QFrame#inputFrame:hover {{
        border: 1px solid #333333;
    }}

    QTextEdit#messageInput {{
        background-color: transparent;
        color: {c["text"]};
        border: none;
        padding: 10px 16px;
        font-size: 14px;
        line-height: 1.5;
        selection-background-color: rgba(255, 107, 53, 0.35);
        selection-color: #ffffff;
    }}

    /* ═══ BUTTONS — premium with gradient + glow states ═════════════════ */
    QPushButton {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 {c["primary_variant"]}, stop:1 {c["primary"]}
        );
        color: #0A0A0A;
        border: none;
        border-radius: 12px;
        padding: 8px 18px;
        font-weight: 600;
        font-size: 13px;
        letter-spacing: 0.3px;
    }}
    QPushButton:hover {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 #FFa060, stop:1 {c["primary_variant"]}
        );
    }}
    QPushButton:pressed {{
        background-color: {c["primary"]};
        padding-top: 9px;
        padding-bottom: 7px;
    }}
    QPushButton:disabled {{
        background-color: {c["surface_variant"]};
        color: {c["text_tertiary"]};
    }}

    /* Secondary / ghost button — glass style */
    QPushButton#secondary {{
        background-color: rgba(255, 255, 255, 0.04);
        color: {c["text"]};
        border: 1px solid {c["border"]};
    }}
    QPushButton#secondary:hover {{
        background-color: rgba(255, 107, 53, 0.08);
        border-color: rgba(255, 107, 53, 0.4);
        color: {c["primary_variant"]};
    }}

    /* Sidebar navigation — sleek pill buttons */
    QPushButton#sidebarButton {{
        background-color: transparent;
        color: {c["text_secondary"]};
        border: none;
        border-radius: 10px;
        padding: 10px 14px;
        text-align: left;
        font-size: 13px;
        font-weight: 500;
        letter-spacing: 0.2px;
    }}
    QPushButton#sidebarButton:hover {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(255,255,255,0.06), stop:1 rgba(255,255,255,0.02)
        );
        color: {c["text"]};
    }}
    QPushButton#sidebarButton:checked {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(255,107,53,0.15), stop:1 rgba(255,107,53,0.06)
        );
        color: {c["primary"]};
        font-weight: 600;
    }}

    /* ═══ LABELS ════════════════════════════════════════════════════════ */
    QLabel {{
        color: {c["text"]};
        background: transparent;
        letter-spacing: 0.1px;
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
        letter-spacing: 0.2px;
    }}

    /* ═══ SCROLLBARS — ultra-thin, auto-fade feel ═══════════════════════ */
    QScrollBar:vertical {{
        background-color: transparent;
        width: 5px;
        margin: 4px 1px;
    }}
    QScrollBar::handle:vertical {{
        background-color: rgba(255, 255, 255, 0.08);
        min-height: 40px;
        border-radius: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: rgba(255, 107, 53, 0.5);
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    QScrollBar:horizontal {{
        background-color: transparent;
        height: 5px;
        margin: 1px 4px;
    }}
    QScrollBar::handle:horizontal {{
        background-color: rgba(255, 255, 255, 0.08);
        min-width: 40px;
        border-radius: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: rgba(255, 107, 53, 0.5);
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}

    /* ═══ COMBO BOX — glass dropdown ═══════════════════════════════════ */
    QComboBox {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 #181818, stop:1 {c["surface"]}
        );
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
        padding: 8px 32px 8px 12px;
        min-height: 32px;
        font-size: 13px;
    }}
    QComboBox:hover {{
        border-color: rgba(255, 107, 53, 0.5);
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
        background-color: #181818;
        color: {c["text"]};
        border: 1px solid #2a2a2a;
        selection-background-color: rgba(255, 107, 53, 0.2);
        selection-color: {c["primary_variant"]};
        outline: none;
        padding: 4px;
        border-radius: 10px;
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 32px;
        padding: 6px 12px;
        border-radius: 6px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: rgba(255, 255, 255, 0.06);
    }}

    /* ═══ LINE EDIT — glowing focus border ═════════════════════════════ */
    QLineEdit {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 #161616, stop:1 {c["surface"]}
        );
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
        padding: 8px 12px;
        font-size: 13px;
        selection-background-color: rgba(255, 107, 53, 0.35);
    }}
    QLineEdit:hover {{
        border-color: #333333;
    }}
    QLineEdit:focus {{
        border: 1px solid {c["primary"]};
    }}

    /* ═══ CHECKBOXES — premium toggle style ═════════════════════════════ */
    QCheckBox {{
        color: {c["text"]};
        spacing: 8px;
        font-size: 13px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 5px;
        border: 1px solid #333333;
        background-color: rgba(255, 255, 255, 0.04);
    }}
    QCheckBox::indicator:hover {{
        border-color: rgba(255, 107, 53, 0.5);
        background-color: rgba(255, 107, 53, 0.06);
    }}
    QCheckBox::indicator:checked {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:1, y2:1,
            stop:0 {c["primary_variant"]}, stop:1 {c["primary"]}
        );
        border-color: {c["primary"]};
    }}

    /* ═══ GROUP BOX — subtle card container ═════════════════════════════ */
    QGroupBox {{
        border: 1px solid {c["border"]};
        border-radius: 14px;
        margin-top: 14px;
        padding-top: 16px;
        font-weight: 600;
        color: {c["text"]};
        background-color: rgba(255, 255, 255, 0.02);
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 16px;
        padding: 0 8px;
        color: {c["text_secondary"]};
        letter-spacing: 0.3px;
    }}

    /* ═══ DIALOGS — elevated glass panel ════════════════════════════════ */
    QDialog {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 #121212, stop:1 {c["background"]}
        );
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 16px;
    }}

    /* ═══ PROGRESS BAR — gradient fill ═════════════════════════════════ */
    QProgressBar {{
        border: none;
        border-radius: 5px;
        background-color: rgba(255, 255, 255, 0.06);
        text-align: center;
        color: {c["text"]};
        font-size: 11px;
    }}
    QProgressBar::chunk {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["primary"]}, stop:1 {c["secondary"]}
        );
        border-radius: 5px;
    }}

    /* ═══ TAB WIDGET — underline accent ═════════════════════════════════ */
    QTabWidget::pane {{
        border: 1px solid {c["border"]};
        background-color: {c["background"]};
        border-radius: 12px;
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {c["text_secondary"]};
        padding: 10px 20px;
        border: none;
        font-weight: 500;
        letter-spacing: 0.3px;
    }}
    QTabBar::tab:selected {{
        color: {c["primary"]};
        border-bottom: 2px solid {c["primary"]};
    }}
    QTabBar::tab:hover:!selected {{
        color: {c["text"]};
    }}

    /* ═══ SPIN BOX — consistent glass style ════════════════════════════ */
    QSpinBox, QDoubleSpinBox {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 #161616, stop:1 {c["surface"]}
        );
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
        padding: 6px 10px;
        font-size: 13px;
    }}
    QSpinBox:hover, QDoubleSpinBox:hover {{
        border-color: #333333;
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {c["primary"]};
    }}

    /* ═══ TOOLTIPS — floating glass chip ════════════════════════════════ */
    QToolTip {{
        background-color: #1e1e1e;
        color: {c["text"]};
        border: 1px solid #333333;
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 12px;
    }}

    /* ═══ MENU — glass dropdown ════════════════════════════════════════ */
    QMenu {{
        background-color: #181818;
        color: {c["text"]};
        border: 1px solid #2a2a2a;
        border-radius: 12px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 8px 24px 8px 16px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background-color: rgba(255, 107, 53, 0.12);
        color: {c["primary_variant"]};
    }}
    QMenu::separator {{
        height: 1px;
        background: #2a2a2a;
        margin: 4px 8px;
    }}

    /* ═══ SLIDER — premium track + handle ═══════════════════════════════ */
    QSlider::groove:horizontal {{
        height: 4px;
        background: rgba(255, 255, 255, 0.08);
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 {c["primary_variant"]}, stop:1 {c["primary"]}
        );
    }}
    QSlider::handle:horizontal:hover {{
        background-color: {c["secondary"]};
    }}
    QSlider::sub-page:horizontal {{
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["primary"]}, stop:1 {c["secondary"]}
        );
        border-radius: 2px;
    }}

    /* ═══ STATUS BAR ═══════════════════════════════════════════════════ */
    QStatusBar {{
        background-color: {c["surface"]};
        color: {c["text_secondary"]};
        border-top: 1px solid {c["border"]};
        font-size: 11px;
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
