"""Tests for the pytxqr data <-> QR transfer pipeline."""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pytxqr import Decoder, Encoder, read_animated_gif, write_animated_gif


def roundtrip_frames(data: bytes, chunk_len: int, drop=0.0,
                     redundancy=2.0) -> bytes:
    """Encode, optionally drop/shuffle frames, and decode."""
    frames = Encoder(chunk_len, redundancy=redundancy).encode(data)
    order = list(frames)
    random.shuffle(order)
    dec = Decoder()
    for f in order:
        if drop and random.random() < drop:
            continue
        dec.decode(f)
        if dec.is_completed():
            break
    assert dec.is_completed(), "decoding did not complete"
    return dec.data()


def test_single_frame():
    data = b"hi"
    assert roundtrip_frames(data, chunk_len=100) == data


def test_multi_frame_exact():
    data = b"The quick brown fox jumps over the lazy dog. " * 20
    assert roundtrip_frames(data, chunk_len=50) == data


def test_out_of_order():
    data = os.urandom(2000)
    assert roundtrip_frames(data, chunk_len=80) == data


def test_with_dropped_frames():
    # With extra redundancy, dropping a quarter of frames still recovers.
    data = os.urandom(1500)
    for _ in range(5):
        assert roundtrip_frames(data, chunk_len=64, drop=0.25,
                                redundancy=3.0) == data


def test_binary_data():
    data = bytes(range(256)) * 4
    assert roundtrip_frames(data, chunk_len=70) == data


def test_full_qr_gif_pipeline():
    data = b"Transfer me over QR codes! " * 5
    frames = Encoder(60).encode(data)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.gif")
        n = write_animated_gif(frames, path, fps=5)
        assert n == len(frames)
        assert os.path.getsize(path) > 0

        decoded_frames = read_animated_gif(path)
        dec = Decoder()
        for f in decoded_frames:
            if not f:
                continue
            dec.decode(f)
            if dec.is_completed():
                break
        assert dec.is_completed()
        assert dec.data() == data


def test_tiled_multi_screen_pipeline():
    # Pack several QR codes per animation frame for higher throughput.
    data = b"High-throughput tiled QR transfer. " * 8
    frames = Encoder(60).encode(data)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "tiled.gif")
        per_frame = 4
        n = write_animated_gif(frames, path, fps=5, per_frame=per_frame)
        # ~per_frame fewer animation frames than QR codes.
        import math
        assert n == math.ceil(len(frames) / per_frame)

        decoded = read_animated_gif(path)
        dec = Decoder()
        for f in decoded:
            if not f:
                continue
            try:
                dec.decode(f)
            except ValueError:
                continue
            if dec.is_completed():
                break
        assert dec.is_completed()
        assert dec.data() == data


def test_hccb_color_code_roundtrip():
    from pytxqr.colorcode import decode_color, encode_color

    for n in (1, 50, 777, 3000):
        data = os.urandom(n)
        img = encode_color(data, cell=8)
        assert decode_color(img, cell=8) == data


def test_hccb_density_vs_qr():
    import base64

    from pytxqr.colorcode import encode_color
    from pytxqr.qr import encode_qr

    data = os.urandom(600)
    qr = encode_qr(base64.b64encode(data).decode(), box_size=10, border=4)
    cc = encode_color(data, cell=10, border=20)
    qr_density = len(data) / (qr.width * qr.height)
    cc_density = len(data) / (cc.width * cc.height)
    # Color code should be several times denser per pixel than QR.
    assert cc_density > 3 * qr_density


def test_hccb_full_gif_pipeline():
    from pytxqr.colorcode import read_color_gif, write_color_gif

    data = b"HCCB color-barcode transfer of this payload. " * 4
    frames = Encoder(60).encode(data)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "color.gif")
        write_color_gif(frames, path, fps=5)
        dec = Decoder()
        for f in read_color_gif(path):
            if not f:
                continue
            dec.decode(f)
            if dec.is_completed():
                break
        assert dec.is_completed()
        assert dec.data() == data


def test_bench_simulation():
    from pytxqr.bench import simulate

    # No drops: always completes, goodput scales with per_frame * fps.
    base = simulate(nbytes=2048, split=100, per_frame=1, fps=10,
                    trials=3, seed=7)
    tiled = simulate(nbytes=2048, split=100, per_frame=9, fps=10,
                     trials=3, seed=7)
    assert base.completed_ratio == 1.0
    assert tiled.completed_ratio == 1.0
    assert tiled.goodput > base.goodput  # tiling raises throughput

    # With drops, extra redundancy still recovers the data.
    dropped = simulate(nbytes=2048, split=100, per_frame=9, fps=10,
                       drop=0.2, redundancy=3.0, trials=3, seed=7)
    assert dropped.completed_ratio == 1.0


if __name__ == "__main__":
    test_single_frame()
    test_multi_frame_exact()
    test_out_of_order()
    test_with_dropped_frames()
    test_binary_data()
    test_full_qr_gif_pipeline()
    test_tiled_multi_screen_pipeline()
    test_hccb_color_code_roundtrip()
    test_hccb_density_vs_qr()
    test_hccb_full_gif_pipeline()
    test_bench_simulation()
    print("All tests passed.")
