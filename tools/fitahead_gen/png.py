"""Tiny RGBA PNG encoder plus the default face drawing.

The face plate is a separate material with its own 0..1 UV square, so replacing
this texture at runtime is the whole mechanism for "the user draws their own
face". This module only supplies the placeholder.
"""

import math
import struct
import zlib


def encode_png(width, height, pixels):
    """`pixels` is a flat bytearray of RGBA rows, top to bottom."""
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter type 0 (None)
        raw.extend(pixels[y * stride:(y + 1) * stride])

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


class Canvas:
    def __init__(self, size, background):
        self.size = size
        self.px = bytearray(size * size * 4)
        for i in range(size * size):
            self.px[i * 4:i * 4 + 4] = bytes(background)

    def _blend(self, x, y, color, alpha):
        if alpha <= 0.0 or not (0 <= x < self.size and 0 <= y < self.size):
            return
        a = min(1.0, alpha)
        o = (y * self.size + x) * 4
        for c in range(3):
            self.px[o + c] = int(self.px[o + c] * (1 - a) + color[c] * a)
        self.px[o + 3] = max(self.px[o + 3], int(255 * a))

    def ellipse(self, cx, cy, rx, ry, color, softness=1.5):
        for y in range(int(cy - ry - 2), int(cy + ry + 3)):
            for x in range(int(cx - rx - 2), int(cx + rx + 3)):
                d = math.hypot((x - cx) / max(rx, 1e-6), (y - cy) / max(ry, 1e-6))
                self._blend(x, y, color, (1.0 - d) * rx / softness)

    def arc(self, cx, cy, r, thickness, start_deg, end_deg, color):
        steps = max(24, int(r * 4))
        for i in range(steps + 1):
            a = math.radians(start_deg + (end_deg - start_deg) * i / steps)
            self.ellipse(cx + math.cos(a) * r, cy + math.sin(a) * r,
                         thickness, thickness, color, softness=1.0)

    def to_png(self):
        return encode_png(self.size, self.size, self.px)


def default_face(size=512, skin=(255, 226, 205), ink=(58, 44, 40),
                 blush=(246, 150, 152)):
    """A deliberately plain round face: two dots and a smile.

    Kept minimal on purpose — it is a placeholder for the user's own drawing,
    and anything more characterful would fight with what they replace it with.
    """
    c = Canvas(size, (skin[0], skin[1], skin[2], 255))
    s = size / 512.0

    c.ellipse(size * 0.5, size * 0.5, size * 0.495, size * 0.495,
              (skin[0], skin[1], skin[2]), softness=6.0 * s)

    eye_y = size * 0.44
    for dx in (-0.145, 0.145):
        c.ellipse(size * (0.5 + dx), eye_y, 26 * s, 32 * s, ink, softness=2.0 * s)
        # catchlight, so the eye reads as glossy rather than as a flat hole
        c.ellipse(size * (0.5 + dx) + 9 * s, eye_y - 11 * s, 8 * s, 8 * s,
                  (255, 255, 255), softness=1.2 * s)

    c.arc(size * 0.5, size * 0.545, size * 0.115, 8.5 * s, 25, 155, ink)

    for dx in (-0.245, 0.245):
        c.ellipse(size * (0.5 + dx), size * 0.545, 34 * s, 22 * s, blush,
                  softness=9.0 * s)

    return c.to_png()
