"""UI themes and styles for the application."""

# Dark theme colors (inspired by NVIDIA)
DARK_COLORS = {
    "background": "#1a1a1a",
    "surface": "#2d2d2d",
    "surface_variant": "#3d3d3d",
    "primary": "#76b900",  # NVIDIA green
    "primary_variant": "#5a8c00",
    "secondary": "#00d4aa",
    "text": "#ffffff",
    "text_secondary": "#b0b0b0",
    "border": "#404040",
    "error": "#ff5252",
    "success": "#4caf50",
    "warning": "#ffc107",
    "user_message_bg": "#2d3748",
    "ai_message_bg": "#1e3a5f",
    "input_bg": "#363636",
}

# Light theme colors
LIGHT_COLORS = {
    "background": "#f5f5f5",
    "surface": "#ffffff",
    "surface_variant": "#e0e0e0",
    "primary": "#76b900",
    "primary_variant": "#5a8c00",
    "secondary": "#00b894",
    "text": "#212121",
    "text_secondary": "#757575",
    "border": "#e0e0e0",
    "error": "#d32f2f",
    "success": "#388e3c",
    "warning": "#f57c00",
    "user_message_bg": "#e3f2fd",
    "ai_message_bg": "#f3e5f5",
    "input_bg": "#ffffff",
}


def get_stylesheet(colors: dict) -> str:
    """Generate QSS stylesheet from color palette.

    Args:
        colors: Color dictionary

    Returns:
        QSS stylesheet string
    """
    return f"""
    /* Main Window */
    QMainWindow {{
        background-color: {colors["background"]};
        color: {colors["text"]};
    }}

    /* Central Widget */
    QWidget {{
        background-color: {colors["background"]};
        color: {colors["text"]};
    }}

    /* Sidebar */
    QFrame#sidebar {{
        background-color: {colors["surface"]};
        border-right: 1px solid {colors["border"]};
    }}

    /* Chat Area */
    QScrollArea#chatArea {{
        background-color: {colors["background"]};
        border: none;
    }}

    /* Message Bubbles */
    QFrame#userMessage {{
        background-color: {colors["user_message_bg"]};
        border-radius: 12px;
        padding: 12px;
    }}

    QFrame#aiMessage {{
        background-color: {colors["ai_message_bg"]};
        border-radius: 12px;
        padding: 12px;
    }}

    /* Input Area */
    QFrame#inputArea {{
        background-color: {colors["surface"]};
        border-top: 1px solid {colors["border"]};
    }}

    QTextEdit#messageInput {{
        background-color: {colors["input_bg"]};
        color: {colors["text"]};
        border: 1px solid {colors["border"]};
        border-radius: 8px;
        padding: 8px;
        font-size: 14px;
    }}

    QTextEdit#messageInput:focus {{
        border: 2px solid {colors["primary"]};
    }}

    /* Buttons */
    QPushButton {{
        background-color: {colors["primary"]};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 16px;
        font-weight: 500;
    }}

    QPushButton:hover {{
        background-color: {colors["primary_variant"]};
    }}

    QPushButton:pressed {{
        background-color: {colors["primary_variant"]};
    }}

    QPushButton:disabled {{
        background-color: {colors["surface_variant"]};
        color: {colors["text_secondary"]};
    }}

    QPushButton#secondary {{
        background-color: {colors["surface_variant"]};
        color: {colors["text"]};
        border: 1px solid {colors["border"]};
    }}

    QPushButton#secondary:hover {{
        background-color: {colors["surface"]};
    }}

    /* Sidebar Buttons */
    QPushButton#sidebarButton {{
        background-color: transparent;
        color: {colors["text_secondary"]};
        border: none;
        border-radius: 4px;
        padding: 10px 16px;
        text-align: left;
    }}

    QPushButton#sidebarButton:hover {{
        background-color: {colors["surface_variant"]};
        color: {colors["text"]};
    }}

    QPushButton#sidebarButton:checked {{
        background-color: {colors["surface_variant"]};
        color: {colors["primary"]};
        border-left: 3px solid {colors["primary"]};
    }}

    /* Labels */
    QLabel {{
        color: {colors["text"]};
    }}

    QLabel#title {{
        font-size: 18px;
        font-weight: bold;
        color: {colors["text"]};
    }}

    QLabel#subtitle {{
        font-size: 14px;
        color: {colors["text_secondary"]};
    }}

    /* Scrollbars */
    QScrollBar:vertical {{
        background-color: {colors["surface"]};
        width: 12px;
        margin: 0px;
    }}

    QScrollBar::handle:vertical {{
        background-color: {colors["surface_variant"]};
        min-height: 30px;
        border-radius: 6px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {colors["text_secondary"]};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    /* Combo Box */
    QComboBox {{
        background-color: {colors["surface"]};
        color: {colors["text"]};
        border: 1px solid {colors["border"]};
        border-radius: 6px;
        padding: 6px 12px;
        min-height: 30px;
    }}

    QComboBox:hover {{
        border: 1px solid {colors["primary"]};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 30px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {colors["surface"]};
        color: {colors["text"]};
        border: 1px solid {colors["border"]};
        selection-background-color: {colors["primary"]};
    }}

    /* Line Edit */
    QLineEdit {{
        background-color: {colors["surface"]};
        color: {colors["text"]};
        border: 1px solid {colors["border"]};
        border-radius: 6px;
        padding: 8px;
    }}

    QLineEdit:focus {{
        border: 2px solid {colors["primary"]};
    }}

    /* Check Box */
    QCheckBox {{
        color: {colors["text"]};
    }}

    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 2px solid {colors["border"]};
        background-color: {colors["surface"]};
    }}

    QCheckBox::indicator:checked {{
        background-color: {colors["primary"]};
        border: 2px solid {colors["primary"]};
    }}

    /* Group Box */
    QGroupBox {{
        border: 1px solid {colors["border"]};
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 12px;
        font-weight: bold;
        color: {colors["text"]};
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 8px;
    }}

    /* Dialog */
    QDialog {{
        background-color: {colors["background"]};
        color: {colors["text"]};
    }}

    /* Progress Bar */
    QProgressBar {{
        border: none;
        border-radius: 4px;
        background-color: {colors["surface_variant"]};
        text-align: center;
        color: {colors["text"]};
    }}

    QProgressBar::chunk {{
        background-color: {colors["primary"]};
        border-radius: 4px;
    }}

    /* Tab Widget */
    QTabWidget::pane {{
        border: 1px solid {colors["border"]};
        background-color: {colors["background"]};
    }}

    QTabBar::tab {{
        background-color: {colors["surface"]};
        color: {colors["text_secondary"]};
        padding: 10px 20px;
        border: none;
    }}

    QTabBar::tab:selected {{
        background-color: {colors["background"]};
        color: {colors["primary"]};
        border-bottom: 2px solid {colors["primary"]};
    }}

    QTabBar::tab:hover:!selected {{
        color: {colors["text"]};
    }}
"""


def apply_dark_theme(app):
    """Apply dark theme to QApplication.

    Args:
        app: QApplication instance
    """
    stylesheet = get_stylesheet(DARK_COLORS)
    app.setStyleSheet(stylesheet)


def apply_light_theme(app):
    """Apply light theme to QApplication.

    Args:
        app: QApplication instance
    """
    stylesheet = get_stylesheet(LIGHT_COLORS)
    app.setStyleSheet(stylesheet)
