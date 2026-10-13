"""Small Qt helpers shared by the renderer, the GUI and the overlay."""

from __future__ import annotations

import os
import sys

from PIL import Image

_app = None


def ensure_qt_app():
    """Make sure a Q(Gui)Application exists (needed for painting and SVG)."""
    global _app
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance()
    if app is None:
        if not os.environ.get("QT_QPA_PLATFORM") and not _has_display():
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
        _app = QGuiApplication(sys.argv[:1])
        app = _app
    return app


def _has_display() -> bool:
    if sys.platform in ("win32", "darwin"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def qimage_to_pil(qimg) -> Image.Image:
    from PySide6.QtGui import QImage
    img = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    data = bytes(img.constBits())[: img.bytesPerLine() * h]
    if img.bytesPerLine() != w * 4:
        rows = [data[y * img.bytesPerLine(): y * img.bytesPerLine() + w * 4] for y in range(h)]
        data = b"".join(rows)
    return Image.frombytes("RGBA", (w, h), data)


def pil_to_qimage(img: Image.Image):
    from PySide6.QtGui import QImage
    img = img.convert("RGBA")
    data = img.tobytes()
    q = QImage(data, img.width, img.height, img.width * 4, QImage.Format.Format_RGBA8888)
    return q.copy()  # detach from the Python buffer


def pil_to_qpixmap(img: Image.Image):
    from PySide6.QtGui import QPixmap
    return QPixmap.fromImage(pil_to_qimage(img))


def svg_size(data: bytes) -> tuple[int, int]:
    ensure_qt_app()
    from PySide6.QtCore import QByteArray
    from PySide6.QtSvg import QSvgRenderer
    r = QSvgRenderer(QByteArray(data))
    vb = r.viewBoxF()
    if vb.width() > 0 and vb.height() > 0:
        return round(vb.width()), round(vb.height())
    s = r.defaultSize()
    return max(1, s.width()), max(1, s.height())


def render_svg(data: bytes, size: int) -> Image.Image:
    ensure_qt_app()
    from PySide6.QtCore import QByteArray, QRectF
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    r = QSvgRenderer(QByteArray(data))
    w, h = svg_size(data)
    n = max(w, h)
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    f = size / n
    r.render(p, QRectF(0, 0, w * f, h * f))
    p.end()
    return qimage_to_pil(img)
