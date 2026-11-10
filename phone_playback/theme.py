"""Read the Windows colour scheme and resolve the app's accent preference."""

import ctypes as C
from ctypes import wintypes as W
from PySide6.QtGui import QColor, QImage
from PySide6.QtCore import QUrl, Qt

FALLBACK = "#b7ebbe"


def windows_accent():
    try:
        get_colour = C.WinDLL("dwmapi").DwmGetColorizationColor
        get_colour.argtypes = [C.POINTER(W.DWORD), C.POINTER(W.BOOL)]
        get_colour.restype = C.c_long
        colour, opaque = W.DWORD(), W.BOOL()
        if get_colour(C.byref(colour), C.byref(opaque)) == 0:
            # DWM returns AARRGGBB; widgets use the opaque RGB component.
            return f"#{colour.value & 0xFFFFFF:06x}"
    except (OSError, AttributeError):
        pass
    return None


def album_accent(url):
    """Extract a restrained accent from local art; never fetch an image URL."""
    location = QUrl(url)
    if not location.isLocalFile():
        return None
    image = QImage(location.toLocalFile())
    if image.isNull():
        return None
    image = image.scaled(
        32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    bins = {}
    for y in range(image.height()):
        for x in range(image.width()):
            c = image.pixelColor(x, y)
            h, s, v, _ = c.getHsvF()
            if c.alphaF() < 0.5 or s < 0.12 or v < 0.16:
                continue
            bucket = int(h * 24) % 24
            weight = s * v
            total, hs, ss, vs = bins.get(bucket, (0, 0, 0, 0))
            bins[bucket] = (total + weight, hs + h * weight, ss + s * weight, vs + v * weight)
    if not bins:
        return None
    total, h, s, v = max(bins.values(), key=lambda b: b[0])
    return QColor.fromHsvF(
        h / total, max(0.28, min(0.65, s / total)), max(0.72, min(0.92, v / total))
    ).name()


def accent_for(settings, album_colour=None):
    if settings.get("theme_source") == "album" and album_colour:
        return album_colour
    if settings.get("theme_source") == "custom":
        colour = QColor(settings.get("accent_colour", ""))
        if colour.isValid():
            return colour.name()
    return windows_accent() or FALLBACK


def foreground_for(accent):
    def luminance(value):
        colour = QColor(value)
        channels = [colour.redF(), colour.greenF(), colour.blueF()]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
        return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    background = luminance(accent)
    choices = ("#142019", "#f5f5f7")
    return max(
        choices,
        key=lambda c: (max(background, luminance(c)) + 0.05)
        / (min(background, luminance(c)) + 0.05),
    )


def volume_symbol(volume):
    if volume <= 0:
        return "volume-muted"
    if volume <= 33:
        return "volume-low"
    if volume <= 66:
        return "volume-medium"
    return "volume-high"
