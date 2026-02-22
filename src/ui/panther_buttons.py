"""Custom panther-themed buttons — QPainter vector art + animations.

Grok-accurate design:
  • PantherSendButton  — white ↑ arrow in dark circle, hover glow
  • PantherMicButton   — minimalist mic icon, concentric rings when recording
  • PantherAttachButton — clean + icon, morphs to panther eye when files attached
"""
import math
import os
from pathlib import Path

from PyQt6.QtCore import (
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    pyqtProperty,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import QPushButton, QGraphicsDropShadowEffect


# ── Color constants ─────────────────────────────────────────────────────────
ORANGE = QColor("#FF6B35")
ORANGE_LIGHT = QColor("#FF8C42")
AMBER = QColor("#FFB347")
GOLD = QColor("#FFD700")
DARK = QColor("#0A0A0A")
SURFACE = QColor("#141414")
WHITE = QColor("#e8e8e8")
MUTED = QColor("#888888")
BORDER = QColor("#2a2a2a")
BORDER_LIGHT = QColor("#3a3a3a")


class PantherSendButton(QPushButton):
    """Send button — white upward arrow in dark circle (Grok-accurate).

    Design:
      • Dark circle (#1a1a1a) with subtle border
      • Clean white arrow pointing up (↑)
      • Hover: background brightens, subtle orange glow
      • Pressed: flash effect
    """

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Send message")

        self._is_hovered = False
        self._is_pressed = False

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._is_pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._is_pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 1

        # ── Background circle ──
        if self._is_pressed:
            bg = QColor("#444444")
        elif self._is_hovered:
            bg = QColor("#333333")
        else:
            bg = QColor("#222222")

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # ── Arrow icon (↑) ──
        arrow_color = QColor("#ffffff") if self._is_hovered else QColor("#e0e0e0")
        p.setPen(QPen(arrow_color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Vertical line
        p.drawLine(QPointF(cx, cy + 7), QPointF(cx, cy - 6))
        # Arrow head  (V shape pointing up)
        p.drawLine(QPointF(cx - 5, cy - 1), QPointF(cx, cy - 7))
        p.drawLine(QPointF(cx + 5, cy - 1), QPointF(cx, cy - 7))

        p.end()


class PantherMicButton(QPushButton):
    """Microphone button — minimalist mic capsule icon.

    Design:
      • Transparent background, subtle border on hover
      • Clean mic icon in muted gray, brightens on hover
      • Recording: orange pulsating rings + icon turns gold
      • Plays panther roar sound on activation (if available)
    """

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setFixedSize(36, 36)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Hold to speak")

        self._ring_phase = 0.0
        self._is_hovered = False

        # Ring animation timer
        self._ring_timer = QTimer(self)
        self._ring_timer.timeout.connect(self._animate_rings)
        self._ring_timer.start(50)

        # Sound player (lazy-loaded)
        self._player = None

    def _animate_rings(self):
        """Animate concentric rings when recording."""
        if self.isChecked():
            self._ring_phase += 0.10
            self.update()

    def _play_roar(self):
        """Play panther roar sound effect."""
        try:
            from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
            roar_path = Path(__file__).parent.parent.parent / "assest" / "Panther_roar.mp3"
            if roar_path.exists():
                if self._player is None:
                    self._player = QMediaPlayer(self)
                    self._audio_output = QAudioOutput(self)
                    self._player.setAudioOutput(self._audio_output)
                    self._audio_output.setVolume(0.5)
                from PyQt6.QtCore import QUrl
                self._player.setSource(QUrl.fromLocalFile(str(roar_path)))
                self._player.play()
        except ImportError:
            pass

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def nextCheckState(self):
        """Push-to-talk: checked state controlled externally."""
        pass

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        is_recording = self.isChecked()

        # ── Subtle hover circle ──
        if self._is_hovered or is_recording:
            bg_alpha = 30 if is_recording else 15
            bg = QColor(255, 107, 53, bg_alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(bg))
            p.drawEllipse(QRectF(2, 2, w - 4, h - 4))

        # ── Pulsating rings (recording only) ──
        if is_recording:
            for i in range(3):
                phase_offset = self._ring_phase + i * 1.0
                progress = (phase_offset % 2.5) / 2.5
                alpha = max(0, int(150 * (1 - progress)))
                ring_color = QColor(ORANGE_LIGHT)
                ring_color.setAlpha(alpha)
                p.setPen(QPen(ring_color, 1.2 - progress * 0.6))
                p.setBrush(Qt.BrushStyle.NoBrush)
                radius = 8 + progress * 10
                p.drawEllipse(QPointF(cx, cy), radius, radius)

        # ── Mic icon ──
        if is_recording:
            icon_color = GOLD
            pen_width = 2.0
        elif self._is_hovered:
            icon_color = WHITE
            pen_width = 1.8
        else:
            icon_color = MUTED
            pen_width = 1.6

        p.setPen(QPen(icon_color, pen_width))
        p.setBrush(Qt.BrushStyle.NoBrush)

        if is_recording:
            # Roar mouth shape
            p.setPen(QPen(GOLD, 2.0))
            mouth = QPainterPath()
            mouth.moveTo(cx - 6, cy - 2)
            mouth.lineTo(cx - 3, cy - 6)
            mouth.lineTo(cx, cy - 4)
            mouth.lineTo(cx + 3, cy - 6)
            mouth.lineTo(cx + 6, cy - 2)
            mouth.lineTo(cx + 7, cy + 2)
            mouth.lineTo(cx + 3, cy + 5)
            mouth.lineTo(cx, cy + 6)
            mouth.lineTo(cx - 3, cy + 5)
            mouth.lineTo(cx - 7, cy + 2)
            mouth.closeSubpath()
            p.drawPath(mouth)

            # Center line
            p.setPen(QPen(AMBER, 1.0))
            p.drawLine(QPointF(cx, cy - 2), QPointF(cx, cy + 3))
        else:
            # Clean mic capsule
            mic = QPainterPath()
            mic.addRoundedRect(QRectF(cx - 3.5, cy - 8, 7, 11), 3.5, 3.5)
            p.drawPath(mic)
            # Stand
            p.drawLine(QPointF(cx, cy + 3), QPointF(cx, cy + 7))
            p.drawLine(QPointF(cx - 4, cy + 7), QPointF(cx + 4, cy + 7))
            # Pickup arc
            arc_rect = QRectF(cx - 6, cy - 1, 12, 8)
            p.drawArc(arc_rect, 0, 180 * 16)

        p.end()


class PantherAttachButton(QPushButton):
    """Attachment button — clean + icon (Grok-accurate).

    Design:
      • Default: muted gray + icon
      • Hover: brightens to white
      • Active (files attached): morphs to panther eye with iris gradient
    """

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Attach files")

        self._has_files = False
        self._is_hovered = False
        self._pupil_dilation = 0.0

        self._pupil_anim = QPropertyAnimation(self, b"pupilDilation")
        self._pupil_anim.setDuration(300)

    def _get_pupil_dilation(self) -> float:
        return self._pupil_dilation

    def _set_pupil_dilation(self, val: float):
        self._pupil_dilation = val
        self.update()

    pupilDilation = pyqtProperty(float, _get_pupil_dilation, _set_pupil_dilation)

    def set_has_files(self, has_files: bool):
        """Switch between + icon and panther eye modes."""
        self._has_files = has_files
        self.update()

    def enterEvent(self, event):
        self._is_hovered = True
        if self._has_files:
            self._pupil_anim.stop()
            self._pupil_anim.setStartValue(self._pupil_dilation)
            self._pupil_anim.setEndValue(0.8)
            self._pupil_anim.start()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        if self._has_files:
            self._pupil_anim.stop()
            self._pupil_anim.setStartValue(self._pupil_dilation)
            self._pupil_anim.setEndValue(0.2)
            self._pupil_anim.start()
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        # ── Subtle hover background ──
        if self._is_hovered:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(255, 255, 255, 12)))
            p.drawEllipse(QRectF(2, 2, w - 4, h - 4))

        if self._has_files:
            self._draw_panther_eye(p, cx, cy)
        else:
            self._draw_plus_icon(p, cx, cy)

        p.end()

    def _draw_plus_icon(self, p: QPainter, cx: float, cy: float):
        """Draw a clean + icon (Grok-style attachment button)."""
        if self._is_hovered:
            color = QColor("#e0e0e0")
            pen_width = 2.2
        else:
            color = QColor("#888888")
            pen_width = 2.0

        p.setPen(QPen(color, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)

        size = 7  # half-length of each cross arm
        # Vertical line
        p.drawLine(QPointF(cx, cy - size), QPointF(cx, cy + size))
        # Horizontal line
        p.drawLine(QPointF(cx - size, cy), QPointF(cx + size, cy))

    def _draw_panther_eye(self, p: QPainter, cx: float, cy: float):
        """Draw panther eye with vertical slit pupil."""
        # Outer glow
        if self._is_hovered:
            halo = QRadialGradient(QPointF(cx, cy), 18)
            halo.setColorAt(0.4, QColor(255, 107, 53, 40))
            halo.setColorAt(1.0, QColor(255, 107, 53, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(halo))
            p.drawEllipse(QRectF(0, 0, self.width(), self.height()))

        # Eye outline
        eye_pen_color = AMBER if self._is_hovered else ORANGE
        p.setPen(QPen(eye_pen_color, 1.8))

        # Iris gradient
        iris = QRadialGradient(QPointF(cx, cy), 10)
        iris.setColorAt(0, QColor(255, 215, 0, 120))
        iris.setColorAt(0.4, QColor(255, 179, 71, 100))
        iris.setColorAt(0.8, QColor(255, 107, 53, 60))
        iris.setColorAt(1, QColor(255, 107, 53, 20))
        p.setBrush(QBrush(iris))

        # Almond eye shape
        eye = QPainterPath()
        eye.moveTo(cx - 12, cy)
        eye.cubicTo(QPointF(cx - 6, cy - 8), QPointF(cx + 6, cy - 8), QPointF(cx + 12, cy))
        eye.cubicTo(QPointF(cx + 6, cy + 8), QPointF(cx - 6, cy + 8), QPointF(cx - 12, cy))
        p.drawPath(eye)

        # Pupil slit
        pupil_w = 1.2 + self._pupil_dilation * 4.5
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#0A0A0A")))
        p.drawEllipse(QPointF(cx, cy), pupil_w, 6)

        # Catchlight
        p.setBrush(QBrush(QColor(255, 255, 255, 180)))
        p.drawEllipse(QPointF(cx - 2.5, cy - 2.5), 1.5, 1.5)
