"""The site's PNG icon (the MCP registry entry's): a real 512×512 PNG with see-through rounded corners."""
import struct
import zlib

from ltlaw.render import _icon_png


def test_icon_png():
    b = _icon_png(64)
    assert b[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", b[16:24])
    assert (w, h) == (64, 64)
    raw = zlib.decompress(b[b.index(b"IDAT") + 4:b.index(b"IEND") - 8])
    row = lambda y: raw[y * (64 * 4 + 1) + 1:(y + 1) * (64 * 4 + 1)]  # noqa: E731
    assert row(0)[3] == 0 and row(32)[4 * 32 + 3] == 255   # corner transparent, middle opaque
    assert row(18)[4 * 32:4 * 32 + 3] == b"\xff\xff\xff"   # on the first line: white
    assert row(8)[4 * 32:4 * 32 + 3] == bytes([31, 95, 168])  # between: the site's blue
