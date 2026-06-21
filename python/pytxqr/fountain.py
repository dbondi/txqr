"""Luby Transform (LT) fountain codes.

This is a pure-Python, self-contained implementation of LT fountain codes,
mirroring the role of ``github.com/google/gofountain`` in the original Go
TXQR project. Fountain codes let a receiver reconstruct the original data
from *any* sufficiently large subset of the transmitted blocks, which is
exactly what you want for transferring data over a lossy, one-way channel
such as an animated stream of QR codes: the camera can miss frames, read
them out of order, or read the same frame twice, and the data still comes
through.

Encoder and decoder agree on the structure of each encoded block purely from
its integer block id: the id seeds a PRNG that determines the block's degree
(how many source blocks are XORed together) and which source blocks those
are. This means no per-block metadata about the XOR structure needs to be
transmitted -- only the block id.
"""

from __future__ import annotations

import random
from typing import List, Sequence


def _robust_soliton(k: int, c: float = 0.03, delta: float = 0.05) -> List[float]:
    """Return the robust soliton degree distribution for ``k`` source blocks.

    The result is a probability mass function indexed by degree (index 0 is
    unused and always 0). This distribution keeps the average degree low while
    ensuring enough degree-one blocks exist to bootstrap decoding.
    """
    if k == 1:
        return [0.0, 1.0]

    # Ideal soliton distribution.
    rho = [0.0] * (k + 1)
    rho[1] = 1.0 / k
    for d in range(2, k + 1):
        rho[d] = 1.0 / (d * (d - 1))

    # Robust component.
    import math

    s = c * math.log(k / delta) * math.sqrt(k)
    spike = int(k / s) if s else k
    spike = min(max(spike, 1), k)

    tau = [0.0] * (k + 1)
    for d in range(1, spike):
        tau[d] = s / (k * d)
    if spike < k:
        tau[spike] = s * math.log(s / delta) / k

    beta = sum(rho[d] + tau[d] for d in range(1, k + 1))
    return [0.0] + [(rho[d] + tau[d]) / beta for d in range(1, k + 1)]


def _sample_degree(rng: random.Random, cdf: Sequence[float]) -> int:
    """Sample a degree from a cumulative distribution function."""
    r = rng.random()
    for d in range(1, len(cdf)):
        if r <= cdf[d]:
            return d
    return len(cdf) - 1


def _cdf(pmf: Sequence[float]) -> List[float]:
    out = [0.0] * len(pmf)
    acc = 0.0
    for i in range(1, len(pmf)):
        acc += pmf[i]
        out[i] = acc
    return out


def source_blocks_for(block_id: int, num_chunks: int) -> List[int]:
    """Deterministically derive which source chunks compose an encoded block.

    Both encoder and decoder call this with the same ``block_id`` and
    ``num_chunks`` and therefore agree on the XOR structure without it ever
    being transmitted.
    """
    rng = random.Random(block_id)
    cdf = _cdf(_robust_soliton(num_chunks))
    degree = _sample_degree(rng, cdf)
    degree = min(degree, num_chunks)
    return rng.sample(range(num_chunks), degree)


def encode_block(block_id: int, chunks: Sequence[bytes]) -> bytes:
    """Build a single encoded LT block by XOR-ing its source chunks."""
    indices = source_blocks_for(block_id, len(chunks))
    size = len(chunks[0])
    acc = bytearray(size)
    for idx in indices:
        chunk = chunks[idx]
        for i in range(size):
            acc[i] ^= chunk[i]
    return bytes(acc)


class LTDecoder:
    """Online Gaussian-elimination decoder for LT fountain codes over GF(2).

    Each received block is a linear equation over the source chunks: a set of
    source indices (the coefficient row) plus the XORed bytes (the right-hand
    side). Maintaining the system in row-echelon form means the data is
    recoverable as soon as ``num_chunks`` linearly-independent blocks have
    arrived -- *any* such set works. This avoids the extra overhead and
    occasional stalls of pure belief-propagation (peeling), which only makes
    progress when a degree-one block happens to be available.
    """

    def __init__(self, num_chunks: int, chunk_len: int):
        self.num_chunks = num_chunks
        self.chunk_len = chunk_len
        # pivot index -> [coeffs:set, data:bytearray]; coeffs' min == key.
        self._pivots: dict[int, list] = {}
        self.recovered: List[bytes | None] = [None] * num_chunks

    def add_block(self, block_id: int, data: bytes) -> None:
        """Add a received block and reduce it into the echelon system."""
        coeffs = set(source_blocks_for(block_id, self.num_chunks))
        block_data = bytearray(data)

        # Reduce against existing pivot rows until a new pivot or empty row.
        while coeffs:
            p = min(coeffs)
            pivot = self._pivots.get(p)
            if pivot is None:
                self._pivots[p] = [coeffs, block_data]  # new pivot
                break
            pc, pd = pivot
            coeffs ^= pc  # GF(2) row addition on coefficients
            self._xor_into(block_data, pd)
        # If coeffs became empty the block was linearly dependent: discard.

    @staticmethod
    def _xor_into(dst: bytearray, src: bytes) -> None:
        for i in range(len(dst)):
            dst[i] ^= src[i]

    def is_complete(self) -> bool:
        return len(self._pivots) == self.num_chunks

    def data(self) -> bytes:
        """Back-substitute the echelon system and return the padded data."""
        if not self.is_complete():
            raise ValueError("decoding not yet complete")

        # Every source index is a pivot; back-substitute high index -> low.
        for p in sorted(self._pivots, reverse=True):
            coeffs, d = self._pivots[p]
            out = bytearray(d)
            for q in coeffs:
                if q != p:
                    # q > p (p was the row minimum), so already solved.
                    self._xor_into(out, self.recovered[q])  # type: ignore[arg-type]
            self.recovered[p] = bytes(out)

        return b"".join(self.recovered)  # type: ignore[arg-type]
