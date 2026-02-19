"""Custom panther-themed buttons — QPainter vector art + animations.

Refined designs informed by Stitch luxury component library.

Three luxury buttons:
  • PantherSendButton  — geometric panther head, breathing glow, outer halo
  • PantherMicButton   — concentric sound rings, roar on activation
  • PantherAttachButton — paperclip → panther eye morph when files pending
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
from PyQt6.QtWidgets import QPushButton


# ── Color constants ─────────────────────────────────────────────────────────
ORANGE = QColor("#FF6B35")
ORANGE_LIGHT = QColor("#FF8C42")
AMBER = QColor("#FFB347")
GOLD = QColor("#FFD700")
DARK = QColor("#0A0A0A")
SURFACE = QColor("#161410")
WARM_DARK = QColor("#1a1510")
BORDER = QColor("#2a2218")
MUTED = QColor("#8a8078")


class PantherSendButton(QPushButton):
    """Send button — geometric panther head silhouette.

    Stitch-informed design:
      • Circular surface (#161410) with subtle orange border
      • Sharp angular panther head facing right (send direction)
      • Idle: breathing pulse + outer glow halo
      • Hover: eyes brighten to gold, glow intensifies, send arrow appears
      • Click: flash effect
    """

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setFixedSize(44, 44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Send message")

        self._glow_opacity = 0.6
        self._is_hovered = False
        self._breath_phase = 0.0

        # Breathing animation timer
        self._breath_timer = QTimer(self)
        self._breath_timer.timeout.connect(self._breathe)
        self._breath_timer.start(50)

    def _breathe(self):
        """Idle breathing pulse."""
        self._breath_phase += 0.08
        self._glow_opacity = 0.5 + 0.15 * math.sin(self._breath_phase)
        self.update()

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        # ── Outer glow halo (Stitch: soft orange glow shadow) ──
        if self._is_hovered:
            halo = QRadialGradient(QPointF(cx, cy), w / 2)
            halo.setColorAt(0.6, QColor(255, 107, 53, 40))
            halo.setColorAt(1.0, QColor(255, 107, 53, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(halo))
            p.drawEllipse(QRectF(0, 0, w, h))

        # ── Background circle — obsidian surface disc ──
        glow_alpha = int(255 * (0.25 if self._is_hovered else self._glow_opacity * 0.12))
        bg = QRadialGradient(QPointF(cx, cy), w / 2 - 2)
        bg.setColorAt(0, QColor(30, 26, 20, glow_alpha + 60))
        bg.setColorAt(0.85, QColor(22, 20, 16, glow_alpha + 40))
        bg.setColorAt(1.0, QColor(ORANGE.red(), ORANGE.green(), ORANGE.blue(), glow_alpha))
        p.setBrush(QBrush(bg))

        pen_color = QColor(ORANGE) if self._is_hovered else QColor(BORDER)
        if self._is_hovered:
            pen_color.setAlpha(220)
        p.setPen(QPen(pen_color, 1.5))
        p.drawEllipse(QRectF(2, 2, w - 4, h - 4))

        # ── Panther head silhouette (Stitch: sharp angular, facing right) ──
        pen_color = AMBER if self._is_hovered else ORANGE
        p.setPen(QPen(pen_color, 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)

        head = QPainterPath()
        # Left ear — sharp triangular
        head.moveTo(cx - 10, cy - 4)
        head.lineTo(cx - 8, cy - 13)
        head.lineTo(cx - 4, cy - 7)
        # Forehead bridge
        head.lineTo(cx + 1, cy - 9)
        # Right ear — sharp triangular
        head.lineTo(cx + 5, cy - 13)
        head.lineTo(cx + 9, cy - 4)
        # Right cheek → snout
        head.lineTo(cx + 11, cy - 1)
        head.lineTo(cx + 14, cy + 1)  # nose tip → send direction
        # Jaw line
        head.lineTo(cx + 10, cy + 5)
        head.lineTo(cx + 5, cy + 8)
        head.lineTo(cx - 2, cy + 8)
        head.lineTo(cx - 8, cy + 4)
        head.closeSubpath()
        p.drawPath(head)

        # ── Eyes — glowing amber dots ──
        eye_color = GOLD if self._is_hovered else AMBER
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(eye_color))
        # Left eye
        p.drawEllipse(QPointF(cx - 4, cy - 1), 2.0, 1.5)
        # Right eye
        p.drawEllipse(QPointF(cx + 5, cy - 1), 2.0, 1.5)

        # ── Eye glow halo (tiny) ──
        if self._is_hovered:
            eye_glow = QColor(GOLD)
            eye_glow.setAlpha(60)
            p.setBrush(QBrush(eye_glow))
            p.drawEllipse(QPointF(cx - 4, cy - 1), 3.5, 3.0)
            p.drawEllipse(QPointF(cx + 5, cy - 1), 3.5, 3.0)

        # ── Nose bridge accent line ──
        p.setPen(QPen(pen_color, 1.2))
        p.drawLine(QPointF(cx, cy - 6), QPointF(cx + 1, cy + 1))

        # ── Send arrow accent (hover only — Stitch gold arrow) ──
        if self._is_hovered:
            p.setPen(QPen(GOLD, 1.8))
            p.drawLine(QPointF(cx + 13, cy + 1), QPointF(cx + 18, cy + 1))
            p.drawLine(QPointF(cx + 16, cy - 2), QPointF(cx + 18, cy + 1))
            p.drawLine(QPointF(cx + 16, cy + 4), QPointF(cx + 18, cy + 1))

        p.end()


class PantherMicButton(QPushButton):
    """Microphone button — concentric sound rings + panther icon.

    Stitch-informed design:
      • Idle: minimalist mic capsule in orange outline
      • Hover: border brightens + subtle orange fill
      • Checked (recording): pulsating concentric rings radiate outward,
        mic transforms to open-mouth roar icon
      • Plays panther roar sound on activation (if available)
    """

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setFixedSize(44, 44)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to speak")

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
            pass  # multimedia module not available

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def nextCheckState(self):
        """Override to play roar on check."""
        super().nextCheckState()
        if self.isChecked():
            self._play_roar()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        is_recording = self.isChecked()

        # ── Outer glow halo (recording or hover) ──
        if is_recording or self._is_hovered:
            halo = QRadialGradient(QPointF(cx, cy), w / 2)
            alpha = 50 if is_recording else 30
            halo.setColorAt(0.5, QColor(255, 107, 53, alpha))
            halo.setColorAt(1.0, QColor(255, 107, 53, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(halo))
            p.drawEllipse(QRectF(0, 0, w, h))

        # ── Background circle ──
        if is_recording:
            pulse = 0.15 + 0.10 * math.sin(self._ring_phase * 2)
            bg_color = QColor(ORANGE)
            bg_color.setAlpha(int(255 * pulse))
        elif self._is_hovered:
            bg_color = QColor(ORANGE)
            bg_color.setAlpha(20)
        else:
            bg_color = QColor(0, 0, 0, 0)

        p.setBrush(QBrush(bg_color))
        border_color = ORANGE if (is_recording or self._is_hovered) else BORDER
        p.setPen(QPen(border_color, 1.5))
        p.drawEllipse(QRectF(2, 2, w - 4, h - 4))

        # ── Concentric rings (Stitch: gradient-faded expanding rings) ──
        if is_recording:
            for i in range(4):
                # Each ring fades as it expands — like a roar radiating out
                phase_offset = self._ring_phase + i * 1.2
                ring_progress = (phase_offset % 3.0) / 3.0  # 0→1 cycle
                ring_alpha = max(0, int(200 * (1 - ring_progress)))
                ring_color = QColor(ORANGE_LIGHT if i % 2 == 0 else ORANGE)
                ring_color.setAlpha(ring_alpha)
                p.setPen(QPen(ring_color, 1.5 - ring_progress * 0.8))
                p.setBrush(Qt.BrushStyle.NoBrush)
                radius = 10 + ring_progress * 14
                p.drawEllipse(QPointF(cx, cy), radius, radius)

        # ── Icon ──
        icon_color = AMBER if self._is_hovered else ORANGE
        p.setPen(QPen(icon_color, 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)

        if is_recording:
            # Open mouth / roar shape (Stitch: fangs visible)
            p.setPen(QPen(GOLD, 2.0))
            mouth = QPainterPath()
            mouth.moveTo(cx - 7, cy - 3)
            # Upper jaw with fangs
            mouth.lineTo(cx - 4, cy - 7)   # left fang tip
            mouth.lineTo(cx - 2, cy - 4)
            mouth.lineTo(cx + 2, cy - 4)
            mouth.lineTo(cx + 4, cy - 7)   # right fang tip
            mouth.lineTo(cx + 7, cy - 3)
            # Cheek
            mouth.lineTo(cx + 8, cy + 1)
            # Lower jaw
            mouth.lineTo(cx + 4, cy + 5)
            mouth.lineTo(cx, cy + 6)
            mouth.lineTo(cx - 4, cy + 5)
            mouth.lineTo(cx - 8, cy + 1)
            mouth.closeSubpath()
            p.drawPath(mouth)

            # Center tongue/throat line
            p.setPen(QPen(AMBER, 1.0))
            p.drawLine(QPointF(cx, cy - 2), QPointF(cx, cy + 3))
        else:
            # Minimalist mic capsule (Stitch: clean rounded rect + arc)
            mic = QPainterPath()
            mic.addRoundedRect(QRectF(cx - 4, cy - 10, 8, 13), 4, 4)
            p.drawPath(mic)
            # Stand
            p.drawLine(QPointF(cx, cy + 3), QPointF(cx, cy + 8))
            p.drawLine(QPointF(cx - 5, cy + 8), QPointF(cx + 5, cy + 8))
            # Pickup arc
            arc_rect = QRectF(cx - 7, cy - 1, 14, 10)
            p.drawArc(arc_rect, 0, 180 * 16)

        p.end()


class PantherAttachButton(QPushButton):
    """Attachment button — paperclip → panther eye morph.

    Stitch-informed design:
      • Default: muted warm gray paperclip icon (#8a8078)
      • Hover: paperclip brightens to orange
      • Active (has files): smooth morph to panther eye with:
        - Almond-shaped eye outline in orange (#FF6B35)
        - Amber iris gradient (#FFB347)
        - Gold vertical slit pupil (#FFD700)
        - Hover: pupil dilates smoothly
        - Tiny highlight dot for realism
    """

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setFixedSize(44, 44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Attach files (images, documents, videos)")

        self._has_files = False
        self._is_hovered = False
        self._pupil_dilation = 0.0  # 0 = closed slit, 1 = dilated

        # Pupil animation
        self._pupil_anim = QPropertyAnimation(self, b"pupilDilation")
        self._pupil_anim.setDuration(300)

    # Property for animation
    def _get_pupil_dilation(self) -> float:
        return self._pupil_dilation

    def _set_pupil_dilation(self, val: float):
        self._pupil_dilation = val
        self.update()

    pupilDilation = pyqtProperty(float, _get_pupil_dilation, _set_pupil_dilation)

    def set_has_files(self, has_files: bool):
        """Switch between paperclip and panther eye modes."""
        self._has_files = has_files
        self.update()

    def enterEvent(self, event):
        self._is_hovered = True
        if self._has_files:
            # Dilate pupil on hover
            self._pupil_anim.stop()
            self._pupil_anim.setStartValue(self._pupil_dilation)
            self._pupil_anim.setEndValue(0.8)
            self._pupil_anim.start()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        if self._has_files:
            # Contract pupil
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

        # ── Outer glow (when files attached or hover) ──
        if self._has_files or self._is_hovered:
            halo = QRadialGradient(QPointF(cx, cy), w / 2)
            alpha = 40 if self._has_files else 20
            halo.setColorAt(0.5, QColor(255, 107, 53, alpha))
            halo.setColorAt(1.0, QColor(255, 107, 53, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(halo))
            p.drawEllipse(QRectF(0, 0, w, h))

        # ── Background circle ──
        glow = 0.15 if self._is_hovered else (0.10 if self._has_files else 0.03)
        bg = QColor(ORANGE)
        bg.setAlpha(int(255 * glow))
        p.setBrush(QBrush(bg))
        border_color = ORANGE if (self._is_hovered or self._has_files) else BORDER
        p.setPen(QPen(border_color, 1.5))
        p.drawEllipse(QRectF(2, 2, w - 4, h - 4))

        if self._has_files:
            self._draw_panther_eye(p, cx, cy)
        else:
            self._draw_paperclip(p, cx, cy)

        p.end()

    def _draw_paperclip(self, p: QPainter, cx: float, cy: float):
        """Draw a minimalist paperclip icon (Stitch: muted gray, brightens on hover)."""
        # Stitch design: default is muted gray, hover brightens it
        color = AMBER if self._is_hovered else MUTED
        p.setPen(QPen(color, 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Clean paperclip shape — elongated loop
        clip = QPainterPath()
        clip.moveTo(cx + 2, cy + 9)
        clip.lineTo(cx + 2, cy - 5)
        clip.arcTo(QRectF(cx - 4, cy - 11, 12, 12), 0, 180)
        clip.lineTo(cx - 4, cy + 5)
        clip.arcTo(QRectF(cx - 7, cy + 1, 6, 8), 0, -180)
        clip.lineTo(cx - 4, cy - 3)
        clip.arcTo(QRectF(cx - 4, cy - 7, 8, 8), 180, -180)
        p.drawPath(clip)

        # Add tiny "+" indicator
        if self._is_hovered:
            p.setPen(QPen(GOLD, 1.5))
            p.drawLine(QPointF(cx + 10, cy - 6), QPointF(cx + 10, cy - 2))
            p.drawLine(QPointF(cx + 8, cy - 4), QPointF(cx + 12, cy - 4))

    def _draw_panther_eye(self, p: QPainter, cx: float, cy: float):
        """Draw panther eye with vertical slit pupil (Stitch: almond + iris gradient)."""
        # ── Outer eye shape (almond) ──
        eye_pen_color = AMBER if self._is_hovered else ORANGE
        p.setPen(QPen(eye_pen_color, 2.0))

        # Iris glow gradient (Stitch: warm amber center → orange edge)
        iris_gradient = QRadialGradient(QPointF(cx, cy), 11)
        iris_gradient.setColorAt(0, QColor(255, 215, 0, 140))   # gold center
        iris_gradient.setColorAt(0.4, QColor(255, 179, 71, 120))  # amber
        iris_gradient.setColorAt(0.8, QColor(255, 107, 53, 80))   # orange
        iris_gradient.setColorAt(1, QColor(255, 107, 53, 30))     # fade
        p.setBrush(QBrush(iris_gradient))

        # Smooth almond eye using cubic bezier
        eye = QPainterPath()
        eye.moveTo(cx - 14, cy)
        eye.cubicTo(
            QPointF(cx - 7, cy - 10),
            QPointF(cx + 7, cy - 10),
            QPointF(cx + 14, cy)
        )
        eye.cubicTo(
            QPointF(cx + 7, cy + 10),
            QPointF(cx - 7, cy + 10),
            QPointF(cx - 14, cy)
        )
        p.drawPath(eye)

        # ── Vertical slit pupil (dilates on hover via animation) ──
        pupil_width = 1.5 + self._pupil_dilation * 5.5
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(DARK))
        pupil = QPainterPath()
        pupil.addEllipse(QPointF(cx, cy), pupil_width, 7.5)
        p.drawPath(pupil)

        # Inner pupil slit highlight
        inner_slit = QColor(DARK)
        inner_slit.setAlpha(200)
        p.setBrush(QBrush(inner_slit))
        p.drawEllipse(QPointF(cx, cy), max(1.0, pupil_width * 0.5), 6)

        # ── Catchlight — Stitch: tiny white reflection dot ──
        p.setBrush(QBrush(QColor(255, 255, 255, 200)))
        p.drawEllipse(QPointF(cx - 3, cy - 3), 1.8, 1.8)
        # Secondary smaller catchlight
        p.setBrush(QBrush(QColor(255, 255, 255, 100)))
        p.drawEllipse(QPointF(cx + 2, cy + 2), 1.0, 1.0)

        # ── Corner accents (inner corner of eye — tear duct detail) ──
        if self._is_hovered:
            p.setPen(QPen(GOLD, 1.2))
            p.drawLine(QPointF(cx - 13, cy), QPointF(cx - 16, cy))
            p.drawLine(QPointF(cx + 13, cy), QPointF(cx + 16, cy))
