"""Hybrid local index: TF-IDF dense-ish + BM25 sparse, SQLite-canonical backed, Qdrant-optional.

Phase 1 (default): pure-local index stored under data/indexes/ — no server needed.
Qdrant adapter (src/indexing/qdrant_index.py) mirrors the same payload when QDRANT_URL is reachable.
"""
from __future__ import annotations
import json
import os
import re
import sqlite3
import numpy as np

TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*")


def tokenize_technical(text: str) -> list[str]:
    toks: list[str] = []
    for m in TOKEN_RE.finditer(text):
        t = m.group(0)
        # CamelCase split but preserve original (CanIf_Init -> canif_init, can, if, init)
        toks.append(t.lower())
        for part in re.split(r"[_\-]+", t):
            for sub in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", part):
                if len(sub) > 1:
                    toks.append(sub.lower())
    return [t for t in toks if len(t) > 1]


class HybridIndex:
    def __init__(self):
        self.chunk_ids: list[str] = []
        self.payloads: list[dict] = []
        self.texts: list[str] = []
        self.tokenized: list[list[str]] = []  # cached (500-doc scale: tokenize once at build)
        self.vocab: dict[str, int] = {}
        self.idf: np.ndarray | None = None
        self.doc_matrix: np.ndarray | None = None

    def build(self, chunks: list[dict]):
        self.chunk_ids = [c["chunk_id"] for c in chunks]
        self.payloads = chunks
        self.texts = [(c.get("section_title", "") + " " + c.get("normalized_text", "")) for c in chunks]
        # document frequency over technical tokens
        from collections import Counter
        df: Counter = Counter()
        self.tokenized = [tokenize_technical(t) for t in self.texts]
        for toks in self.tokenized:
            for t in set(toks):
                df[t] += 1
        vocab_terms = [t for t, _ in df.most_common(10000)]
        self.vocab = {t: i for i, t in enumerate(vocab_terms)}
        n = len(chunks)
        self.idf = np.array([np.log((n + 1) / (df[t] + 1)) + 1.0 for t in vocab_terms], dtype=np.float32)
        mat = np.zeros((n, len(vocab_terms)), dtype=np.float32)
        for i, toks in enumerate(self.tokenized):
            tf: Counter = Counter(toks)
            mx = max(tf.values()) if tf else 1
            for t, cnt in tf.items():
                j = self.vocab.get(t)
                if j is not None:
                    mat[i, j] = (0.5 + 0.5 * cnt / mx) * self.idf[j]
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        self.doc_matrix = mat / np.where(norms == 0, 1, norms)

    def embed_query(self, q: str) -> np.ndarray:
        toks = tokenize_technical(q)
        from collections import Counter
        tf: Counter = Counter(toks)
        mx = max(tf.values()) if tf else 1
        v = np.zeros((len(self.vocab),), dtype=np.float32)
        for t, cnt in tf.items():
            j = self.vocab.get(t)
            if j is not None:
                v[j] = (0.5 + 0.5 * cnt / mx) * self.idf[j]
        n = np.linalg.norm(v)
        return v / (n or 1.0)

    def dense_scores(self, q: str) -> np.ndarray:
        qv = self.embed_query(q)
        return (self.doc_matrix @ qv).astype(float)

    def bm25_scores(self, q: str, k1: float = 1.5, b: float = 0.75) -> np.ndarray:
        tokenized = self.tokenized or [tokenize_technical(t) for t in self.texts]
        if not self.tokenized:
            self.tokenized = tokenized
        from collections import Counter as C
        cached = getattr(self, "_bm25_cache", None)
        if cached is None or cached[2] != len(tokenized):
            df = C()
            for toks in tokenized:
                for t in set(toks):
                    df[t] += 1
            avgdl = sum(len(t) for t in tokenized) / max(1, len(tokenized))
            self._bm25_cache = (df, avgdl, len(tokenized))
        else:
            df, avgdl, _ = cached
        q_terms = tokenize_technical(q)
        n = len(tokenized)
        scores = np.zeros(n)
        for term in set(q_terms):
            idf = np.log((n - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5) + 1.0)
        for i, toks in enumerate(self.tokenized):
                f = toks.count(term)
                if f:
                    denom = f + k1 * (1 - b + b * len(toks) / (avgdl or 1))
                    scores[i] += idf * (f * (k1 + 1) / denom)
        return scores

    def save(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        np.savez_compressed(path + ".npz", matrix=self.doc_matrix, idf=self.idf)
        with open(path + ".meta.json", "w") as f:
            json.dump({"chunk_ids": self.chunk_ids, "payloads": self.payloads,
                       "texts": self.texts, "vocab": self.vocab}, f)

    @classmethod
    def load(cls, path: str) -> "HybridIndex":
        idx = cls()
        z = np.load(path + ".npz")
        idx.doc_matrix, idx.idf = z["matrix"], z["idf"]
        with open(path + ".meta.json") as f:
            m = json.load(f)
        idx.chunk_ids, idx.payloads, idx.texts, idx.vocab = m["chunk_ids"], m["payloads"], m["texts"], m["vocab"]
        return idx


def load_chunks(canonical_db: str) -> list[dict]:
    conn = sqlite3.connect(canonical_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM chunks").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("requirement_ids", "api_names", "ecu_parameters"):
            try:
                d[k] = json.loads(d[k] or "[]")
            except Exception:
                d[k] = []
        out.append(d)
    return out
