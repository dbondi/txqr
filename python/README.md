# pytxqr — TXQR in pure Python

A Python port of the **core** of [TXQR](../README.md): transferring arbitrary
data through an **animated stream of QR codes**.

It keeps the essential idea that makes TXQR work — [Luby Transform **fountain
codes**](https://en.wikipedia.org/wiki/Fountain_code) — so a receiver can
reconstruct the original data from *any* sufficiently large subset of frames,
even if some are missed, read out of order, or read twice. This is exactly the
property you need when a camera reads a looping animation off a screen.

Mobile/camera apps are intentionally out of scope (per the task) — this focuses
on the **data ⇆ QR code transfer** itself, with an animated GIF as the on-screen
transport and OpenCV to read frames back for verification.

## How it works

```
raw bytes ──base64──▶ text ──split──▶ fixed-size chunks
        ──LT fountain encode──▶ encoded blocks ──frame──▶ strings ──▶ QR images
```

Each frame string rendered into one QR code looks like:

```
blockID/chunkLen/total|<base64 payload>
```

* `blockID` — identifies the fountain block and (deterministically) which
  source chunks it XORs together, so no XOR-structure metadata is transmitted.
* `chunkLen` — source chunk size.
* `total` — length of the base64 text, which tells the decoder how many chunks
  to expect.
* payload — base64 of the XORed block bytes (kept ASCII so QR codes stay small).

The decoder feeds blocks into a belief-propagation (peeling) LT decoder until
every source chunk is recovered, then trims padding and base64-decodes.

## Install

```bash
cd python
pip install -r requirements.txt
# or: pip install .
```

## CLI usage

```bash
# data  ->  animated QR GIF
python -m pytxqr.cli encode input.bin -o out.gif --split 100 --fps 5

# animated QR GIF  ->  data
python -m pytxqr.cli decode out.gif -o recovered.bin
```

Use `-` for stdin/stdout. Encode options: `--split` (chunk size), `--redundancy`
(fountain overhead, default 2.0), `--fps`, `--box-size`, `--border`, and
`--level` (`low`/`medium`/`high`/`highest` QR error correction).

## Library usage

```python
from pytxqr import Encoder, Decoder, write_animated_gif, read_animated_gif

frames = Encoder(chunk_len=100).encode(b"hello world")
write_animated_gif(frames, "out.gif", fps=5)

dec = Decoder()
for frame in read_animated_gif("out.gif"):
    if frame:
        dec.decode(frame)
    if dec.is_completed():
        break
assert dec.data() == b"hello world"
```

## Tests

```bash
python tests/test_pytxqr.py    # or: pytest tests/
```

Covers single/multi-frame transfers, out-of-order frames, dropped frames,
binary data, and the full QR→GIF→decode pipeline.
