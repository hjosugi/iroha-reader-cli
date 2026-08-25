#!/usr/bin/env python3
"""Draw the application icon.

Pure standard library: the shapes are rendered 4x and averaged down,
which gives clean edges without pulling in an image library.

    python3 scripts/make-icon.py assets/icon.png [size]
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

SCALE = 4
BACKGROUND = (59, 42, 99, 255)     # deep indigo
WAVE = (242, 233, 255, 255)        # near white
SUBTITLE = (168, 132, 232, 255)    # violet

Color = tuple[int, int, int, int]


class Canvas:
    """A small RGBA canvas with the two shapes this icon needs."""

    def __init__(self, size: int):
        self.size = size
        self.pixels = bytearray(size * size * 4)

    def rounded_rect(self, x: float, y: float, w: float, h: float,
                     radius: float, color: Color) -> None:
        x0, y0, x1, y1 = int(x), int(y), int(x + w), int(y + h)
        radius = min(radius, w / 2, h / 2)
        for py in range(max(y0, 0), min(y1, self.size)):
            for px in range(max(x0, 0), min(x1, self.size)):
                if self._inside(px + 0.5, py + 0.5, x, y, w, h, radius):
                    self._set(px, py, color)

    @staticmethod
    def _inside(px: float, py: float, x: float, y: float,
                w: float, h: float, radius: float) -> bool:
        # Clamp the point into the inner rectangle; outside the corners
        # the distance to that clamped point is the corner distance.
        cx = min(max(px, x + radius), x + w - radius)
        cy = min(max(py, y + radius), y + h - radius)
        return (px - cx) ** 2 + (py - cy) ** 2 <= radius * radius

    def _set(self, x: int, y: int, color: Color) -> None:
        offset = (y * self.size + x) * 4
        self.pixels[offset:offset + 4] = bytes(color)

    def downscale(self, factor: int) -> tuple[int, bytearray]:
        """Average factor x factor blocks into one pixel."""
        out_size = self.size // factor
        out = bytearray(out_size * out_size * 4)
        area = factor * factor
        for y in range(out_size):
            for x in range(out_size):
                totals = [0, 0, 0, 0]
                for sy in range(factor):
                    row = (y * factor + sy) * self.size
                    for sx in range(factor):
                        offset = (row + x * factor + sx) * 4
                        for channel in range(4):
                            totals[channel] += self.pixels[offset + channel]
                start = (y * out_size + x) * 4
                out[start:start + 4] = bytes(total // area for total in totals)
        return out_size, out


def draw(size: int) -> tuple[int, bytearray]:
    canvas = Canvas(size * SCALE)
    unit = size * SCALE / 256  # everything below is in 256 pt units

    canvas.rounded_rect(0, 0, 256 * unit, 256 * unit, 52 * unit, BACKGROUND)

    # A waveform: five bars, tallest in the middle.
    heights = (46, 86, 118, 86, 46)
    bar_w, gap, centre = 18, 14, 96
    total = len(heights) * bar_w + (len(heights) - 1) * gap
    left = (256 - total) / 2
    for index, height in enumerate(heights):
        x = left + index * (bar_w + gap)
        canvas.rounded_rect(x * unit, (centre - height / 2) * unit,
                            bar_w * unit, height * unit, bar_w / 2 * unit, WAVE)

    # Two subtitle lines under it.
    for row, width in ((178, 148), (206, 96)):
        canvas.rounded_rect((256 - width) / 2 * unit, row * unit,
                            width * unit, 14 * unit, 7 * unit, SUBTITLE)

    return canvas.downscale(SCALE)


def write_png(path: Path, size: int, pixels: bytearray) -> None:
    raw = bytearray()
    stride = size * 4
    for y in range(size):
        raw.append(0)  # filter type 0
        raw += pixels[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else Path("assets/icon.png")
    size = int(argv[2]) if len(argv) > 2 else 256
    out.parent.mkdir(parents=True, exist_ok=True)
    written, pixels = draw(size)
    write_png(out, written, pixels)
    print(f"icon: {out} ({written}x{written})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
