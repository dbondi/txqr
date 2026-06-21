"""Throughput simulation for the TXQR pipeline.

Simulates playing the encoded animation frame-by-frame into the decoder and
measures *goodput*: original bytes recovered per second of playback. This is
the protocol/algorithm ceiling (in-memory decode); a real screen->camera link
is additionally bounded by display resolution and camera frame rate.

Each animation frame shows ``per_frame`` QR codes (parallel screens). Frames
play in order and loop until the data is fully reconstructed; with ``drop`` >
0 each QR code is independently missed with that probability, modelling a
camera that skips reads.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import List

from .protocol import Decoder, Encoder


@dataclass
class BenchResult:
    nbytes: int
    split: int
    per_frame: int
    fps: int
    redundancy: float
    drop: float
    total_anim_frames: int      # animation frames in one full loop
    anim_frames_played: float   # frames shown until decode completed (avg)
    seconds: float              # playback time until completion (avg)
    goodput: float              # original bytes / second (avg)
    completed_ratio: float      # fraction of trials that completed


def simulate(nbytes: int = 4096, split: int = 100, per_frame: int = 9,
             fps: int = 10, redundancy: float = 2.0, drop: float = 0.0,
             trials: int = 5, max_loops: int = 50,
             seed: int | None = None) -> BenchResult:
    """Run ``trials`` playback simulations and average the results."""
    rng = random.Random(seed)
    played_list: List[float] = []
    completed = 0
    total_anim = 0

    for _ in range(trials):
        data = os.urandom(nbytes)
        frames = Encoder(split, redundancy=redundancy).encode(data)
        groups = [frames[i:i + per_frame]
                  for i in range(0, len(frames), per_frame)]
        total_anim = len(groups)

        dec = Decoder()
        played = 0
        done = False
        for _loop in range(max_loops):
            for group in groups:
                played += 1
                for qr in group:
                    if drop and rng.random() < drop:
                        continue
                    dec.decode(qr)
                if dec.is_completed():
                    done = True
                    break
            if done:
                break

        if done and dec.data() == data:
            completed += 1
            played_list.append(played)

    avg_played = sum(played_list) / len(played_list) if played_list else float("nan")
    seconds = avg_played / fps if played_list else float("nan")
    goodput = nbytes / seconds if played_list and seconds else float("nan")

    return BenchResult(
        nbytes=nbytes, split=split, per_frame=per_frame, fps=fps,
        redundancy=redundancy, drop=drop, total_anim_frames=total_anim,
        anim_frames_played=avg_played, seconds=seconds, goodput=goodput,
        completed_ratio=completed / trials,
    )


def _human(n: float) -> str:
    if n != n:  # NaN
        return "    n/a"
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:6.1f} {unit}/s"
        n /= 1024
    return f"{n:6.1f} GB/s"


def format_table(results: List[BenchResult]) -> str:
    """Render a list of BenchResults as an aligned text table."""
    header = (f"{'split':>6}{'per_frame':>11}{'fps':>5}{'redund':>8}"
              f"{'drop':>6}{'anim played':>13}{'time':>8}"
              f"{'goodput':>13}{'ok':>6}")
    lines = [header, "-" * len(header)]
    for r in results:
        played = (f"{r.anim_frames_played:.0f}/{r.total_anim_frames}"
                  if r.anim_frames_played == r.anim_frames_played else "n/a")
        time = (f"{r.seconds:.2f}s"
                if r.seconds == r.seconds else "n/a")
        lines.append(
            f"{r.split:>6}{r.per_frame:>11}{r.fps:>5}{r.redundancy:>8.1f}"
            f"{r.drop:>6.2f}{played:>13}{time:>8}"
            f"{_human(r.goodput):>13}{r.completed_ratio*100:>5.0f}%"
        )
    return "\n".join(lines)
