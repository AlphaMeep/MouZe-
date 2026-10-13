import io
import struct

from PIL import Image

from mouze.formats import wincursor, xcursor


def sample(size=32, color=(255, 0, 0, 255)):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for y in range(size // 2):
        for x in range(y + 1):
            img.putpixel((x, y), color)
    img.putpixel((size - 1, size - 1), (0, 255, 0, 128))
    return img


def test_cur_roundtrip_single():
    img = sample()
    data = wincursor.write_cur(wincursor.CursorImage(img, (3, 4)))
    out = wincursor.read_cur(data)
    assert out.hotspot == (3, 4)
    assert out.image.tobytes() == img.tobytes()


def test_cur_multisize_prefers_requested():
    a, b = sample(32), sample(64)
    data = wincursor.write_cur([wincursor.CursorImage(a, (1, 1)), wincursor.CursorImage(b, (2, 2))])
    assert len(wincursor.read_cur_all(data)) == 2
    assert wincursor.read_cur(data, prefer_size=32).image.size == (32, 32)
    assert wincursor.read_cur(data).image.size == (64, 64)


def test_cur_256_size_field_wraps_to_zero():
    data = wincursor.write_cur(wincursor.CursorImage(sample(256), (0, 0)))
    assert data[6] == 0 and data[7] == 0
    assert wincursor.read_cur(data).image.size == (256, 256)


def test_cur_with_png_entry():
    img = sample(48)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    png = buf.getvalue()
    data = struct.pack("<HHH", 0, 2, 1) + struct.pack("<BBBBHHII", 48, 48, 0, 0, 5, 6, len(png), 22) + png
    out = wincursor.read_cur(data)
    assert out.hotspot == (5, 6)
    assert out.image.tobytes() == img.tobytes()


def test_ani_roundtrip_with_rates():
    frames = [wincursor.CursorImage(sample(32, (i * 40, 0, 0, 255)), (2, 2)) for i in range(5)]
    delays = [50, 100, 50, 200, 50]
    data = wincursor.write_ani(wincursor.AnimatedCursor(frames, delays, "Title", "Me"))
    assert data[:4] == b"RIFF" and data[8:12] == b"ACON"
    out = wincursor.read_ani(data)
    assert len(out.frames) == 5
    assert out.title == "Title" and out.author == "Me"
    assert [abs(d - e) <= 17 for d, e in zip(out.delays_ms, delays)] == [True] * 5
    assert out.frames[3].image.tobytes() == frames[3].image.tobytes()


def test_read_any_static():
    data = wincursor.write_cur(wincursor.CursorImage(sample(), (0, 0)))
    anim = wincursor.read_any(data)
    assert len(anim.frames) == 1


def test_xcursor_roundtrip_premultiplied():
    img = sample(24)
    xc = xcursor.XCursor({24: [xcursor.XFrame(img, (1, 2), 0)], 48: [xcursor.XFrame(sample(48), (2, 4), 0)]})
    data = xcursor.write_xcursor(xc)
    back = xcursor.read_xcursor(data)
    assert sorted(back.sizes) == [24, 48]
    fr = back.best(26)[0]
    assert fr.hotspot == (1, 2)
    # opaque pixels survive exactly; the half transparent one approximately
    assert fr.image.getpixel((0, 0)) == (255, 0, 0, 255)
    r, g, b, a = fr.image.getpixel((23, 23))
    assert a == 128 and abs(g - 255) <= 2


def test_xcursor_animated_delays():
    frames = [xcursor.XFrame(sample(32), (0, 0), 40), xcursor.XFrame(sample(32), (0, 0), 60)]
    back = xcursor.read_xcursor(xcursor.write_xcursor(xcursor.XCursor({32: frames})))
    assert [f.delay_ms for f in back.sizes[32]] == [40, 60]
