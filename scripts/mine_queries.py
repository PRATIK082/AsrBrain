"""Query flywheel miner (Phase 4, slice 1).

``clusters`` groups logged user phrasings by content-token Jaccard similarity so repeated
question forms (including paraphrases the hand-written aliases never saw) surface
as one cluster, ranked by frequency x failure weight (ABSTAIN / down-vote first).
Jaccard is corpus-size independent; deep paraphrase recall arrives with slice-2 embeddings.

``promote`` appends human-labelled clusters to the golden set and deliberately
re-freezes the hold-out manifest. Split assignment stays hash-based, so a promoted
item may land in train (improves retrieval) or hold-out (judges it, never tune on it).

Usage:
    python scripts/mine_queries.py clusters [--db data/canonical/chat.db] [--threshold 0.55]
    python scripts/mine_queries.py promote --labels labels.json [--golden ...] [--split ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.chat.store import ChatStore  # noqa: E402
from src.evaluation.splits import save_split, split_ids  # noqa: E402

CANDIDATES_PATH = os.path.join("data", "benchmarks", "mining_candidates.jsonl")

FAILURE_WEIGHT = {"ABSTAIN": 3.0, "DOWN": 3.0, "PARTIAL": 2.0, "CLARIFY": 1.0, "ANSWERED": 1.0}


def _tokens(text: str) -> list[str]:
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in text or "").split() if t]


# Minimal English function-word set (generic NLP practice, not domain rules):
# lets content words decide similarity, independent of log size.
STOP = {"a", "an", "the", "is", "are", "was", "were", "be", "what", "whats", "which",
        "who", "how", "why", "when", "where", "do", "does", "did", "could",
        "would", "should", "give", "me", "need", "want", "please", "with", "for",
        "from", "that", "this", "and", "all", "any", "its", "had", "has", "have",
        "will", "shall", "may", "might", "must", "been", "being", "such", "than",
        "then", "them", "they", "their", "there", "these", "those", "through",
        "under", "upon", "into", "over", "after", "before", "between", "both",
        "each", "other", "some", "more", "most", "many", "much", "very", "just",
        "about", "detail", "detailed", "tell", "explain", "describe", "show", "list",
        "example", "information", "info", "i", "of", "on", "in", "to", "by", "as",
        "at", "or", "an"}


def _content(text: str) -> set[str]:
    toks = [t for t in _tokens(text) if t not in STOP]
    return set(toks) or set(_tokens(text))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster_queries(queries: list[str], threshold: float = 0.3) -> list[list[int]]:
    """Union-find clustering on content-token Jaccard >= threshold."""
    feats = [_content(q) for q in queries]
    parent = list(range(len(queries)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(queries)):
        for j in range(i + 1, len(queries)):
            if _jaccard(feats[i], feats[j]) >= threshold:
                union(i, j)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(queries)):
        groups[find(i)].append(i)
    return sorted(groups.values(), key=lambda g: (-len(g), g[0]))


def load_logged(db_path: str = "data/canonical/chat.db") -> list[dict]:
    """Merge query_log rows with down-vote mining candidates (dedup by text)."""
    rows = []
    if os.path.exists(db_path):
        try:
            rows = ChatStore(db_path).list_query_log()
        except Exception:
            rows = []
    seen = {r.get("query", "") for r in rows}
    if os.path.exists(CANDIDATES_PATH):
        with open(CANDIDATES_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    cand = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if cand.get("query") and cand["query"] not in seen:
                    seen.add(cand["query"])
                    rows.append({"query": cand["query"], "outcome": "DOWN",
                                 "conversation_id": cand.get("conversation_id", ""),
                                 "evidence_ids": [], "intent": ""})
    return rows


def rank_clusters(rows: list[dict], threshold: float = 0.3) -> list[dict]:
    queries = [r.get("query", "") for r in rows]
    ranked = []
    for members in cluster_queries(queries, threshold):
        sub = [rows[i] for i in members]
        weight = sum(FAILURE_WEIGHT.get(r.get("outcome", "ANSWERED"), 1.0) for r in sub)
        outcomes = Counter(r.get("outcome", "?") for r in sub)
        intents = Counter(r.get("intent", "") for r in sub if r.get("intent"))
        ranked.append({"size": len(sub), "score": round(len(sub) * weight, 2),
                       "outcomes": dict(outcomes),
                       "top_intent": intents.most_common(1)[0][0] if intents else "",
                       "queries": [r.get("query", "") for r in sub]})
    ranked.sort(key=lambda c: (-c["score"], -c["size"]))
    return ranked


def cmd_clusters(args: argparse.Namespace) -> int:
    rows = load_logged(args.db)
    if not rows:
        print("no logged queries yet — ask questions via API/chat first (ASRBRAIN_QUERY_LOG=1).")
        return 0
    ranked = rank_clusters(rows, args.threshold)
    shown = 0
    for c in ranked:
        if c["size"] < args.min_size and c["score"] < 3.0:
            continue
        shown += 1
        print(f"--- cluster score={c['score']} size={c['size']} outcomes={c['outcomes']} "
              f"intent={c['top_intent'] or '?'}")
        for q in c["queries"][:8]:
            print(f"    - {q[:140]}")
    print(f"{len(rows)} logged queries in {len(ranked)} clusters ({shown} shown).")
    return 0


def _next_mined_id(existing: set[str]) -> str:
    n = 1
    while f"q-M-{n:04d}" in existing:
        n += 1
    return f"q-M-{n:04d}"


def promote_labels(labels: list[dict], golden_path: str, split_path: str) -> dict:
    """Append labelled items to the golden set and deliberately re-freeze the split."""
    items: list[dict] = []
    with open(golden_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    existing = {i.get("query_id", "") for i in items}
    added = []
    for lab in labels:
        qid = lab.get("query_id") or _next_mined_id(existing | {a["query_id"] for a in added})
        item = {"query_id": qid,
                "question": lab["question"],
                "category": lab.get("category", "mined"),
                "difficulty": lab.get("difficulty", "medium"),
                "answerable": lab.get("answerable", True),
                "expected_answer_type": lab.get("expected_answer_type", "grounded_answer"),
                "gold_answer": lab.get("gold_answer", ""),
                "gold_claims": lab.get("gold_claims", []),
                "gold_evidence_ids": lab.get("gold_evidence_ids", []),
                "gold_pages": lab.get("gold_pages", []),
                "gold_requirement_ids": lab.get("gold_requirement_ids", []),
                "gold_sections": lab.get("gold_sections", []),
                "gold_source_documents": lab.get("gold_source_documents", []),
                "required_modules": lab.get("required_modules", []),
                "required_platforms": lab.get("required_platforms", []),
                "required_versions": lab.get("required_versions", []),
                "source": "mined",
                "tags": lab.get("tags", ["mined"] + (["paraphrase"] if lab.get("paraphrase_of") else []))}
        if lab.get("paraphrase_of"):
            item["paraphrase_of"] = lab["paraphrase_of"]
        if lab.get("notes"):
            item["notes"] = lab["notes"]
        added.append(item)
    with open(golden_path, "a", encoding="utf-8", newline="\n") as fh:
        for item in added:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    manifest = save_split(split_path, items + added, golden_path)
    assignment = split_ids(added)
    return {"added": [a["query_id"] for a in added], "train": assignment["train"],
            "holdout": assignment["holdout"],
            "counts": manifest["counts"],
            "warning": ("holdout items judge, never tune on them" if assignment["holdout"] else "")}


def cmd_promote(args: argparse.Namespace) -> int:
    with open(args.labels, encoding="utf-8") as fh:
        labels = json.load(fh)
    if isinstance(labels, dict):
        labels = labels.get("items", [])
    res = promote_labels(labels, args.golden, args.split)
    print(f"promoted {len(res['added'])} items: train={res['train']} holdout={res['holdout']}")
    if res["warning"]:
        print(f"WARNING: {res['warning']}")
    print(f"split re-frozen: {res['counts']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mine logged queries into golden training data.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("clusters", help="rank paraphrase clusters of logged queries")
    c.add_argument("--db", default="data/canonical/chat.db")
    c.add_argument("--threshold", type=float, default=0.3)
    c.add_argument("--min-size", type=int, default=2)
    c.set_defaults(fn=cmd_clusters)
    p = sub.add_parser("promote", help="append labelled items to golden set + re-freeze split")
    p.add_argument("--labels", required=True, help="JSON array (or {items:[...]}) of labelled items")
    p.add_argument("--golden", default="data/benchmarks/autosar_golden_v2.jsonl")
    p.add_argument("--split", default="data/benchmarks/holdout_v2.json")
    p.set_defaults(fn=cmd_promote)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
