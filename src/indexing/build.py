"""Index builder entry point."""
from __future__ import annotations
import argparse
from .hybrid import HybridIndex, load_chunks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical", default="data/canonical/canonical.db")
    ap.add_argument("--out", default="data/indexes/hybrid")
    args = ap.parse_args()
    chunks = load_chunks(args.canonical)
    idx = HybridIndex()
    idx.build(chunks)
    idx.save(args.out)
    print(f"indexed {len(chunks)} chunks -> {args.out}")


if __name__ == "__main__":
    main()
