"""File hashing helpers (consolidated)."""
from __future__ import annotations

import hashlib


def sha256_file(path: str) -> str:
    """SHA-256 of a file, chunked to keep memory low."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()