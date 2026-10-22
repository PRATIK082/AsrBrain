"""Frozen train / hold-out split for the golden set (master prompt §9, §3).

The split is **deterministic**: a query lands in the hold-out when
``sha256(query_id + salt)`` falls in the bottom ``holdout_ratio`` of the hash space. Nothing about
the item content or its position in the file can move an item between splits, so re-running the
harness never silently re-shuffles the evaluation set.

The split is *frozen*: the manifest records the SHA-256 of the golden file it was created from.
If the golden file changes, :func:`verify_split` reports the drift so the hold-out cannot be
quietly reshaped.
"""
from __future__ import annotations

import hashlib
import json
import os

DEFAULT_SALT = "asrbrain-holdout-2026"
DEFAULT_RATIO = 0.2


def _bucket(query_id: str, salt: str) -> float:
    digest = hashlib.sha256(f"{query_id}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(1 << 64)


def split_ids(items: list[dict], ratio: float = DEFAULT_RATIO, salt: str = DEFAULT_SALT) -> dict:
    """Return ``{"train": [...], "holdout": [...]}`` of query ids."""
    train: list[str] = []
    holdout: list[str] = []
    for item in items:
        qid = item.get("query_id", "")
        (holdout if _bucket(qid, salt) < ratio else train).append(qid)
    return {"train": sorted(train), "holdout": sorted(holdout)}


def save_split(path: str, items: list[dict], golden_path: str, ratio: float = DEFAULT_RATIO,
               salt: str = DEFAULT_SALT) -> dict:
    """Freeze a split manifest next to the golden set."""
    parts = split_ids(items, ratio, salt)
    manifest = {
        "version": 1,
        "salt": salt,
        "holdout_ratio": ratio,
        "golden_sha256": _sha256_file(golden_path),
        "golden_path": golden_path,
        "counts": {"train": len(parts["train"]), "holdout": len(parts["holdout"])},
        "train": parts["train"],
        "holdout": parts["holdout"],
        "note": "Hold-out is scored for reporting only. Never tune a change on it "
                "(master prompt §3).",
    }
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    return manifest


def load_split(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def apply_split(items: list[dict], manifest: dict) -> tuple[list[dict], list[dict]]:
    """Split golden items into (train, hold-out) using a frozen manifest."""
    holdout_ids = set(manifest.get("holdout", []))
    train, holdout = [], []
    for item in items:
        (holdout if item.get("query_id") in holdout_ids else train).append(item)
    return train, holdout


def verify_split(items: list[dict], manifest: dict, golden_path: str) -> list[str]:
    """Report drift between the frozen manifest and the golden set on disk."""
    problems: list[str] = []
    current = _sha256_file(golden_path)
    frozen = manifest.get("golden_sha256")
    if frozen and current != frozen:
        problems.append(
            f"golden set changed since the split was frozen ({frozen[:12]} -> {current[:12]}); "
            "re-freeze deliberately with src.evaluation.splits")
    known = {i.get("query_id") for i in items}
    missing = [q for q in manifest.get("holdout", []) if q not in known]
    if missing:
        problems.append(f"{len(missing)} hold-out ids are absent from the golden set: {missing[:5]}")
    return problems


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()
