"""Bitmap helpers.

Every cursor frame inside MouZe is a Pillow ``RGBA`` image (straight alpha).
This module holds the image post-processing pipeline ("adjustments") that can
be applied to *any* skin, built-in or imported.
"""

from __future__ import annotations

import colorsys
from dataclasses import asdict, dataclass

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps


@dataclass
class Adjustments:
    """User tweaks applied on top of a skin before it is used."""

    hue: int = 0              # degrees, -180..180
    saturation: float = 1.0   # 0..2
    brightness: float = 1.0   # 0..2
    opacity: float = 1.0      # 0.1..1
    speed: float = 1.0        # animation speed multiplier, 0.25..4
    mirror: bool = False      # left-handed mode
    invert: bool = False
    grayscale: bool = False
    outline: bool = False     # add a contrasting outline (helps on busy backgrounds)
    outline_color: str = "#000000"
    shadow: bool = False      # add a soft drop shadow
    tint: str = ""            # optional "#rrggbb" colourise

    def is_identity(self) -> bool:
        return self == Adjustments()

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v != getattr(Adjustments(), k)}

    @classmethod
    def from_dict(cls, data: dict | None) -> Adjustments:
        data = dict(data or {})
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})

    def key(self) -> tuple:
        return tuple(sorted((k, str(v)) for k, v in self.to_dict().items()))


def parse_hex(color: str) -> tuple[int, int, int, int]:
    c = color.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) == 6:
        c += "ff"
    if len(c) != 8:
        raise ValueError(f"bad colour {color!r}")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), int(c[6:8], 16)


def _hue_lut(degrees: int) -> list[int]:
    shift = round((degrees % 360) / 360 * 256)
    return [(i + shift) % 256 for i in range(256)]


def hue_shift(img: Image.Image, degrees: int) -> Image.Image:
    if not degrees % 360:
        return img
    alpha = img.getchannel("A")
    h, s, v = img.convert("RGB").convert("HSV").split()
    h = h.point(_hue_lut(degrees))
    out = Image.merge("HSV", (h, s, v)).convert("RGB").convert("RGBA")
    out.putalpha(alpha)
    return out


def set_opacity(img: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 0.999:
        return img
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lambda a: int(a * max(0.0, opacity))))
    return out


def tint(img: Image.Image, color: str) -> Image.Image:
    r, g, b, _ = parse_hex(color)
    alpha = img.getchannel("A")
    gray = ImageOps.grayscale(img.convert("RGB"))
    out = ImageOps.colorize(gray, black=(int(r * 0.15), int(g * 0.15), int(b * 0.15)),
                            white=(min(255, r + 90), min(255, g + 90), min(255, b + 90)),
                            mid=(r, g, b)).convert("RGBA")
    out.putalpha(alpha)
    return out


def add_outline(img: Image.Image, color: str, width: int) -> Image.Image:
    """Draw a solid outline of ``width`` pixels around opaque areas (in place size)."""
    if width <= 0:
        return img
    alpha = img.getchannel("A").point(lambda a: 255 if a > 40 else 0)
    grown = alpha
    for _ in range(width):
        grown = grown.filter(ImageFilter.MaxFilter(3))
    r, g, b, a = parse_hex(color)
    ring = Image.new("RGBA", img.size, (r, g, b, 0))
    ring.putalpha(grown.point(lambda v: v * a // 255))
    ring.alpha_composite(img)
    return ring


def add_shadow(img: Image.Image, offset: tuple[int, int], blur: float,
               strength: float = 0.45) -> Image.Image:
    alpha = img.getchannel("A")
    shadow_a = Image.new("L", img.size, 0)
    shadow_a.paste(alpha, offset)
    shadow_a = shadow_a.filter(ImageFilter.GaussianBlur(blur))
    shadow_a = shadow_a.point(lambda v: int(v * strength))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.putalpha(shadow_a)
    out.alpha_composite(img)
    return out


def invert(img: Image.Image) -> Image.Image:
    alpha = img.getchannel("A")
    out = ImageOps.invert(img.convert("RGB")).convert("RGBA")
    out.putalpha(alpha)
    return out


def grayscale(img: Image.Image) -> Image.Image:
    alpha = img.getchannel("A")
    out = ImageOps.grayscale(img.convert("RGB")).convert("RGBA")
    out.putalpha(alpha)
    return out


def apply_color_adjustments(img: Image.Image, adj: Adjustments) -> Image.Image:
    """Colour/alpha/mirror tweaks for a single frame (size is preserved)."""
    out = img
    if adj.tint:
        out = tint(out, adj.tint)
    if adj.hue:
        out = hue_shift(out, adj.hue)
    if adj.grayscale:
        out = grayscale(out)
    if adj.invert:
        out = invert(out)
    if abs(adj.saturation - 1.0) > 1e-3:
        a = out.getchannel("A")
        out = ImageEnhance.Color(out.convert("RGB")).enhance(adj.saturation).convert("RGBA")
        out.putalpha(a)
    if abs(adj.brightness - 1.0) > 1e-3:
        a = out.getchannel("A")
        out = ImageEnhance.Brightness(out.convert("RGB")).enhance(adj.brightness).convert("RGBA")
        out.putalpha(a)
    if adj.outline:
        out = add_outline(out, adj.outline_color, max(1, round(out.width / 32)))
    if adj.shadow:
        s = max(1, round(out.width / 24))
        out = add_shadow(out, (s, s + s // 2), blur=max(0.8, out.width / 40))
    if adj.opacity < 0.999:
        out = set_opacity(out, adj.opacity)
    if adj.mirror:
        out = out.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return out


def fit_canvas(img: Image.Image, size: int, hotspot: tuple[int, int]) -> tuple[Image.Image, tuple[int, int]]:
    """Place ``img`` on a square transparent canvas of ``size`` (cropping if needed)."""
    if img.size == (size, size):
        return img, hotspot
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img.crop((0, 0, min(size, img.width), min(size, img.height))), (0, 0))
    hx = min(max(hotspot[0], 0), size - 1)
    hy = min(max(hotspot[1], 0), size - 1)
    return canvas, (hx, hy)


def scale_frame(img: Image.Image, factor: float, nearest: bool = False) -> Image.Image:
    if abs(factor - 1.0) < 1e-6:
        return img
    w = max(1, round(img.width * factor))
    h = max(1, round(img.height * factor))
    # Premultiply before resampling so transparent edges do not go dark.
    resample = Image.Resampling.NEAREST if nearest else Image.Resampling.LANCZOS
    pre = img.convert("RGBa")
    return pre.resize((w, h), resample).convert("RGBA")


def is_blank(img: Image.Image) -> bool:
    return img.getchannel("A").getbbox() is None


def hsv_to_hex(h: float, s: float, v: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def images_equal(a: Image.Image, b: Image.Image) -> bool:
    if a.size != b.size:
        return False
    return ImageChops.difference(a.convert("RGBA"), b.convert("RGBA")).getbbox() is None
