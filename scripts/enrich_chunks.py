"""Optional offline enrichment of canonical chunks with LLM-derived context headers.

Usage (opt-in, requires Ollama):
    python scripts/enrich_chunks.py --limit 50

Writes enriched fields into a sidecar JSONL (data/benchmarks/chunk_enrichment.jsonl)
rather than mutating canonical.db, so it is safe and reversible.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.config.settings import settings
from src.ingestion.enrichment import enrich_chunk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", default="data/benchmarks/chunk_enrichment.jsonl")
    args = ap.parse_args()

    import sqlite3
    conn = sqlite3.connect(settings.canonical_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT chunk_id, normalized_text FROM chunks LIMIT ?", (args.limit,)).fetchall()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in rows:
            env = enrich_chunk(r["normalized_text"] or "")
            rec = {"chunk_id": r["chunk_id"], "enrichment": env}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(r["chunk_id"], env.get("Layer"), env.get("Target_Modules"))
    print("wrote", args.out)


if __name__ == "__main__":
    main()