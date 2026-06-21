"""HCCB-style high-capacity color barcode.

A demonstration of the color-density idea behind Microsoft's High Capacity
Color Barcode (HCCB): instead of 1 bit per black/white module like a QR code,
each cell carries one of 8 well-separated colors = 3 bits per cell. That is a
~3x areal-density gain at the symbol level, before any of QR's structural and
error-correction overhead is even counted.

This is a software-pipeline codec (display -> GIF -> decode), so it relies on
the GIF palette preserving the 8 colors exactly rather than on a camera-grade
color-calibration / perspective pipeline. The geometry is axis-aligned and
deterministic: encoder and decoder share the cell/border size constants, so no
finder patterns are needed here (a real camera version would add them).

Frame layout (row-major cells):

    [ 32-bit payload length ][ payload bytes ][ padding ]

The decoder reads the length header, then exactly that many payload bytes;
trailing padding cells are ignored.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from PIL import Image

# 8 maximally-separated colors (corners of the RGB cube) -> 3 bits each.
PALETTE: List[Tuple[int, int, int]] = [
    (0, 0, 0),        # 000 black
    (255, 255, 255),  # 001 white
    (255, 0, 0),      # 010 red
    (0, 255, 0),      # 011 green
    (0, 0, 255),      # 100 blue
    (255, 255, 0),    # 101 yellow
    (0, 255, 255),    # 110 cyan
    (255, 0, 255),    # 111 magenta
]
BITS_PER_CELL = 3
BACKGROUND = (200, 200, 200)  # neutral grey quiet zone, not in PALETTE

DEFAULT_CELL = 10   # pixels per color cell
DEFAULT_BORDER = 20  # quiet-zone pixels around the grid


def _bytes_to_bits(data: bytes) -> List[int]:
    bits: List[int] = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _bits_to_bytes(bits: Sequence[int]) -> bytes:
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for b in bits[i:i + 8]:
            byte = (byte << 1) | b
        out.append(byte)
    return bytes(out)


def _payload_bits(data: bytes) -> List[int]:
    header = len(data).to_bytes(4, "big")
    bits = _bytes_to_bits(header + data)
    # Pad to a whole number of cells.
    while len(bits) % BITS_PER_CELL:
        bits.append(0)
    return bits


def encode_color(data: bytes, cell: int = DEFAULT_CELL,
                 border: int = DEFAULT_BORDER,
                 cols: int | None = None) -> Image.Image:
    """Render ``data`` into an HCCB-style color-barcode image."""
    bits = _payload_bits(data)
    n_cells = len(bits) // BITS_PER_CELL
    if cols is None:
        cols = max(1, math.ceil(math.sqrt(n_cells)))
    rows = math.ceil(n_cells / cols)

    width = 2 * border + cols * cell
    height = 2 * border + rows * cell
    img = Image.new("RGB", (width, height), BACKGROUND)
    px = img.load()

    for idx in range(n_cells):
        triple = bits[idx * 3: idx * 3 + 3]
        color = PALETTE[(triple[0] << 2) | (triple[1] << 1) | triple[2]]
        r, c = divmod(idx, cols)
        x0 = border + c * cell
        y0 = border + r * cell
        for y in range(y0, y0 + cell):
            for x in range(x0, x0 + cell):
                px[x, y] = color
    return img


def _nearest_color(rgb: Tuple[float, float, float]) -> int:
    best_i, best_d = 0, float("inf")
    for i, (pr, pg, pb) in enumerate(PALETTE):
        d = (rgb[0] - pr) ** 2 + (rgb[1] - pg) ** 2 + (rgb[2] - pb) ** 2
        if d < best_d:
            best_d, best_i = d, i
    return best_i


def decode_color(img: Image.Image, cell: int = DEFAULT_CELL,
                 border: int = DEFAULT_BORDER) -> bytes:
    """Decode an HCCB-style color-barcode image back into bytes."""
    img = img.convert("RGB")
    width, height = img.size
    px = img.load()

    cols = (width - 2 * border) // cell
    rows = (height - 2 * border) // cell
    if cols <= 0 or rows <= 0:
        return b""

    bits: List[int] = []
    half = cell // 2
    for idx in range(rows * cols):
        r, c = divmod(idx, cols)
        cx = border + c * cell + half
        cy = border + r * cell + half
        # Average a small central patch for noise tolerance.
        rs = gs = bs = 0
        cnt = 0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                x = min(max(cx + dx, 0), width - 1)
                y = min(max(cy + dy, 0), height - 1)
                pr, pg, pb = px[x, y]
                rs += pr; gs += pg; bs += pb; cnt += 1
        color_i = _nearest_color((rs / cnt, gs / cnt, bs / cnt))
        bits.extend(((color_i >> 2) & 1, (color_i >> 1) & 1, color_i & 1))

    decoded = _bits_to_bytes(bits)
    if len(decoded) < 4:
        return b""
    length = int.from_bytes(decoded[:4], "big")
    if length < 0 or 4 + length > len(decoded):
        return b""
    return decoded[4:4 + length]


def capacity_bytes(width: int, height: int, cell: int = DEFAULT_CELL,
                   border: int = DEFAULT_BORDER) -> int:
    """Usable payload bytes for an image of the given pixel size."""
    cols = (width - 2 * border) // cell
    rows = (height - 2 * border) // cell
    cells = max(0, cols) * max(0, rows)
    return max(0, cells * BITS_PER_CELL // 8 - 4)


# --- Animated-GIF pipeline, mirroring qr.py for the color codec -------------

_PAD = "\n"  # padding char to equalize frame lengths (absent from frames)


def write_color_gif(frames: Sequence[str], path: str, fps: int = 5,
                    cell: int = DEFAULT_CELL, border: int = DEFAULT_BORDER) -> int:
    """Write protocol frame strings as an animated color-barcode GIF.

    Frames are padded to a uniform length so every color image shares the same
    grid geometry (origin-aligned), which keeps decoding exact.
    """
    if not frames:
        raise ValueError("no frames to write")
    width = max(len(f) for f in frames)
    padded = [f.ljust(width, _PAD) for f in frames]
    images = [encode_color(f.encode("utf-8"), cell, border) for f in padded]
    duration_ms = int(1000 / fps) if fps else 1000
    images[0].save(path, save_all=True, append_images=images[1:],
                   duration=duration_ms, loop=0)
    return len(images)


def read_color_gif(path: str, cell: int = DEFAULT_CELL,
                   border: int = DEFAULT_BORDER) -> List[str]:
    """Decode an animated color-barcode GIF into protocol frame strings."""
    img = Image.open(path)
    out: List[str] = []
    idx = 0
    try:
        while True:
            img.seek(idx)
            data = decode_color(img.convert("RGB"), cell, border)
            if data:
                try:
                    out.append(data.decode("utf-8").rstrip(_PAD))
                except UnicodeDecodeError:
                    pass
            idx += 1
    except EOFError:
        pass
    return out
