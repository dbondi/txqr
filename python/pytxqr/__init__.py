"""pytxqr -- transfer data via animated QR codes, in pure Python.

A Python port of the core of TXQR (https://github.com/divan/txqr): the
data <-> animated-QR-code transfer pipeline, using Luby Transform fountain
codes for loss-tolerant, out-of-order reconstruction.

Typical use::

    from pytxqr import Encoder, Decoder

    frames = Encoder(chunk_len=100).encode(b"hello world")
    dec = Decoder()
    for f in frames:
        dec.decode(f)
    assert dec.data() == b"hello world"
"""

from .colorcode import (
    decode_color,
    encode_color,
    read_color_gif,
    write_color_gif,
)
from .protocol import Decoder, Encoder
from .qr import (
    decode_qr,
    encode_qr,
    read_animated_gif,
    write_animated_gif,
)

__all__ = [
    "Encoder",
    "Decoder",
    "encode_qr",
    "decode_qr",
    "write_animated_gif",
    "read_animated_gif",
    "encode_color",
    "decode_color",
    "write_color_gif",
    "read_color_gif",
]

__version__ = "0.1.0"
