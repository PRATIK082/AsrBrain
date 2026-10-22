"""Deterministic fixture corpus for CI.

The real corpus is 25 MB of paid AUTOSAR PDFs and is deliberately not in the repository. The
CI gate therefore needs a corpus it can build from source in seconds. This module
materialises a small, *synthetic* AUTOSAR-shaped corpus with the same schema, the same signals
(requirement ids, API names, ECUC parameters, section titles) and the same table and figure
records, so the harness exercises the real code paths end to end.

Nothing here is derived from a real standard: the identifiers, module names and sentences are
invented. Only ingestion tooling and synthetic data ship in the repository — never the
paid standard documents themselves.

    python -m src.evaluation.fixture --out data/canonical/fixture.db
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  document_id TEXT PRIMARY KEY, source_pdf TEXT, sha256 TEXT, title TEXT,
  autosar_release TEXT, platform TEXT, module TEXT, document_type TEXT,
  page_count INTEGER, quality REAL);
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY, document_id TEXT, source_pdf TEXT, source_sha256 TEXT,
  page_start INTEGER, page_end INTEGER, pdf_page_index INTEGER, autosar_release TEXT,
  platform TEXT, module TEXT, document_type TEXT, section_number TEXT, section_title TEXT,
  requirement_ids TEXT, api_names TEXT, ecu_parameters TEXT, parent_chunk_id TEXT,
  chunk_kind TEXT, text TEXT, normalized_text TEXT);
CREATE TABLE IF NOT EXISTS tables (
  evidence_id TEXT PRIMARY KEY, document_id TEXT, source_pdf TEXT, page INTEGER,
  caption TEXT, rows_json TEXT, autosar_release TEXT, platform TEXT, module TEXT, parser TEXT);
CREATE TABLE IF NOT EXISTS figures (
  evidence_id TEXT PRIMARY KEY, document_id TEXT, source_pdf TEXT, page INTEGER, kind TEXT,
  number TEXT, caption TEXT, parser TEXT, is_inferred INTEGER);
"""

#: (document_id, source, release, platform, module, doc type, pages)
DOCUMENTS = [
    ("doc-fixture-sws", "fixture/SWS_FixtureModule.pdf", "R24-11", "Classic",
     "FixtureModule", "SWS", 24),
    ("doc-fixture-prs", "fixture/PRS_FixtureService.pdf", "R22-11", "Foundation",
     "FixtureService", "PRS", 18),
]

SECTIONS = ["Initialisation", "State Machine", "Error Handling", "Configuration",
            "Timing Constraints", "Diagnostics", "Deployment", "API Contract"]
APIS = ["FixtureModule_Init", "FixtureModule_SetMode", "FixtureModule_GetStatus",
        "FixtureModule_RegisterCallback", "FixtureService_Discover", "FixtureService_Send",
        "FixtureService_Subscribe", "FixtureService_Unsubscribe"]
PARAMS = ["FixtureModuleClockRef", "FixtureModuleQueueSize", "FixtureServiceTimeoutMs",
          "FixtureServiceMaxRetries"]
TABLES = ["FixtureModule Configuration Parameters", "Error Codes",
          "Fixture Service Message Layout", "Timing Constraints"]
FIGURES = ["FixtureModule architecture", "FixtureService message flow", "State machine"]


def _chunk_text(section: str, index: int, req_id: str, api: str, doc_type: str) -> str:
    return (
        f"{req_id} The {section} of the fixture module shall call {api} exactly once per "
        f"cycle. The implementation shall report E_NOT_OK when the {doc_type} precondition is "
        f"violated. Timeout handling follows the {section.lower()} rule with a 500 ms budget "
        f"and the error code 0x{index:02X} shall be reported to the caller. [Note: synthetic "
        f"fixture text for the evaluation harness.]"
    )


def build(out_path: str) -> dict:
    """Materialise the fixture corpus. Returns a small summary."""
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(out_path):
        os.remove(out_path)
    conn = sqlite3.connect(out_path)
    conn.executescript(SCHEMA)

    chunk_rows = []
    doc_rows = []
    table_rows = []
    figure_rows = []
    counter = 0

    for doc_id, source, release, platform, module, doc_type, pages in DOCUMENTS:
        sha = ("f" * 64)[:12] + doc_id
        doc_rows.append((doc_id, source, sha, f"Fixture {doc_type}", release, platform,
                         module, doc_type, pages, 1.0))
        per_doc = 40 if doc_type == "SWS" else 28
        for i in range(per_doc):
            counter += 1
            section = SECTIONS[i % len(SECTIONS)]
            req_id = f"{doc_type}_FIXTURE_{counter:05d}"
            api = APIS[i % len(APIS)]
            param = PARAMS[i % len(PARAMS)]
            page = 1 + (i % pages)
            has_param = (i % 4 == 0)
            text = _chunk_text(section, i, req_id, api, doc_type)
            chunk_id = f"chunk-fixture-{counter:06d}"
            chunk_rows.append((
                chunk_id, doc_id, source, sha, page, page, page - 1, release, platform, module,
                doc_type, f"{1 + i // len(SECTIONS)}.{1 + i % len(SECTIONS)}", section,
                json.dumps([req_id]),
                json.dumps([api]),
                json.dumps([param]) if has_param else "[]",
                None, "atomic", text, text.lower()))
        for t in range(12):
            page = 1 + t * 2
            caption = f"{TABLES[t % len(TABLES)]} (part {t + 1})"
            table_rows.append((f"tbl-{doc_id}-{page}-{t}", doc_id, source, page, caption,
                               "[]", release, platform, module, "fixture"))
        for f in range(10):
            page = 2 + f * 2
            caption = f"{FIGURES[f % len(FIGURES)]} (view {f + 1})"
            figure_rows.append((f"fig-{doc_id}-{page}-{f}", doc_id, source, page, "figure",
                                f"{1 + f}", caption, "fixture", 0))

    conn.executemany("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)", doc_rows)
    conn.executemany("INSERT INTO chunks VALUES (" + ",".join(["?"] * 20) + ")", chunk_rows)
    conn.executemany("INSERT INTO tables VALUES (?,?,?,?,?,?,?,?,?,?)", table_rows)
    conn.executemany("INSERT INTO figures VALUES (?,?,?,?,?,?,?,?,?)", figure_rows)
    conn.commit()
    conn.close()
    return {
        "path": out_path,
        "documents": len(doc_rows),
        "chunks": len(chunk_rows),
        "tables": len(table_rows),
        "figures": len(figure_rows),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the synthetic fixture corpus for CI")
    ap.add_argument("--out", default="data/canonical/fixture.db")
    args = ap.parse_args()
    print(json.dumps(build(args.out), indent=2))


if __name__ == "__main__":
    main()
