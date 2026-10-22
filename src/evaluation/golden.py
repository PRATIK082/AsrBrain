"""Golden-set schema, validation and coverage accounting.

A golden item is a JSON object with one line per item. The schema is a superset of the original
v1 seed schema in :mod:`src.evaluation.datasets` so that old files still load.

Required by §9: question, gold answer, gold evidence ids, category, release/version, difficulty
and an ``needs_expert_review`` flag. §9 also requires the corpus mix to be auditable, so
:func:`coverage_report` computes the realised mix rather than trusting the author.
"""
from __future__ import annotations

import hashlib
import json
import os
import random

#: Fields every golden item must carry.
REQUIRED_FIELDS = [
    "query_id", "question", "category", "difficulty", "answerable",
    "gold_evidence_ids", "gold_answer", "needs_expert_review",
]

#: Fields carried by v1 items only (kept for backwards compatibility with the seed file).
LEGACY_FIELDS = [
    "expected_answer_type", "required_versions", "required_platforms", "required_modules",
    "gold_source_documents", "gold_pages", "gold_sections", "gold_requirement_ids", "gold_claims",
]

#: The category taxonomy used by the coverage mix in §9.
CATEGORIES = [
    "definition",
    "api_lookup",
    "requirement_lookup",
    "configuration",
    "runtime_behaviour",
    "table_lookup",
    "diagram_lookup",
    "release_comparison",
    "multi_hop",
    "code_explanation",
    "traceability",
    "impact_analysis",
    "test_analysis",
    "unanswerable",
    "adversarial",
]

#: §9 coverage requirements, expressed as minimum shares of the whole set.
COVERAGE_TARGETS = {
    "multi_hop": 0.30,
    "unanswerable": 0.15,
    "table_lookup": 0.03,
    "diagram_lookup": 0.03,
    "release_comparison": 0.03,
    "code_explanation": 0.03,
    "traceability": 0.03,
    "impact_analysis": 0.03,
    "test_analysis": 0.03,
}

DIFFICULTIES = ["easy", "medium", "hard"]


def new_item(query_id: str, question: str, category: str, **kw) -> dict:
    """Create a golden item with every field present, so no downstream code needs .get()."""
    item = {
        "query_id": query_id,
        "question": question,
        "category": category,
        "difficulty": kw.pop("difficulty", "medium"),
        "answerable": bool(kw.pop("answerable", True)),
        "gold_answer": kw.pop("gold_answer", ""),
        "gold_evidence_ids": list(kw.pop("gold_evidence_ids", [])),
        "needs_expert_review": bool(kw.pop("needs_expert_review", True)),
        "expected_answer_type": kw.pop("expected_answer_type", "exact_lookup"),
        "required_versions": list(kw.pop("required_versions", [])),
        "required_platforms": list(kw.pop("required_platforms", [])),
        "required_modules": list(kw.pop("required_modules", [])),
        "gold_source_documents": list(kw.pop("gold_source_documents", [])),
        "gold_pages": list(kw.pop("gold_pages", [])),
        "gold_sections": list(kw.pop("gold_sections", [])),
        "gold_requirement_ids": list(kw.pop("gold_requirement_ids", [])),
        "gold_claims": list(kw.pop("gold_claims", [])),
        "tags": list(kw.pop("tags", [])),
        "source": kw.pop("source", "generated"),
        "notes": kw.pop("notes", ""),
    }
    if kw:
        raise TypeError(f"unknown golden-item fields: {sorted(kw)}")
    return item


def load_golden(path: str) -> list[dict]:
    """Read a JSONL golden set."""
    items: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} is not valid JSON: {exc}") from exc
    return items


def write_golden(path: str, items: list[dict]) -> int:
    """Write a JSONL golden set, creating the directory if needed."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    return len(items)


def file_sha256(path: str) -> str:
    """SHA-256 of a file, used to freeze the golden set and the hold-out split."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def validate(items: list[dict]) -> list[str]:
    """Return a list of problems with the golden set. Empty list means valid."""
    problems: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(items):
        qid = item.get("query_id") or f"<index {i}>"
        for field in REQUIRED_FIELDS:
            if field not in item:
                problems.append(f"{qid}: missing field '{field}'")
        if item.get("query_id") in seen:
            problems.append(f"{qid}: duplicate query_id")
        seen.add(item.get("query_id"))
        if not (item.get("question") or "").strip():
            problems.append(f"{qid}: empty question")
        cat = item.get("category")
        if cat and cat not in CATEGORIES:
            problems.append(f"{qid}: unknown category '{cat}'")
        diff = item.get("difficulty")
        if diff and diff not in DIFFICULTIES:
            problems.append(f"{qid}: unknown difficulty '{diff}'")
        if item.get("answerable"):
            if not item.get("gold_evidence_ids"):
                problems.append(f"{qid}: answerable item without gold_evidence_ids")
            if not (item.get("gold_answer") or "").strip():
                problems.append(f"{qid}: answerable item without gold_answer")
        else:
            if item.get("gold_evidence_ids"):
                problems.append(f"{qid}: unanswerable item must not carry gold_evidence_ids")
    return problems


def coverage_report(items: list[dict]) -> dict:
    """Realised coverage mix versus the §9 targets."""
    n = len(items)
    by_cat: dict[str, int] = {}
    for item in items:
        cat = item.get("category", "unknown")
        by_cat[cat] = by_cat.get(cat, 0) + 1
    # A slice may be reached either through the category or through an explicit tag, so both
    # are counted. Without this, an item tagged "unanswerable" would be invisible to the
    # "unanswerable" slice even though it is exactly that.
    tagged: dict[str, int] = dict(by_cat)
    for item in items:
        for tag in item.get("tags", []) or []:
            tagged[tag] = tagged.get(tag, 0) + 1
    mix = {cat: round(count / n, 4) for cat, count in sorted(by_cat.items())} if n else {}
    gaps = []
    for tag, target in COVERAGE_TARGETS.items():
        got = tagged.get(tag, 0) / n if n else 0.0
        if got < target:
            gaps.append({"slice": tag, "target": target, "actual": round(got, 4), "shortfall": n})
    return {
        "n": n,
        "by_category": by_cat,
        "mix": mix,
        "answerable": sum(1 for i in items if i.get("answerable")),
        "unanswerable": sum(1 for i in items if not i.get("answerable")),
        "needs_expert_review": sum(1 for i in items if i.get("needs_expert_review")),
        "difficulty": {d: sum(1 for i in items if i.get("difficulty") == d) for d in DIFFICULTIES},
        "coverage_gaps": gaps,
        "meets_coverage_targets": not gaps,
    }


def expert_review_sample(items: list[dict], size: int = 40, seed: int = 20261021) -> list[dict]:
    """Stratified sample for expert review: proportional per category, deterministic."""
    rng = random.Random(seed)
    by_cat: dict[str, list[dict]] = {}
    for item in items:
        by_cat.setdefault(item.get("category", "unknown"), []).append(item)
    cats = sorted(by_cat)
    if not cats:
        return []
    per = max(1, size // len(cats))
    picked: list[dict] = []
    for cat in cats:
        pool = sorted(by_cat[cat], key=lambda x: x.get("query_id", ""))
        picked.extend(rng.sample(pool, min(per, len(pool))))
    # top up from the largest pools if the stratified pass came short
    if len(picked) < size:
        remaining = [i for i in items if i not in picked]
        rng.shuffle(remaining)
        picked.extend(remaining[: size - len(picked)])
    return sorted(picked, key=lambda x: x.get("query_id", ""))[:size]
