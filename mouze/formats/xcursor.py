"""Reader/writer for the Xcursor file format used by Linux desktops."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from PIL import Image

MAGIC = b"Xcur"
IMAGE_TYPE = 0xFFFD0002
COMMENT_TYPE = 0xFFFE0001


@dataclass
class XFrame:
    image: Image.Image            # RGBA, straight alpha
    hotspot: tuple[int, int]
    delay_ms: int = 0


@dataclass
class XCursor:
    # nominal size -> frames
    sizes: dict[int, list[XFrame]] = field(default_factory=dict)

    def best(self, size: int) -> list[XFrame]:
        if not self.sizes:
            return []
        nominal = min(self.sizes, key=lambda s: (abs(s - size), -s))
        return self.sizes[nominal]


def _premultiply_argb(img: Image.Image) -> bytes:
    pre = img.convert("RGBA").convert("RGBa")  # premultiplied
    r, g, b, a = pre.split()
    # Xcursor pixels are little-endian ARGB words = bytes B, G, R, A
    return Image.merge("RGBA", (b, g, r, a)).tobytes()


def _unpremultiply(data: bytes, w: int, h: int) -> Image.Image:
    img = Image.frombytes("RGBA", (w, h), data)
    b, g, r, a = img.split()
    return Image.merge("RGBa", (r, g, b, a)).convert("RGBA")


def write_xcursor(cursor: XCursor) -> bytes:
    chunks = []
    for nominal in sorted(cursor.sizes):
        for fr in cursor.sizes[nominal]:
            w, h = fr.image.size
            if w > 0x7FFF or h > 0x7FFF:
                raise ValueError("image too large")
            hx = max(0, min(w - 1, int(fr.hotspot[0])))
            hy = max(0, min(h - 1, int(fr.hotspot[1])))
            header = struct.pack("<9I", 36, IMAGE_TYPE, nominal, 1, w, h, hx, hy, max(0, int(fr.delay_ms)))
            chunks.append((nominal, header + _premultiply_argb(fr.image)))
    if not chunks:
        raise ValueError("cursor has no frames")
    ntoc = len(chunks)
    header_size = 16
    pos = header_size + ntoc * 12
    toc = []
    for nominal, blob in chunks:
        toc.append(struct.pack("<3I", IMAGE_TYPE, nominal, pos))
        pos += len(blob)
    return (MAGIC + struct.pack("<3I", header_size, 0x10000, ntoc) + b"".join(toc)
            + b"".join(blob for _, blob in chunks))


def read_xcursor(data: bytes) -> XCursor:
    if data[:4] != MAGIC:
        raise ValueError("not an Xcursor file")
    header_size, _version, ntoc = struct.unpack_from("<3I", data, 4)
    cursor = XCursor()
    for i in range(ntoc):
        ctype, subtype, pos = struct.unpack_from("<3I", data, header_size + i * 12)
        if ctype != IMAGE_TYPE:
            continue
        (_hs, _t, nominal, _v, w, h, hx, hy, delay) = struct.unpack_from("<9I", data, pos)
        pix = data[pos + 36: pos + 36 + w * h * 4]
        cursor.sizes.setdefault(nominal or subtype, []).append(
            XFrame(_unpremultiply(pix, w, h), (hx, hy), delay))
    return cursor
