"""Parent-child expansion + extractive compression (spec §14–15)."""
from __future__ import annotations
import re


MODEL_PATTERNS = [r"(?<!Traffic )Class [A-Z]\w*", r"Package M2::", r"Aggregated by",
                  r"Base ARObject", "«enumeration»", r"atp\.recommendedPackage"]
CONFIG_MARKERS = ("Mapping Rule", "ECUC-", "BSW Description", "Template Description",
                  "M2 Parameter", "shall ", "constr_")


def is_model_structure(chunk: dict) -> bool:
    """True when a chunk is dominantly an M2 class definition, rather than template
    configuration content.

    Merged context chunks often blend both (a class definition beside its tables), so a
    mere marker sighting is not enough — "Traffic Class" tables say "Class" too. A chunk
    counts as model-structure only when UML markers dominate the configuration markers
    at least two-to-one AND it carries no mapping-table furniture (ECUC/mapping rules),
    which always means the chunk configures rather than defines.
    """
    text = (chunk.get("section_title", "") + "\n" + chunk.get("normalized_text", ""))
    model = sum(len(re.findall(p, text)) for p in MODEL_PATTERNS)
    config = sum(text.count(m) for m in CONFIG_MARKERS)
    if model < 4 or model < 2 * config:
        return False
    return "ECUC-" not in text and "Mapping Rule" not in text


def order_evidence(evidence: list[dict]) -> list[dict]:
    """Stable partition: configuration evidence first, M2 model-structure last.

    Relevance order is kept inside each group; only the groups move. Applied AFTER the
    top-k cut, so the retrieved SET is unchanged — only the presentation order (and
    hence the [E#] numbering the answer follows) changes. The answer then flows
    system template -> configuration and grounds out in the model, instead of
    leading with what an element IS.
    """
    config = [c for c in evidence if not is_model_structure(c)]
    model = [c for c in evidence if is_model_structure(c)]
    return config + model


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
            # The parent itself may also be a ranked candidate (context chunks are
            # retrieved too). Without this, the same chunk appears twice — once as
            # the merge, once as itself — and wastes evidence slots.
            used.add(pid)
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
