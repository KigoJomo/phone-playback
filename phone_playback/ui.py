"""Taskbar-edge now-playing pill, native tray and transient hover controls."""

import sys, time, json, ctypes as C, threading, os
from ctypes import wintypes as W
from pathlib import Path

BASE = Path(__file__).resolve().parent
# Dependencies are installed through pyproject.toml.
from PySide6.QtCore import Qt, QTimer, QRectF, QRect, QPoint, QUrl, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QPixmap,
    QIcon,
    QCursor,
    QLinearGradient,
    QRadialGradient,
    QActionGroup,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QSlider,
    QSystemTrayIcon,
    QMenu,
    QPushButton,
    QColorDialog,
)
from . import core
from .config import save as save_config
from .theme import accent_for, foreground_for, volume_symbol

BG = "#171b22"
FG = "#f5f5f7"
MUTED = "#9ca5b3"
ACCENT = "#b7ebbe"
PREVIEW = "--preview" in sys.argv
PREVIEW_DIR = Path(os.environ.get("PHONE_PLAYBACK_PREVIEW_DIR", str(BASE.parent / "docs")))


def font(size, weight=QFont.Weight.Normal):
    f = QFont("Segoe UI", size)
    f.setWeight(weight)
    return f


def rounded(p, rect, radius, color):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(rect), radius, radius)


def symbol(p, name, rect, color=FG):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(rect.center())
    p.scale(rect.width() / 24, rect.height() / 24)
    p.setPen(
        QPen(
            QColor(color),
            1.8,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    p.setBrush(QColor(color))
    if name == "pause":
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(-6, -7, 4, 14), 1, 1)
        p.drawRoundedRect(QRectF(2, -7, 4, 14), 1, 1)
    elif name == "play":
        path = QPainterPath()
        path.moveTo(-4, -8)
        path.lineTo(8, 0)
        path.lineTo(-4, 8)
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)
    elif name in ("next", "previous"):
        if name == "previous":
            p.scale(-1, 1)
        path = QPainterPath()
        path.moveTo(-6, -6)
        path.lineTo(3, 0)
        path.lineTo(-6, 6)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(6, -6, 6, 6)
    elif name.startswith("volume"):
        path = QPainterPath()
        path.moveTo(-8, -3)
        path.lineTo(-4, -3)
        path.lineTo(1, -7)
        path.lineTo(1, 7)
        path.lineTo(-4, 3)
        path.lineTo(-8, 3)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if name == "volume-muted":
            p.drawLine(5, -3, 10, 3)
            p.drawLine(5, 3, 10, -3)
        elif name in ("volume-medium", "volume-high"):
            p.drawArc(QRectF(-1, -4, 8, 8), -60 * 16, 120 * 16)
            if name == "volume-high":
                p.drawArc(QRectF(-2, -7, 14, 14), -60 * 16, 120 * 16)
    elif name in ("back15", "ahead15"):
        if name == "back15":
            p.scale(-1, 1)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(-8, -8, 16, 16), 70 * 16, 270 * 16)
        p.drawLine(2, -9, 4, -5)
        p.drawLine(4, -5, -1, -4)
        if name == "back15":
            p.scale(-1, 1)
        p.setFont(font(6, QFont.Weight.DemiBold))
        p.drawText(QRectF(-6, -4, 12, 10), Qt.AlignmentFlag.AlignCenter, "15")
    elif name == "more":
        p.setPen(Qt.PenStyle.NoPen)
        for x in (-6, 0, 6):
            p.drawEllipse(QPoint(x, 0), 1.4, 1.4)
    p.restore()


class IconButton(QWidget):
    def __init__(self, name, callback, size=36, primary=False, tip=""):
        super().__init__()
        self.symbol = name
        self.callback = callback
        self.primary = primary
        self.hovered = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tip)
        self.setAccessibleName(tip)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def enterEvent(self, e):
        self.hovered = True
        self.update()

    def leaveEvent(self, e):
        self.hovered = False
        self.update()

    def mouseReleaseEvent(self, e):
        if (
            self.isEnabled()
            and e.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(e.position().toPoint())
        ):
            self.callback()

    def keyPressEvent(self, e):
        if self.isEnabled() and e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return):
            self.callback()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.32)
        if self.primary:
            rounded(
                p,
                self.rect().adjusted(1, 1, -1, -1),
                self.width() / 2,
                QColor(ACCENT).lighter(112).name() if self.hovered else ACCENT,
            )
        elif self.hovered or self.hasFocus():
            rounded(p, self.rect(), 12, "#2b323d")
        size = 24 if self.primary else 21
        symbol(
            p,
            self.symbol,
            QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size),
            foreground_for(ACCENT) if self.primary else FG,
        )


class Marquee(QWidget):
    def __init__(self, size=10, weight=QFont.Weight.Normal):
        super().__init__()
        self.text = ""
        self.offset = 0
        self.started = time.monotonic()
        self.setFont(font(size, weight))
        self.setMinimumWidth(20)
        self.setFixedHeight(QFontMetrics(self.font()).height() + 4)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(33)

    def setText(self, text):
        if self.text != text:
            self.text = text
            self.offset = 0
            self.started = time.monotonic()
            self.setAccessibleName(text)
            self.update()

    def animate(self):
        width = QFontMetrics(self.font()).horizontalAdvance(self.text)
        if width > self.width() and self.isVisible():
            self.offset = max(0, time.monotonic() - self.started - 1.5) * 24 % (width + 55)
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setFont(self.font())
        p.setPen(QColor(FG))
        p.setClipRect(self.rect())
        fm = QFontMetrics(self.font())
        y = (self.height() - fm.height()) / 2 + fm.ascent()
        width = fm.horizontalAdvance(self.text)
        p.drawText(QPoint(int(-self.offset), int(y)), self.text)
        if width > self.width():
            p.drawText(QPoint(int(width + 55 - self.offset), int(y)), self.text)
        for left in (False, True):
            if left and self.offset < 1:
                continue
            x = 0 if left else self.width() - 12
            fade = QLinearGradient(x, 0, x + 12, 0)
            clear = QColor(23, 27, 34, 0)
            fade.setColorAt(0, QColor(BG) if left else clear)
            fade.setColorAt(1, clear if left else QColor(BG))
            p.fillRect(QRectF(x, 0, 12, self.height()), fade)


class Artwork(QWidget):
    def __init__(self, size):
        super().__init__()
        self.setFixedSize(size, size)
        self.pixmap = QPixmap()
        self.path = None

    def setPath(self, url):
        path = QUrl(url).toLocalFile() if url else ""
        if path != self.path:
            self.path = path
            self.pixmap = QPixmap(path) if path and Path(path).is_file() else QPixmap()
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        radius = min(16, self.width() / 4)
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        p.setClipPath(path)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor(ACCENT).darker(280))
        gradient.setColorAt(1, QColor("#292d42"))
        p.fillRect(self.rect(), gradient)
        if not self.pixmap.isNull():
            scaled = self.pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(
                (self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled
            )
        else:
            p.setPen(
                QPen(
                    QColor(ACCENT),
                    max(2, self.width() / 22),
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            for fraction, height in ((0.34, 0.16), (0.5, 0.34), (0.66, 0.24)):
                x = round(self.width() * fraction)
                p.drawLine(
                    x,
                    round(self.height() * (0.5 - height / 2)),
                    x,
                    round(self.height() * (0.5 + height / 2)),
                )


def label(text, size=10, color=MUTED, weight=QFont.Weight.Normal):
    x = QLabel(text)
    x.setFont(font(size, weight))
    x.setStyleSheet("color:" + color + "; background:transparent;")
    return x


class Surface(QWidget):
    def __init__(self, radius):
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rounded(p, self.rect().adjusted(1, 1, -1, -1), self.radius, BG)
        gradient = QRadialGradient(self.width() * 0.12, 0, self.width() * 0.9)
        glow = QColor(ACCENT)
        glow.setAlpha(25)
        gradient.setColorAt(0, glow)
        gradient.setColorAt(1, QColor(23, 27, 34, 0))
        p.setBrush(gradient)
        p.setPen(QPen(QColor("#343c45"), 1))
        p.drawRoundedRect(QRectF(self.rect().adjusted(1, 1, -1, -1)), self.radius, self.radius)


class Pill(Surface):
    def __init__(self, controller):
        super().__init__(15)
        self.controller = controller
        self.setWindowTitle("Phone Playback · taskbar")
        self.setFixedSize(260, 34)
        self.dragging = False
        row = QHBoxLayout(self)
        row.setContentsMargins(5, 4, 4, 4)
        row.setSpacing(8)
        self.art = Artwork(26)
        row.addWidget(self.art)
        self.title = Marquee(9, QFont.Weight.DemiBold)
        row.addWidget(self.title, 1)
        self.play = IconButton(
            "play",
            lambda: controller.command("action", "PlayPause"),
            26,
            tip="Play / pause · Ctrl+Alt+Space",
        )
        row.addWidget(self.play)
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.art.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def enterEvent(self, e):
        self.controller.hover_since = time.monotonic()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.origin = e.globalPosition().toPoint()
            self.start_x = self.x()

    def mouseMoveEvent(self, e):
        if self.dragging:
            self.move(self.start_x + e.globalPosition().toPoint().x() - self.origin.x(), self.y())

    def mouseReleaseEvent(self, e):
        if self.dragging:
            self.dragging = False
            if abs(e.globalPosition().toPoint().x() - self.origin.x()) < 4:
                self.controller.open_panel()
            else:
                self.controller.settings["dock_x"] = self.x()
                self.controller.save_settings()

    def contextMenuEvent(self, e):
        self.controller.menu.exec(e.globalPos())

    def wheelEvent(self, e):
        self.controller.command("volume", 5 if e.angleDelta().y() > 0 else -5)


SLIDER_STYLE = ""


class Slider(QSlider):
    def __init__(self, orientation):
        super().__init__(orientation)
        self.setFixedHeight(18)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x = 5 + (self.width() - 10) * (self.value() - self.minimum()) / max(
            1, self.maximum() - self.minimum()
        )
        rounded(p, QRectF(5, 7, self.width() - 10, 4), 2, "#343c46")
        rounded(p, QRectF(5, 7, max(0, x - 5), 4), 2, ACCENT if self.isEnabled() else "#59616c")
        if self.isEnabled():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(ACCENT).lighter(170))
            p.drawEllipse(QPoint(round(x), 9), 5, 5)

    def value_at(self, e):
        fraction = max(0, min(1, (e.position().x() - 5) / max(1, self.width() - 10)))
        self.setValue(round(self.minimum() + fraction * (self.maximum() - self.minimum())))

    def mousePressEvent(self, e):
        if self.isEnabled() and e.button() == Qt.MouseButton.LeftButton:
            self.setSliderDown(True)
            self.value_at(e)

    def mouseMoveEvent(self, e):
        if self.isSliderDown():
            self.value_at(e)

    def mouseReleaseEvent(self, e):
        if self.isSliderDown():
            self.value_at(e)
            self.setSliderDown(False)

    def wheelEvent(self, e):
        super().wheelEvent(e)
        self.sliderReleased.emit()

    def keyPressEvent(self, e):
        super().keyPressEvent(e)
        self.sliderReleased.emit()


class Panel(Surface):
    def __init__(self, controller):
        super().__init__(22)
        self.controller = controller
        self.setWindowTitle("Phone Playback · controls")
        self.setFixedSize(360, 340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(23, 19, 23, 18)
        layout.setSpacing(0)
        header = QHBoxLayout()
        self.source = QPushButton("CHOOSE A PHONE")
        self.source.setFont(font(8, QFont.Weight.DemiBold))
        self.source.setCursor(Qt.CursorShape.PointingHandCursor)
        self.source.setStyleSheet(
            "QPushButton {color:#aeb9b3; background:transparent; border:0; text-align:left; padding:4px 0;} QPushButton:hover {color:#e8f6eb;}"
        )
        self.source.clicked.connect(controller.choose_player)
        header.addWidget(self.source)
        header.addStretch()
        header.addWidget(
            IconButton("more", lambda: controller.menu.exec(QCursor.pos()), 24, tip="Options")
        )
        layout.addLayout(header)
        layout.addSpacing(18)
        meta = QHBoxLayout()
        meta.setSpacing(16)
        self.art = Artwork(76)
        meta.addWidget(self.art)
        text = QVBoxLayout()
        text.setSpacing(5)
        text.addStretch()
        self.title = Marquee(15, QFont.Weight.DemiBold)
        text.addWidget(self.title)
        self.artist = label("", 10)
        text.addWidget(self.artist)
        text.addStretch()
        meta.addLayout(text, 1)
        layout.addLayout(meta)
        layout.addSpacing(20)
        self.seek = Slider(Qt.Orientation.Horizontal)
        self.seek.setStyleSheet(SLIDER_STYLE)
        self.seek.setAccessibleName("Track position")
        self.seek.setCursor(Qt.CursorShape.PointingHandCursor)
        self.seek.sliderReleased.connect(lambda: controller.command("position", self.seek.value()))
        layout.addWidget(self.seek)
        times = QHBoxLayout()
        self.elapsed = label("0:00", 8)
        self.duration = label("0:00", 8)
        times.addWidget(self.elapsed)
        times.addStretch()
        times.addWidget(self.duration)
        layout.addLayout(times)
        layout.addSpacing(9)
        transport = QHBoxLayout()
        transport.setSpacing(8)
        self.controls = []
        for name, action, value, size, tip in [
            ("back15", "seek", -15, 32, "Back 15 seconds"),
            ("previous", "action", "Previous", 38, "Previous · Ctrl+Alt+Left"),
            ("play", "action", "PlayPause", 54, "Play / pause · Ctrl+Alt+Space"),
            ("next", "action", "Next", 38, "Next · Ctrl+Alt+Right"),
            ("ahead15", "seek", 15, 32, "Forward 15 seconds"),
        ]:
            button = IconButton(
                name, lambda a=action, v=value: controller.command(a, v), size, name == "play", tip
            )
            transport.addWidget(button, 0, Qt.AlignmentFlag.AlignCenter)
            self.controls.append(button)
        self.play = self.controls[2]
        layout.addLayout(transport)
        layout.addSpacing(18)
        volume = QHBoxLayout()
        volume.setSpacing(10)
        self.volume_icon = IconButton("volume-muted", lambda: None, 22, tip="Phone volume")
        self.volume_icon.setCursor(Qt.CursorShape.ArrowCursor)
        self.volume_icon.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        volume.addWidget(self.volume_icon)
        self.volume = Slider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setStyleSheet(SLIDER_STYLE)
        self.volume.setAccessibleName("Phone volume")
        self.volume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.volume.sliderReleased.connect(
            lambda: controller.command("set-volume", self.volume.value())
        )
        volume.addWidget(self.volume, 1)
        self.volume_text = label("0%", 8)
        self.volume_text.setFixedWidth(30)
        self.volume_text.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        volume.addWidget(self.volume_text)
        layout.addLayout(volume)
        layout.addStretch(1)
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(label("CTRL + ALT + SPACE", 7, "#707d88"))
        layout.addLayout(footer)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.hide()

    def wheelEvent(self, e):
        self.controller.command("volume", 5 if e.angleDelta().y() > 0 else -5)


def tray_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rounded(p, QRectF(2, 2, 60, 60), 18, ACCENT)
    p.setPen(
        QPen(QColor(foreground_for(ACCENT)), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    )
    for x, h in [(20, 12), (32, 28), (44, 19)]:
        p.drawLine(x, 32 - h // 2, x, 32 + h // 2)
    p.end()
    return QIcon(pixmap)


class Taskbar:
    def __init__(self):
        self.u = C.WinDLL("user32")
        self.u.FindWindowW.argtypes = [W.LPCWSTR, W.LPCWSTR]
        self.u.FindWindowW.restype = W.HWND
        self.u.FindWindowExW.argtypes = [W.HWND, W.HWND, W.LPCWSTR, W.LPCWSTR]
        self.u.FindWindowExW.restype = W.HWND
        self.u.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
        self.u.GetForegroundWindow.restype = W.HWND

    def rect(self, hwnd):
        r = W.RECT()
        if not hwnd or not self.u.GetWindowRect(hwnd, C.byref(r)):
            return QRect()
        d = QApplication.primaryScreen().devicePixelRatio()
        return QRect(
            round(r.left / d),
            round(r.top / d),
            round((r.right - r.left) / d),
            round((r.bottom - r.top) / d),
        )

    def geometry(self):
        hwnd = self.u.FindWindowW("Shell_TrayWnd", None)
        return self.rect(hwnd), self.rect(self.u.FindWindowExW(hwnd, None, "TrayNotifyWnd", None))

    def fullscreen(self, ours):
        hwnd = self.u.GetForegroundWindow()
        if int(hwnd or 0) in ours:
            return False
        rect = self.rect(hwnd)
        return not rect.isNull() and rect.contains(QApplication.primaryScreen().geometry())


class Controller:
    def __init__(self):
        global ACCENT
        self.settings = core.CONFIG
        ACCENT = accent_for(self.settings)
        self.state = {}
        self.connected = False
        self.last_pos = 0
        self.last_pos_time = time.monotonic()
        self.hover_since = None
        self.leave_since = None
        self.opened_at = 0
        self.menu_open = False
        self.last_position_check = 0
        self.taskbar = Taskbar()
        self.pill = Pill(self)
        self.panel = Panel(self)
        self.menu = QMenu()
        self.menu.setStyleSheet(
            "QMenu {background:#20262f; color:#e9edf1; border:1px solid #3c4550; padding:6px;} QMenu::item {padding:8px 18px;} QMenu::item:selected {background:#34443a;}"
        )
        self.menu.aboutToShow.connect(lambda: setattr(self, "menu_open", True))
        self.menu.aboutToHide.connect(lambda: setattr(self, "menu_open", False))
        self.phone_menu = self.menu.addMenu("Choose phone")
        self.phone_menu.addAction("Searching for paired phones…").setEnabled(False)
        self.menu.addAction("Open controls", self.open_panel)
        self.dock_action = self.menu.addAction("Show song title on taskbar")
        self.dock_action.setCheckable(True)
        self.dock_action.setChecked(self.settings.get("show_dock", True))
        self.dock_action.toggled.connect(self.toggle_dock)
        theme_menu = self.menu.addMenu("Theme colour")
        self.theme_group = QActionGroup(self.menu)
        self.windows_theme = theme_menu.addAction("Follow Windows accent")
        self.custom_theme = theme_menu.addAction("Choose custom colour…")
        for action in (self.windows_theme, self.custom_theme):
            action.setCheckable(True)
            self.theme_group.addAction(action)
        self.windows_theme.triggered.connect(self.follow_windows_theme)
        self.custom_theme.triggered.connect(self.choose_custom_colour)
        self.menu.addSeparator()
        self.menu.addAction("Quit Phone Playback", self.quit)
        self.tray = QSystemTrayIcon(tray_icon())
        self.tray.setToolTip("Phone Playback · connecting")
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.tray_activated)
        self.apply_theme(force=True)
        if not PREVIEW:
            self.tray.show()
        self.pill.title.setText("Connecting to phone…")
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll)
        self.timer.start(80)
        if not PREVIEW:
            threading.Thread(target=core.media_worker, daemon=True).start()
            threading.Thread(target=core.hotkey_worker, daemon=True).start()
        self.position_dock()
        if not PREVIEW:
            QTimer.singleShot(2200, self.report_startup)

    def report_startup(self):
        print(
            json.dumps(
                {
                    "tray_visible": self.tray.isVisible(),
                    "tray_geometry": self.tray.geometry().getRect(),
                    "pill_visible": self.pill.isVisible(),
                    "pill_geometry": self.pill.geometry().getRect(),
                    "panel_visible": self.panel.isVisible(),
                    "connected": self.connected,
                    "player": self.state.get("player"),
                    "layout_fits": self.panel.layout().minimumSize().height()
                    <= self.panel.height(),
                }
            ),
            flush=True,
        )

    def save_settings(self):
        save_config(self.settings)

    def apply_theme(self, force=False):
        global ACCENT
        colour = accent_for(self.settings)
        custom = self.settings.get("theme_source") == "custom"
        self.windows_theme.setChecked(not custom)
        self.custom_theme.setChecked(custom)
        if not force and colour == ACCENT:
            return
        ACCENT = colour
        selected = QColor(ACCENT).darker(280).name()
        self.menu.setStyleSheet(
            "QMenu {background:#20262f; color:#e9edf1; border:1px solid #3c4550; padding:6px;} "
            "QMenu::item {padding:8px 18px;} QMenu::item:selected {background:" + selected + ";}"
        )
        icon = tray_icon()
        self.tray.setIcon(icon)
        QApplication.setWindowIcon(icon)
        for surface in (self.pill, self.panel):
            surface.update()
            for widget in surface.findChildren(QWidget):
                widget.update()

    def follow_windows_theme(self):
        self.settings["theme_source"] = "windows"
        self.save_settings()
        self.apply_theme(force=True)

    def choose_custom_colour(self):
        self.menu_open = True
        try:
            colour = QColorDialog.getColor(QColor(ACCENT), self.panel, "Accent colour")
            if colour.isValid():
                self.settings.update(theme_source="custom", accent_colour=colour.name())
                self.save_settings()
            self.apply_theme(force=True)
        finally:
            self.menu_open = False
            self.opened_at = time.monotonic()

    def toggle_dock(self, on):
        self.settings["show_dock"] = on
        self.save_settings()
        self.position_dock()

    def tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.open_panel()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self.command("action", "PlayPause")

    def command(self, action, value):
        if self.connected:
            core.commands.put((action, value))

    def update_devices(self, devices):
        self.phone_menu.clear()
        for device in devices:
            action = self.phone_menu.addAction(
                device["name"] + (" (offline)" if not device["reachable"] else "")
            )
            action.setCheckable(True)
            action.setChecked(device["id"] == self.settings.get("device_id"))
            action.triggered.connect(
                lambda checked=False, d=device: core.commands.put(("device", d))
            )
        if not devices:
            self.phone_menu.addAction("Pair an Android phone in KDE Connect").setEnabled(False)

    def choose_player(self):
        menu = QMenu(self.panel)
        menu.setStyleSheet(self.menu.styleSheet())
        self.menu_open = True
        for name in self.state.get("playerList", []):
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(name == self.state.get("player"))
            action.triggered.connect(lambda checked=False, n=name: self.command("player", n))
        if menu.isEmpty():
            menu.addAction("Start audio on your phone").setEnabled(False)
        menu.exec(self.panel.source.mapToGlobal(QPoint(0, self.panel.source.height())))
        self.menu_open = False
        self.opened_at = time.monotonic()

    def position_dock(self):
        bar, tray = self.taskbar.geometry()
        screen = QApplication.primaryScreen().geometry()
        self.bar = bar
        visible = (
            bar.width() > bar.height() > 0
            and screen.intersects(bar)
            and self.settings.get("show_dock", True)
        )
        if not PREVIEW and self.taskbar.fullscreen(
            {int(self.pill.winId()), int(self.panel.winId())}
        ):
            visible = False
        if visible:
            default_x = (
                (tray.left() if not tray.isNull() else bar.right() - 200) - self.pill.width() - 10
            )
            x = max(
                bar.left() + 10,
                min(bar.right() - self.pill.width() - 10, self.settings.get("dock_x", default_x)),
            )
            y = bar.center().y() - self.pill.height() // 2
            if not self.pill.dragging:
                self.pill.move(x, y)
            self.pill.show()
            self.pill.raise_()
        else:
            self.pill.hide()

    def open_panel(self):
        screen = QApplication.primaryScreen().geometry()
        anchor = self.pill.geometry() if self.pill.isVisible() else self.tray.geometry()
        if anchor.isNull():
            anchor = QRect(screen.right() - 365, screen.bottom() - 45, 260, 34)
        x = max(
            screen.left() + 8,
            min(screen.right() - self.panel.width() - 8, anchor.right() - self.panel.width()),
        )
        y = anchor.top() - self.panel.height() - 10
        if y < screen.top() + 8:
            y = anchor.bottom() + 10
        y = max(screen.top() + 8, min(screen.bottom() - self.panel.height() - 8, y))
        self.panel.move(x, y)
        self.panel.show()
        self.panel.raise_()
        self.opened_at = time.monotonic()
        self.leave_since = None
        self.fade = QPropertyAnimation(self.panel, b"windowOpacity")
        self.fade.setDuration(140)
        self.fade.setStartValue(0.1)
        self.fade.setEndValue(1.0)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade.start()

    def apply_state(self, value):
        now = time.monotonic()
        old = self.state
        self.state = value
        self.connected = True
        if (
            value.get("position") != old.get("position")
            or value.get("title") != old.get("title")
            or value.get("isPlaying") != old.get("isPlaying")
        ):
            self.last_pos = value.get("position", 0)
            self.last_pos_time = now
        title = value.get("title") or "Start audio on your phone"
        artist = value.get("artist") or "Ready when you are"
        self.pill.title.setText(title + "  ·  " + artist if value.get("artist") else title)
        self.panel.title.setText(title)
        self.panel.artist.setText(
            QFontMetrics(self.panel.artist.font()).elidedText(
                artist, Qt.TextElideMode.ElideRight, 220
            )
        )
        self.panel.source.setText(
            (value.get("device_name", "Phone") + "  /  " + value.get("player", "Player")).upper()
        )
        self.panel.source.setToolTip("Choose phone player")
        for art in (self.pill.art, self.panel.art):
            art.setPath(value.get("localAlbumArtUrl", ""))
        name = "pause" if value.get("isPlaying") else "play"
        self.pill.play.symbol = name
        self.pill.play.update()
        self.panel.play.symbol = name
        self.panel.play.update()
        available = bool(value.get("playerList"))
        self.pill.play.setEnabled(available)
        for button in self.panel.controls:
            button.setEnabled(available)
        for button in (self.panel.controls[0], self.panel.controls[-1]):
            button.setEnabled(available and bool(value.get("canSeek")))
        self.panel.seek.setEnabled(available and bool(value.get("canSeek")))
        self.panel.volume.setEnabled(available)
        self.panel.volume_icon.setEnabled(available)
        self.panel.seek.setRange(0, max(1, value.get("length", 0)))
        if not self.panel.volume.isSliderDown():
            self.panel.volume.setValue(value.get("volume", 0))
        self.panel.volume_text.setText(str(value.get("volume", 0)) + "%")
        self.panel.volume_icon.symbol = volume_symbol(value.get("volume", 0))
        self.panel.volume_icon.setToolTip(f"Phone volume: {value.get('volume', 0)}%")
        self.panel.volume_icon.update()
        self.tray.setToolTip(
            (
                title
                + "\n"
                + artist
                + "\n"
                + value.get("player", "")
                + " · "
                + value.get("device_name", "Phone")
            )[:120]
        )

    def offline(self, message):
        self.connected = False
        self.pill.title.setText("Phone disconnected")
        self.pill.play.setEnabled(False)
        self.panel.title.setText("Connect your phone")
        self.panel.artist.setText(message[:40])
        self.tray.setToolTip("Phone Playback · disconnected")
        for button in self.panel.controls:
            button.setEnabled(False)
        self.panel.seek.setEnabled(False)
        self.panel.volume.setEnabled(False)
        self.panel.volume_icon.setEnabled(False)
        self.panel.volume_icon.setToolTip("Phone volume unavailable")

    def poll(self):
        now = time.monotonic()
        if not PREVIEW and core.kernel32.WaitForSingleObject(core.show_event, 0) == 0:
            self.open_panel()
        while True:
            try:
                kind, value = core.updates.get_nowait()
            except core.queue.Empty:
                break
            if kind == "state":
                self.apply_state(value)
            elif kind == "error":
                self.offline(value)
            elif kind == "devices":
                self.update_devices(value)
            elif kind == "show":
                if self.panel.isVisible():
                    self.panel.hide()
                else:
                    self.open_panel()
            elif kind == "hotkeys" and value:
                self.menu.addAction("Shortcut unavailable: " + ", ".join(value)).setEnabled(False)
        if now - self.last_position_check > 1:
            self.apply_theme()
            self.position_dock()
            self.last_position_check = now
        pos = QCursor.pos()
        over_pill = self.pill.isVisible() and self.pill.geometry().contains(pos)
        tray_rect = self.tray.geometry()
        over_tray = not tray_rect.isNull() and tray_rect.contains(pos)
        if (over_pill or over_tray) and not self.panel.isVisible():
            if self.hover_since is None:
                self.hover_since = now
            elif now - self.hover_since > 0.25 and not self.pill.dragging:
                self.open_panel()
        else:
            self.hover_since = None
        if self.panel.isVisible():
            within = (
                self.panel.geometry().adjusted(-8, -8, 8, 12).contains(pos)
                or over_pill
                or over_tray
            )
            if within or self.menu_open or now - self.opened_at < 1.2:
                self.leave_since = None
            elif self.leave_since is None:
                self.leave_since = now
            elif now - self.leave_since > 0.5:
                self.panel.hide()
                self.leave_since = None
        if self.connected:
            position = (
                self.last_pos + (now - self.last_pos_time) * 1000
                if self.state.get("isPlaying")
                else self.last_pos
            )
            position = min(self.state.get("length", 0), position)
            if not self.panel.seek.isSliderDown():
                self.panel.seek.setValue(int(position))
            self.panel.elapsed.setText(stamp(position))
            self.panel.duration.setText(stamp(self.state.get("length", 0)))

    def quit(self):
        core.stop.set()
        self.tray.hide()
        QApplication.quit()


def stamp(ms):
    seconds = max(0, int(ms or 0) // 1000)
    return f"{seconds // 60}:{seconds % 60:02d}"


def main():
    if not PREVIEW and not core.single_instance():
        return
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    for filename in ("segoeui.ttf", "seguisb.ttf", "segoeuib.ttf"):
        QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / filename))
    app.setFont(font(10))
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Phone Playback")
    app.setWindowIcon(tray_icon())
    controller = Controller()
    if PREVIEW:
        controller.apply_state(
            {
                "title": "A little closer to the music",
                "artist": "Your phone. Your soundtrack.",
                "device_name": "Phone",
                "player": "Music",
                "playerList": ["Music"],
                "isPlaying": True,
                "volume": 40,
                "position": 85000,
                "length": 220901,
                "canSeek": True,
            }
        )
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        controller.panel.show()
        app.processEvents()
        controller.poll()
        app.processEvents()
        controller.panel.grab().save(str(PREVIEW_DIR / "preview-panel.png"))
        controller.pill.grab().save(str(PREVIEW_DIR / "preview-pill.png"))
        tray_icon().pixmap(64, 64).save(str(PREVIEW_DIR / "phone-playback.ico"), "ICO")
        print(
            json.dumps(
                {
                    "panel_size": [controller.panel.width(), controller.panel.height()],
                    "pill_size": [controller.pill.width(), controller.pill.height()],
                    "connected": controller.connected,
                    "panel_layout_fits": controller.panel.layout().minimumSize().height()
                    <= controller.panel.height(),
                    "title": controller.state.get("title"),
                }
            )
        )
        controller.quit()
        return
    app.aboutToQuit.connect(core.stop.set)
    app.exec()


if __name__ == "__main__":
    main()
