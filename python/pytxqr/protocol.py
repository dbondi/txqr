"""TXQR transmission protocol: encode/decode of data into framed chunks.

This mirrors ``encode.go`` and ``decode.go`` from the original Go project.

The flow is:

    raw data  --base64-->  text  --split-->  fixed-size chunks
        --LT fountain encode-->  encoded blocks  --frame-->  strings

Each frame string is what gets rendered into a single QR code:

    blockID/chunkLen/total|<base64 payload>

where ``blockID`` identifies the LT block (and thus its XOR structure),
``chunkLen`` is the source chunk size, ``total`` is the length of the
base64 text, and the payload is the base64-encoded XORed block bytes.

base64 is applied to the block bytes because XOR-ing arbitrary data produces
arbitrary (non-printable) bytes, and keeping the QR payload ASCII makes the
codes smaller and the round-trip robust.
"""

from __future__ import annotations

import base64
import math
from typing import List

from .fountain import LTDecoder, encode_block

DEFAULT_REDUNDANCY = 2.0


def _number_of_chunks(length: int, chunk_len: int) -> int:
    return math.ceil(length / chunk_len) if length else 0


def _split(text: bytes, chunk_len: int) -> List[bytes]:
    """Split ``text`` into ``chunk_len`` sized chunks, padding the last."""
    chunks = []
    for i in range(0, len(text), chunk_len):
        chunk = text[i : i + chunk_len]
        if len(chunk) < chunk_len:
            chunk = chunk + b"\x00" * (chunk_len - len(chunk))
        chunks.append(chunk)
    return chunks


class Encoder:
    """Encodes data into a list of QR-ready frame strings."""

    def __init__(self, chunk_len: int, redundancy: float = DEFAULT_REDUNDANCY):
        if chunk_len <= 0:
            raise ValueError("chunk_len must be positive")
        self.chunk_len = chunk_len
        self.redundancy = redundancy

    def encode(self, data: bytes) -> List[str]:
        """Return frame strings encoding ``data``.

        The input is base64-encoded first so the protocol is binary-safe.
        """
        text = base64.b64encode(data)
        total = len(text)

        # Small payloads that fit in one chunk are sent verbatim (block 0).
        if total <= self.chunk_len:
            payload = base64.b64encode(text).decode("ascii")
            return [self._frame(0, total, payload)]

        chunks = _split(text, self.chunk_len)
        num_chunks = len(chunks)
        num_blocks = max(int(num_chunks * self.redundancy), num_chunks + 1)

        frames = []
        for block_id in range(num_blocks):
            block = encode_block(block_id, chunks)
            payload = base64.b64encode(block).decode("ascii")
            frames.append(self._frame(block_id, total, payload))
        return frames

    def _frame(self, block_id: int, total: int, payload: str) -> str:
        return f"{block_id}/{self.chunk_len}/{total}|{payload}"


class Decoder:
    """Decodes frame strings back into the original data."""

    def __init__(self) -> None:
        self._decoder: LTDecoder | None = None
        self._total = 0
        self._chunk_len = 0
        self._single_payload: bytes | None = None
        self._seen: set[str] = set()
        self.completed = False

    @staticmethod
    def validate(frame: str) -> None:
        """Raise ValueError if ``frame`` is not a well-formed TXQR frame."""
        if not frame or len(frame) < 4 or "|" not in frame:
            raise ValueError(f"invalid frame: {frame!r}")

    def decode(self, frame: str) -> None:
        """Feed a single frame into the decoder."""
        self.validate(frame)
        header, payload = frame.split("|", 1)

        # Skip duplicate frames (cameras often read the same one repeatedly).
        if header in self._seen:
            return
        self._seen.add(header)

        parts = header.split("/")
        if len(parts) != 3:
            raise ValueError(f"invalid header: {header!r}")
        block_id, chunk_len, total = (int(p) for p in parts)

        block = base64.b64decode(payload)

        # Single-frame fast path. ``block`` is the base64 text directly.
        if total <= chunk_len and block_id == 0 and self._decoder is None:
            self._single_payload = block
            self._total = total
            self.completed = True
            return

        if self._decoder is None:
            self._total = total
            self._chunk_len = chunk_len
            num_chunks = _number_of_chunks(total, chunk_len)
            self._decoder = LTDecoder(num_chunks, chunk_len)

        self._decoder.add_block(block_id, block)
        if self._decoder.is_complete():
            self.completed = True

    def is_completed(self) -> bool:
        return self.completed

    def data(self) -> bytes:
        """Return the fully reconstructed original data."""
        if not self.completed:
            raise ValueError("decoding not yet complete")

        if self._single_payload is not None:
            text = self._single_payload
        else:
            assert self._decoder is not None
            text = self._decoder.data()[: self._total]
        return base64.b64decode(text)

    def reset(self) -> None:
        self.__init__()  # type: ignore[misc]
