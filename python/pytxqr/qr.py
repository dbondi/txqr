"""QR code rendering and reading helpers.

Rendering uses the ``qrcode`` library; reading uses OpenCV's QR detector so
the whole pipeline is dependency-light and works headless.
"""

from __future__ import annotations

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


def frames_to_images(frames: Sequence[str], box_size: int = 8,
                     border: int = 4, level: str = "medium") -> List[Image.Image]:
    """Render every frame to a QR image, all normalized to the same size."""
    images = [encode_qr(f, box_size, border, level) for f in frames]
    if not images:
        return images
    max_w = max(im.width for im in images)
    max_h = max(im.height for im in images)
    normalized = []
    for im in images:
        if im.size != (max_w, max_h):
            canvas = Image.new("RGB", (max_w, max_h), "white")
            canvas.paste(im, ((max_w - im.width) // 2, (max_h - im.height) // 2))
            im = canvas
        normalized.append(im)
    return normalized


def write_animated_gif(frames: Sequence[str], path: str, fps: int = 5,
                       box_size: int = 8, border: int = 4,
                       level: str = "medium") -> int:
    """Write frames as an animated GIF. Returns the number of frames written."""
    images = frames_to_images(frames, box_size, border, level)
    if not images:
        raise ValueError("no frames to write")
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


def read_animated_gif(path: str) -> List[str]:
    """Decode every frame of an animated GIF into its QR string."""
    img = Image.open(path)
    out: List[str] = []
    try:
        idx = 0
        while True:
            img.seek(idx)
            out.append(decode_qr(img.copy()))
            idx += 1
    except EOFError:
        pass
    return out
