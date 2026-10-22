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
from .migrations import migrate, new_run, close_run, content_hash

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
    import os as _os
    os.makedirs(out, exist_ok=True)
    db_path = os.path.join(out, "canonical.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)  # M2: idempotent, no-op once applied
    snapshot_id = new_run(
        conn,
        pipeline_version=_os.environ.get("RAG_PIPELINE_VERSION",
                                         _os.environ.get("ASRBRAIN_PIPELINE_VERSION", "v2")),
        parser_name=get_parser(parser).name if parser != "auto" else "auto",
        source_fingerprint=pdf_dir)
    adapter = get_parser(parser)
    reports = []
    try:
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
            # M4: version-link instead of silent overwrite. Same file (same sha) re-ingested
            # keeps its stable id; a changed file gets a new id that supersedes the old row.
            prior = conn.execute("SELECT document_id, sha256 FROM documents WHERE source_pdf=? "
                                 "ORDER BY rowid", (pdf,)).fetchall()
            supersedes = next((d for d, s in prior if d != document_id), None)
            conn.execute(
                "INSERT OR REPLACE INTO documents(document_id, source_pdf, sha256, title,"
                " autosar_release, platform, module, document_type, page_count, quality,"
                " snapshot_id, content_hash, supersedes_doc_id, created_by, confidence)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (document_id, pdf, sha, os.path.basename(pdf), release, platform,
                 module, doctype, len(pages), qr["quality_score"],
                 snapshot_id, sha, supersedes, "parser", qr["quality_score"]))
            chunks = build_chunks(document_id, pdf, sha, release, platform, module, doctype, pages)
            for c in chunks:
                conn.execute(
                    "INSERT OR REPLACE INTO chunks(chunk_id, document_id, source_pdf, sha256,"
                    " page_start, page_end, pdf_page_index, autosar_release, platform, module,"
                    " document_type, section_number, section_title, requirement_ids, api_names,"
                    " ecu_parameters, parent_chunk_id, chunk_kind, text, normalized_text,"
                    " snapshot_id, content_hash, created_by, confidence)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (c.chunk_id, c.document_id, c.source_pdf, c.source_sha256, c.page_start,
                     c.page_end, c.pdf_page_index, c.autosar_release, c.platform, c.module,
                     c.document_type, c.section_number, c.section_title,
                     json.dumps(c.requirement_ids), json.dumps(c.api_names),
                     json.dumps(c.ecu_parameters), c.parent_chunk_id, c.chunk_kind,
                     c.text, c.normalized_text,
                     snapshot_id, content_hash(c.normalized_text), "parser",
                     qr["quality_score"]))
            # first atomic chunk per page, so sidecars join back to text (M4)
            page_chunk: dict[int, str] = {}
            for c in chunks:
                if c.chunk_kind == "atomic" and c.pdf_page_index not in page_chunk:
                    page_chunk[c.pdf_page_index] = c.chunk_id
            for p in pages:
                for t, tab in enumerate(getattr(p, "tables", []) or []):
                    eid = f"tbl-{document_id}-{p.index}-{t}"
                    conn.execute(
                        "INSERT OR REPLACE INTO tables(evidence_id, document_id, source_pdf,"
                        " page, caption, rows_json, autosar_release, platform, module, parser,"
                        " chunk_id, snapshot_id, content_hash, created_by, confidence)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (eid, document_id, pdf, p.index + 1, tab.get("caption", ""),
                         json.dumps(tab.get("rows", [])), release, platform, module,
                         getattr(p, "parser", ""), page_chunk.get(p.index),
                         snapshot_id, content_hash((tab.get("caption", "") or "")
                                                   + json.dumps(tab.get("rows", []))),
                         "parser", qr["quality_score"]))
                for f, fig in enumerate(getattr(p, "figures", []) or []):
                    eid = f"fig-{document_id}-{p.index}-{f}"
                    conn.execute(
                        "INSERT OR REPLACE INTO figures(evidence_id, document_id, source_pdf,"
                        " page, kind, number, caption, autosar_release, platform, module,"
                        " parser, is_inferred, chunk_id, snapshot_id, content_hash,"
                        " created_by, confidence)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (eid, document_id, pdf, p.index + 1, fig.get("kind", "figure"),
                         fig.get("number", ""), fig.get("caption", ""), release, platform,
                         module, getattr(p, "parser", ""), 0, page_chunk.get(p.index),
                         snapshot_id, content_hash((fig.get("caption", "") or "")
                                                   + (fig.get("kind", "") or "")
                                                   + (fig.get("number", "") or "")),
                         "parser", qr["quality_score"]))
            conn.commit()
    finally:
        close_run(conn, snapshot_id)
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
