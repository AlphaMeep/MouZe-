"""Reader/writer for Windows ``.cur``/``.ico`` and animated ``.ani`` cursors.

Pure Python (plus Pillow for PNG-compressed entries).  Written from the public
format descriptions; no Windows APIs are needed so packs can be built on any OS.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field

from PIL import Image

PNG_SIG = b"\x89PNG\r\n\x1a\n"


@dataclass
class CursorImage:
    image: Image.Image          # RGBA
    hotspot: tuple[int, int] = (0, 0)


@dataclass
class AnimatedCursor:
    frames: list[CursorImage] = field(default_factory=list)
    delays_ms: list[int] = field(default_factory=list)
    title: str = ""
    author: str = ""


# --------------------------------------------------------------------------- write

def _dib_bytes(img: Image.Image) -> bytes:
    """32-bit BGRA DIB with AND mask, as stored inside ICO/CUR files."""
    img = img.convert("RGBA")
    w, h = img.size
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    rgba = img.tobytes()
    stride = w * 4
    rows = []
    for y in range(h - 1, -1, -1):
        row = bytearray(rgba[y * stride:(y + 1) * stride])
        # RGBA -> BGRA
        row[0::4], row[2::4] = row[2::4], row[0::4]
        rows.append(bytes(row))
    xor = b"".join(rows)
    mask_stride = ((w + 31) // 32) * 4
    alpha = img.getchannel("A").tobytes()
    mask_rows = []
    for y in range(h - 1, -1, -1):
        bits = bytearray(mask_stride)
        for x in range(w):
            if alpha[y * w + x] == 0:
                bits[x >> 3] |= 0x80 >> (x & 7)
        mask_rows.append(bytes(bits))
    return header + xor + b"".join(mask_rows)


def write_cur(images: list[CursorImage] | CursorImage) -> bytes:
    """Encode one or more sizes of the same cursor into a ``.cur`` file."""
    if isinstance(images, CursorImage):
        images = [images]
    if not images:
        raise ValueError("no images")
    blobs = []
    for ci in images:
        w, h = ci.image.size
        if w > 256 or h > 256:
            raise ValueError("cursor images are limited to 256x256")
        blobs.append(_dib_bytes(ci.image))
    out = io.BytesIO()
    out.write(struct.pack("<HHH", 0, 2, len(images)))
    offset = 6 + 16 * len(images)
    for ci, blob in zip(images, blobs):
        w, h = ci.image.size
        hx, hy = ci.hotspot
        out.write(struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0,
                              max(0, min(w - 1, int(hx))), max(0, min(h - 1, int(hy))),
                              len(blob), offset))
        offset += len(blob)
    for blob in blobs:
        out.write(blob)
    return out.getvalue()


def _chunk(cid: bytes, data: bytes) -> bytes:
    pad = b"\0" if len(data) % 2 else b""
    return cid + struct.pack("<I", len(data)) + data + pad


def write_ani(anim: AnimatedCursor) -> bytes:
    """Encode an animated cursor.  Each frame is stored as a full ``.cur``."""
    if not anim.frames:
        raise ValueError("no frames")
    n = len(anim.frames)
    delays = list(anim.delays_ms) or [100] * n
    if len(delays) < n:
        delays += [delays[-1]] * (n - len(delays))
    jiffies = [max(1, round(d * 60 / 1000)) for d in delays[:n]]
    w, h = anim.frames[0].image.size
    anih = struct.pack("<9I", 36, n, n, w, h, 32, 1, jiffies[0], 0x1)  # AF_ICON
    body = _chunk(b"anih", anih)
    if anim.title or anim.author:
        info = b"INFO"
        if anim.title:
            info += _chunk(b"INAM", anim.title.encode("latin-1", "replace") + b"\0")
        if anim.author:
            info += _chunk(b"IART", anim.author.encode("latin-1", "replace") + b"\0")
        body = _chunk(b"LIST", info) + body
    if len(set(jiffies)) > 1:
        body += _chunk(b"rate", struct.pack(f"<{n}I", *jiffies))
    frames = b"fram" + b"".join(_chunk(b"icon", write_cur(f)) for f in anim.frames)
    body += _chunk(b"LIST", frames)
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"ACON" + body


# ---------------------------------------------------------------------------- read

def _read_dib(data: bytes) -> Image.Image:
    (size, w, h2, planes, bpp, comp, _sz, _xp, _yp, clr_used, _imp) = struct.unpack_from("<IiiHHIIiiII", data, 0)
    h = abs(h2) // 2
    bottom_up = h2 > 0
    if comp not in (0, 3):
        raise ValueError(f"unsupported DIB compression {comp}")
    off = size
    palette = []
    if bpp <= 8:
        ncolors = clr_used or (1 << bpp)
        for i in range(ncolors):
            b, g, r, _ = data[off + i * 4: off + i * 4 + 4]
            palette.append((r, g, b))
        off += ncolors * 4
    elif comp == 3:
        off += 12  # BI_BITFIELDS masks (assume standard BGRA)
    stride = ((w * bpp + 31) // 32) * 4
    xor = data[off: off + stride * h]
    off += stride * h
    mask_stride = ((w + 31) // 32) * 4
    mask = data[off: off + mask_stride * h]
    has_mask = len(mask) >= mask_stride * h
    pixels = bytearray(w * h * 4)
    any_alpha = False
    for row in range(h):
        y = (h - 1 - row) if bottom_up else row
        src = xor[row * stride:(row + 1) * stride]
        for x in range(w):
            if bpp == 32:
                b, g, r, a = src[x * 4: x * 4 + 4]
                if a:
                    any_alpha = True
            elif bpp == 24:
                b, g, r = src[x * 3: x * 3 + 3]
                a = 255
            elif bpp == 16:
                v = src[x * 2] | (src[x * 2 + 1] << 8)
                r, g, b = ((v >> 10) & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, (v & 31) * 255 // 31
                a = 255
            else:
                per_byte = 8 // bpp
                byte = src[x // per_byte]
                shift = (per_byte - 1 - (x % per_byte)) * bpp
                idx = (byte >> shift) & ((1 << bpp) - 1)
                r, g, b = palette[idx] if idx < len(palette) else (0, 0, 0)
                a = 255
            i = (y * w + x) * 4
            pixels[i:i + 4] = bytes((r, g, b, a))
    if has_mask and (bpp < 32 or not any_alpha):
        for row in range(h):
            y = (h - 1 - row) if bottom_up else row
            mrow = mask[row * mask_stride:(row + 1) * mask_stride]
            for x in range(w):
                if mrow[x >> 3] & (0x80 >> (x & 7)):
                    i = (y * w + x) * 4
                    # AND=1, XOR=0 -> transparent; AND=1, XOR!=0 -> "invert" (approximate as black)
                    if pixels[i:i + 3] == b"\0\0\0":
                        pixels[i + 3] = 0
                    else:
                        pixels[i:i + 4] = b"\0\0\0\xff"
    elif bpp == 32 and not any_alpha:
        for i in range(3, len(pixels), 4):
            pixels[i] = 255
    return Image.frombytes("RGBA", (w, h), bytes(pixels))


def read_cur_all(data: bytes) -> list[CursorImage]:
    """Return every image stored in an ICO/CUR file, largest first."""
    reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    if reserved != 0 or kind not in (1, 2):
        raise ValueError("not an ICO/CUR file")
    result = []
    for i in range(count):
        w, h, _cc, _r, hx, hy, size, offset = struct.unpack_from("<BBBBHHII", data, 6 + i * 16)
        blob = data[offset: offset + size]
        if blob[:8] == PNG_SIG:
            img = Image.open(io.BytesIO(blob)).convert("RGBA")
        else:
            img = _read_dib(blob)
        if kind == 1:  # icons have no hotspot
            hx = hy = 0
        result.append(CursorImage(img, (hx, hy)))
    result.sort(key=lambda c: c.image.width, reverse=True)
    return result


def read_cur(data: bytes, prefer_size: int | None = None) -> CursorImage:
    images = read_cur_all(data)
    if not images:
        raise ValueError("empty cursor file")
    if prefer_size:
        images.sort(key=lambda c: (abs(c.image.width - prefer_size), -c.image.width))
    return images[0]


def _iter_chunks(data: bytes, start: int, end: int):
    pos = start
    while pos + 8 <= end:
        cid = data[pos:pos + 4]
        (size,) = struct.unpack_from("<I", data, pos + 4)
        yield cid, data[pos + 8: pos + 8 + size]
        pos += 8 + size + (size & 1)


def read_ani(data: bytes) -> AnimatedCursor:
    if data[:4] != b"RIFF" or data[8:12] != b"ACON":
        raise ValueError("not an ANI file")
    icons: list[bytes] = []
    rates: list[int] | None = None
    seq: list[int] | None = None
    disp_rate = 6
    flags = 1
    title = author = ""
    for cid, chunk in _iter_chunks(data, 12, len(data)):
        if cid == b"anih" and len(chunk) >= 36:
            (_cb, _nframes, nsteps, _w, _h, _bpp, _planes, disp_rate, flags) = struct.unpack_from("<9I", chunk)
        elif cid == b"rate":
            rates = list(struct.unpack_from(f"<{len(chunk) // 4}I", chunk))
        elif cid == b"seq ":
            seq = list(struct.unpack_from(f"<{len(chunk) // 4}I", chunk))
        elif cid == b"LIST":
            kind = chunk[:4]
            for sub, sdata in _iter_chunks(chunk, 4, len(chunk)):
                if kind == b"fram" and sub == b"icon":
                    icons.append(sdata)
                elif kind == b"INFO" and sub == b"INAM":
                    title = sdata.rstrip(b"\0").decode("latin-1", "replace")
                elif kind == b"INFO" and sub == b"IART":
                    author = sdata.rstrip(b"\0").decode("latin-1", "replace")
    if not icons:
        raise ValueError("ANI file contains no frames")
    if not flags & 1:
        raise ValueError("raw-bitmap ANI frames are not supported")
    decoded = [read_cur(ic) for ic in icons]
    order = seq if seq else list(range(len(decoded)))
    frames, delays = [], []
    for step, idx in enumerate(order):
        if idx >= len(decoded):
            continue
        frames.append(decoded[idx])
        jiff = rates[step] if rates and step < len(rates) else disp_rate
        delays.append(max(1, round(jiff * 1000 / 60)))
    return AnimatedCursor(frames, delays, title, author)


def read_any(data: bytes) -> AnimatedCursor:
    """Read either a static ``.cur``/``.ico`` or an animated ``.ani``."""
    if data[:4] == b"RIFF":
        return read_ani(data)
    return AnimatedCursor([read_cur(data)], [0])
