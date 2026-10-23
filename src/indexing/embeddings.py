"""Local dense embeddings (ADR-0002 spike).

BGE-M3-class open model via sentence-transformers, run on local GPU/CPU — no data
leaves the box. Imported lazily so the default TF-IDF path never pays for torch.
``encoder`` is injectable so unit tests never download a model.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

DEFAULT_MODEL = "BAAI/bge-m3"
OLLAMA_MODEL = "bge-m3"


@lru_cache(maxsize=4)
def get_model(name: str = DEFAULT_MODEL):
    from sentence_transformers import SentenceTransformer
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return SentenceTransformer(name, device=device)


def _ollama_host() -> str:
    """Client-side host: OLLAMA_HOST=0.0.0.0 means 'bind all' for the server but
    is not a connectable address, so map it to loopback for the client."""
    import os
    raw = os.getenv("OLLAMA_HOST", "127.0.0.1:11434").strip()
    if "://" not in raw:
        raw = "http://" + raw
    raw = raw.replace("0.0.0.0", "127.0.0.1")
    host_part = raw.split("://", 1)[1]
    if ":" not in host_part:
        raw = raw + ":11434"
    return raw


def _ollama_encode(texts: list[str], model: str = OLLAMA_MODEL) -> np.ndarray:
    """Same BGE-M3 weights served by local Ollama (GPU, no torch needed).

    Batch-first for speed; a batch that returns NaN (observed on some chunk
    texts) is retried item-by-item, and persistently failing items get a zero
    vector (dense score 0 — BM25 still covers them) instead of killing the run.
    """
    import ollama
    client = ollama.Client(host=_ollama_host())
    out: list[list[float] | None] = [None] * len(texts)
    dim = 1024
    bad_batches = bad_items = 0
    for i in range(0, len(texts), 64):
        batch = texts[i:i + 64]
        try:
            res = client.embed(model=model, input=batch)
            for j, v in enumerate(res["embeddings"]):
                out[i + j] = v
            if res["embeddings"]:
                dim = len(res["embeddings"][0])
        except Exception:
            bad_batches += 1
            for j, t in enumerate(batch):
                try:
                    r1 = client.embed(model=model, input=t)
                    out[i + j] = r1["embeddings"][0]
                    dim = len(r1["embeddings"][0])
                except Exception:
                    bad_items += 1
    print(f"ollama embed: {len(texts)} texts, {bad_batches} batch retries, "
          f"{bad_items} zero-vector fallbacks")
    return np.asarray([v if v is not None else [0.0] * dim for v in out],
                      dtype=np.float32)


def encode(texts: list[str], model_name: str = DEFAULT_MODEL, encoder=None,
           engine: str = "ollama") -> np.ndarray:
    """L2-normalised float32 vectors, one row per text.

    engine=ollama uses the local Ollama server (works without torch);
    engine=st uses sentence-transformers in-process. encoder override wins (tests).
    """
    safe = [t if t and t.strip() else "(empty chunk)" for t in texts]
    if encoder is not None:
        vecs = np.asarray(encoder(safe), dtype=np.float32)
    elif engine == "ollama":
        vecs = _ollama_encode(safe, OLLAMA_MODEL if model_name == DEFAULT_MODEL else model_name)
    else:
        model = get_model(model_name)
        vecs = np.asarray(model.encode(safe, batch_size=32, show_progress_bar=False,
                                       convert_to_numpy=True, normalize_embeddings=False),
                          dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return (vecs / np.where(norms == 0, 1, norms)).astype(np.float32)
