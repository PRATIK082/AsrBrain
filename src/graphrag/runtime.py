"""Process-wide singleton for the GraphRAG store (so tools and the API share one file
handle instead of opening SQLite per call)."""
from __future__ import annotations

import os
import threading

from .store import GraphStore

_lock = threading.Lock()
_store: GraphStore | None = None
_store_path: str = ""


def get_store(path: str | None = None) -> GraphStore:
    global _store, _store_path
    from ..config.settings import settings
    target = path or os.environ.get("GRAPH_DB_PATH") or settings.graph_db
    with _lock:
        if _store is None or _store_path != target:
            if _store is not None:
                _store.close()
            _store = GraphStore(target)
            _store_path = target
        return _store


def reset_store() -> None:
    global _store, _store_path
    with _lock:
        if _store is not None:
            _store.close()
        _store = None
        _store_path = ""
