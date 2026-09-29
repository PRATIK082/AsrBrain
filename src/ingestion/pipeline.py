"""Ingestion entry point: PDF discovery → hash → parse (adapter) → chunk → canonical SQLite.

v2 additive: `tables` + `figures` stores (multimodal evidence). Text chunk IDs unchanged.
Rollback: RAG_PIPELINE_VERSION=v1 ignores the new tables at retrieval.
"""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
from .pdf_extract import discover_pdfs, sha256_file, normalize_page_text, extract_signals
from .parsers import get_parser, parser_quality_report
from .metadata import detect_release_platform, infer_module
from .chunking import build_chunks

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents(document_id TEXT PRIMARY KEY, source_pdf TEXT, sha256 TEXT,
 title TEXT, autosar_release TEXT, platform TEXT, module TEXT, document_type TEXT, page_count INT, quality REAL);
CREATE TABLE IF NOT EXISTS chunks(chunk_id TEXT PRIMARY KEY, document_id TEXT, source_pdf TEXT, sha256 TEXT,
 page_start INT, page_end INT, pdf_page_index INT, autosar_release TEXT, platform TEXT, module TEXT,
 document_type TEXT, section_number TEXT, section_title TEXT, requirement_ids TEXT, api_names TEXT,
 ecu_parameters TEXT, parent_chunk_id TEXT, chunk_kind TEXT, text TEXT, normalized_text TEXT);
CREATE TABLE IF NOT EXISTS tables(evidence_id TEXT PRIMARY KEY, document_id TEXT, source_pdf TEXT,
 page INT, caption TEXT, rows_json TEXT, autosar_release TEXT, platform TEXT, module TEXT, parser TEXT);
CREATE TABLE IF NOT EXISTS figures(evidence_id TEXT PRIMARY KEY, document_id TEXT, source_pdf TEXT,
 page INT, kind TEXT, number TEXT, caption TEXT, autosar_release TEXT, platform TEXT, module TEXT,
 parser TEXT, is_inferred INT DEFAULT 0);
"""


def run(pdf_dir: str, out: str, module_hint: str = "", parser: str = "auto") -> dict:
    os.makedirs(out, exist_ok=True)
    db_path = os.path.join(out, "canonical.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    adapter = get_parser(parser)
    reports = []
    for pdf in discover_pdfs(pdf_dir):
        sha = sha256_file(pdf)
        document_id = "doc-" + sha[:12]
        try:
            parsed = adapter.parse(pdf)
            extractor = {"extractor": parsed[0].parser if parsed else adapter.name}
            pages = parsed
        except Exception:
            from .pdf_extract import extract_pages
            pages, extractor = extract_pages(pdf)
        for p in pages:
            p.text = normalize_page_text(p.text)
        full = "\n".join(p.text for p in pages)
        release, platform, doctype = detect_release_platform(full, os.path.basename(pdf))
        module = module_hint or infer_module(full)
        sig = extract_signals(full)
        qr = parser_quality_report(pages, pdf, sha)
        qr.update({**extractor, "release": release, "platform": platform, "document_type": doctype,
                   "requirements_detected": len(sig["requirement_ids"])})
        reports.append(qr)
        with open(os.path.join(out, document_id + ".quality.json"), "w") as f:
            json.dump(qr, f, indent=2)
        conn.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (document_id, pdf, sha, os.path.basename(pdf), release, platform,
                      module, doctype, len(pages), qr["quality_score"]))
        chunks = build_chunks(document_id, pdf, sha, release, platform, module, doctype, pages)
        for c in chunks:
            conn.execute("INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (c.chunk_id, c.document_id, c.source_pdf, c.source_sha256, c.page_start,
                          c.page_end, c.pdf_page_index, c.autosar_release, c.platform, c.module,
                          c.document_type, c.section_number, c.section_title,
                          json.dumps(c.requirement_ids), json.dumps(c.api_names),
                          json.dumps(c.ecu_parameters), c.parent_chunk_id, c.chunk_kind,
                          c.text, c.normalized_text))
        for p in pages:
            for t, tab in enumerate(getattr(p, "tables", []) or []):
                eid = f"tbl-{document_id}-{p.index}-{t}"
                conn.execute("INSERT OR REPLACE INTO tables VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (eid, document_id, pdf, p.index + 1, tab.get("caption", ""),
                              json.dumps(tab.get("rows", [])), release, platform, module,
                              getattr(p, "parser", "")))
            for f, fig in enumerate(getattr(p, "figures", []) or []):
                eid = f"fig-{document_id}-{p.index}-{f}"
                conn.execute("INSERT OR REPLACE INTO figures VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                             (eid, document_id, pdf, p.index + 1, fig.get("kind", "figure"),
                              fig.get("number", ""), fig.get("caption", ""), release, platform,
                              module, getattr(p, "parser", ""), 0))
        conn.commit()
    conn.close()
    with open(os.path.join(out, "ingestion_report.json"), "w") as f:
        json.dump(reports, f, indent=2)
    return {"db": db_path, "documents": len(reports)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", default="pdf")
    ap.add_argument("--out", default="data/canonical")
    ap.add_argument("--module", default="")
    args = ap.parse_args()
    print(json.dumps(run(args.pdf_dir, args.out, args.module), indent=2))


if __name__ == "__main__":
    main()
