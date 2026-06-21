"""QR code rendering and reading helpers.

Rendering uses the ``qrcode`` library; reading uses OpenCV's QR detector so
the whole pipeline is dependency-light and works headless.

Frames can be shown one-per-animation-frame, or packed N-per-frame as a grid
of QR "screens" to multiply throughput: each animation frame then carries N
fountain blocks instead of one. Because the transport uses fountain codes,
the reader does not need to recover every tile from every frame -- any missed
tiles are simply covered by other frames.
"""

from __future__ import annotations

import math
from typing import List, Sequence

import qrcode
from PIL import Image

# QR error-correction levels, matching the original project's names.
import qrcode.constants as _c

LEVELS = {
    "low": _c.ERROR_CORRECT_L,      # ~7%
    "medium": _c.ERROR_CORRECT_M,   # ~15% (good default)
    "high": _c.ERROR_CORRECT_Q,     # ~25%
    "highest": _c.ERROR_CORRECT_H,  # ~30%
}


def encode_qr(data: str, box_size: int = 8, border: int = 4,
              level: str = "medium") -> Image.Image:
    """Render a single string into a QR code image (RGB)."""
    qr = qrcode.QRCode(
        error_correction=LEVELS[level],
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def _normalize(images: Sequence[Image.Image]) -> List[Image.Image]:
    """Pad all images onto a common-sized white canvas (centered)."""
    if not images:
        return list(images)
    max_w = max(im.width for im in images)
    max_h = max(im.height for im in images)
    out = []
    for im in images:
        if im.size != (max_w, max_h):
            canvas = Image.new("RGB", (max_w, max_h), "white")
            canvas.paste(im, ((max_w - im.width) // 2, (max_h - im.height) // 2))
            im = canvas
        out.append(im)
    return out


def frames_to_images(frames: Sequence[str], box_size: int = 8,
                     border: int = 4, level: str = "medium") -> List[Image.Image]:
    """Render every frame to a QR image, all normalized to the same size."""
    return _normalize([encode_qr(f, box_size, border, level) for f in frames])


def _grid_dims(n: int, cols: int | None = None) -> tuple[int, int]:
    """Return (rows, cols) for laying out ``n`` tiles in a near-square grid."""
    if cols is None:
        cols = math.ceil(math.sqrt(n))
    cols = max(1, min(cols, n))
    rows = math.ceil(n / cols)
    return rows, cols


def compose_tiles(images: Sequence[Image.Image], cols: int | None = None,
                  gap: int = 16) -> Image.Image:
    """Lay equal-sized QR images out as a grid on a white background.

    A gap (quiet zone) between tiles lets QR detectors separate them.
    """
    images = _normalize(images)
    rows, cols = _grid_dims(len(images), cols)
    w, h = images[0].size
    width = cols * w + (cols + 1) * gap
    height = rows * h + (rows + 1) * gap
    canvas = Image.new("RGB", (width, height), "white")
    for i, im in enumerate(images):
        r, c = divmod(i, cols)
        canvas.paste(im, (gap + c * (w + gap), gap + r * (h + gap)))
    return canvas


def write_animated_gif(frames: Sequence[str], path: str, fps: int = 5,
                       per_frame: int = 1, cols: int | None = None,
                       gap: int = 16, box_size: int = 8, border: int = 4,
                       level: str = "medium") -> int:
    """Write frames as an animated GIF. Returns the number of GIF frames.

    ``per_frame`` controls how many QR codes are tiled into each animation
    frame (parallel "screens"). With ``per_frame=N`` each frame carries N
    fountain blocks, cutting the number of animation frames ~N-fold.
    """
    images = frames_to_images(frames, box_size, border, level)
    if not images:
        raise ValueError("no frames to write")

    if per_frame > 1:
        tiles = [
            compose_tiles(images[i:i + per_frame], cols=cols, gap=gap)
            for i in range(0, len(images), per_frame)
        ]
        images = _normalize(tiles)

    duration_ms = int(1000 / fps) if fps else 1000
    images[0].save(
        path,
        save_all=True,
        append_images=images[1:],
        duration=duration_ms,
        loop=0,
    )
    return len(images)


def decode_qr(image: Image.Image) -> str:
    """Decode a single QR image back into its string, or '' if none found."""
    import numpy as np
    import cv2

    arr = np.array(image.convert("RGB"))[:, :, ::-1]  # RGB -> BGR for cv2
    detector = cv2.QRCodeDetector()
    text, _points, _ = detector.detectAndDecode(arr)
    return text or ""


def decode_qr_multi(image: Image.Image) -> List[str]:
    """Decode all QR codes present in an image (e.g. a tiled grid frame)."""
    import numpy as np
    import cv2

    arr = np.array(image.convert("RGB"))[:, :, ::-1]
    detector = cv2.QRCodeDetector()
    ok, infos, _points, _ = detector.detectAndDecodeMulti(arr)
    if not ok:
        single = decode_qr(image)
        return [single] if single else []
    return [t for t in infos if t]


def read_animated_gif(path: str) -> List[str]:
    """Decode an animated GIF into the list of all QR strings it carries.

    Works for both single-QR and tiled (multi-QR) frames; every detected QR
    string across every animation frame is returned (duplicates included --
    the protocol decoder ignores repeats).
    """
    img = Image.open(path)
    out: List[str] = []
    idx = 0
    try:
        while True:
            img.seek(idx)
            out.extend(decode_qr_multi(img.copy()))
            idx += 1
    except EOFError:
        pass
    return out
