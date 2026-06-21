"""Command-line interface for pytxqr.

Subcommands::

    pytxqr encode <input> -o out.gif      # data  -> animated QR GIF
    pytxqr decode <in.gif> -o output      # animated QR GIF -> data

Use ``-`` for stdin/stdout.
"""

from __future__ import annotations

import argparse
import sys

from .protocol import Decoder, Encoder
from .qr import read_animated_gif, write_animated_gif


def _read_input(path: str) -> bytes:
    if path == "-":
        return sys.stdin.buffer.read()
    with open(path, "rb") as f:
        return f.read()


def _write_output(path: str, data: bytes) -> None:
    if path == "-":
        sys.stdout.buffer.write(data)
        return
    with open(path, "wb") as f:
        f.write(data)


def cmd_encode(args: argparse.Namespace) -> int:
    data = _read_input(args.input)
    frames = Encoder(args.split, redundancy=args.redundancy).encode(data)
    n = write_animated_gif(
        frames,
        args.output,
        fps=args.fps,
        box_size=args.box_size,
        border=args.border,
        level=args.level,
    )
    print(
        f"Encoded {len(data)} bytes into {n} QR frames -> {args.output} "
        f"({args.fps} fps)",
        file=sys.stderr,
    )
    return 0


def cmd_decode(args: argparse.Namespace) -> int:
    frames = read_animated_gif(args.input)
    dec = Decoder()
    read = 0
    for frame in frames:
        if not frame:
            continue
        try:
            dec.decode(frame)
            read += 1
        except ValueError:
            continue
        if dec.is_completed():
            break

    if not dec.is_completed():
        print(
            f"Incomplete: decoded {read}/{len(frames)} frames, "
            "not enough to reconstruct data",
            file=sys.stderr,
        )
        return 1

    data = dec.data()
    _write_output(args.output, data)
    print(
        f"Recovered {len(data)} bytes from {read} frames -> {args.output}",
        file=sys.stderr,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pytxqr",
        description="Transfer data via animated QR codes (Python TXQR).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    enc = sub.add_parser("encode", help="encode data into an animated QR GIF")
    enc.add_argument("input", help="input file ('-' for stdin)")
    enc.add_argument("-o", "--output", default="out.gif", help="output GIF")
    enc.add_argument("--split", type=int, default=100,
                     help="chunk size per QR frame (default: 100)")
    enc.add_argument("--redundancy", type=float, default=2.0,
                     help="fountain-code redundancy factor (default: 2.0)")
    enc.add_argument("--fps", type=int, default=5, help="animation FPS")
    enc.add_argument("--box-size", type=int, default=8, help="QR pixel size")
    enc.add_argument("--border", type=int, default=4, help="QR quiet-zone size")
    enc.add_argument("--level", default="medium",
                     choices=["low", "medium", "high", "highest"],
                     help="QR error-correction level")
    enc.set_defaults(func=cmd_encode)

    dec = sub.add_parser("decode", help="decode an animated QR GIF into data")
    dec.add_argument("input", help="input animated GIF")
    dec.add_argument("-o", "--output", default="-",
                     help="output file ('-' for stdout)")
    dec.set_defaults(func=cmd_decode)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
