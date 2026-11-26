"""SHA-256 helpers used for integrity checks and duplicate detection."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

CHUNK_SIZE = 1024 * 1024


class Sha256Accumulator:
    """Incremental SHA-256 hasher for streamed uploads."""

    def __init__(self) -> None:
        self._hasher: Any = hashlib.sha256()

    def update(self, chunk: bytes) -> None:
        self._hasher.update(chunk)

    def hexdigest(self) -> str:
        return str(self._hasher.hexdigest())


def sha256_file(path: Path) -> str:
    accumulator = Sha256Accumulator()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            accumulator.update(chunk)
    return accumulator.hexdigest()
