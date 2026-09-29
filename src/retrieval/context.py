"""Parent-child expansion + extractive compression (spec §14–15)."""
from __future__ import annotations
import re


def parent_expand(ranked: list[dict], by_id: dict[str, dict], max_parents: int = 6) -> list[dict]:
    """If ≥2 atomics share a parent context chunk, swap them for the parent (bounded)."""
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in ranked:
        if c.get("parent_chunk_id"):
            groups[c["parent_chunk_id"]].append(c)
    parents = []
    used = set()
    for pid, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(members) >= 2 and pid in by_id and len(parents) < max_parents:
            p = dict(by_id[pid])
            p["rerank_score"] = max(m.get("rerank_score", 0) for m in members)
            p["merged_from"] = [m["chunk_id"] for m in members]
            parents.append(p)
            used.update(m["chunk_id"] for m in members)
    rest = [c for c in ranked if c["chunk_id"] not in used]
    merged = parents + rest
    merged.sort(key=lambda d: d.get("rerank_score", 0), reverse=True)
    return merged


NORMATIVE = ("shall", "shall not", "should", "may", "must", "never", "always")


def compress(text: str, query: str, max_chars: int = 1500) -> str:
    """Extractive: keep sentences with query overlap + normative sentences; never rewrite."""
    sents = re.split(r"(?<=[.!?])\s+", text)
    qtokens = set(re.findall(r"[a-z0-9_]+", query.lower()))
    scored = []
    for s in sents:
        toks = set(re.findall(r"[a-z0-9_]+", s.lower()))
        overlap = len(qtokens & toks)
        bonus = 2 if any(n in s.lower() for n in NORMATIVE) else 0
        scored.append((overlap + bonus, s))
    scored.sort(key=lambda x: -x[0])
    out, total = [], 0
    for _, s in scored:
        if total + len(s) > max_chars:
            continue
        out.append(s)
        total += len(s)
        if total >= max_chars:
            break
    # restore original order
    order = {s: i for i, s in enumerate(sents)}
    out.sort(key=lambda s: order.get(s, 0))
    return " ".join(out) if out else text[:max_chars]
