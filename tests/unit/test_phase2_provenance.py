"""Regression tests for the provenance contract, migration reversibility and repairs."""
import os
import sqlite3

from src.ingestion import migrations as mig
from src.ingestion import project_sources as ps
from src.ingestion.chunking import build_chunks
from src.ingestion.parsers import ParsedPage
from src.ingestion.pdf_extract import extract_signals


def _fresh_db(tmp_path):
    db = str(tmp_path / "m.db")
    conn = sqlite3.connect(db)
    return db, conn


def test_migrate_fresh_db_reaches_current(tmp_path):
    _, conn = _fresh_db(tmp_path)
    assert mig.migrate(conn) == mig.CURRENT_VERSION
    assert mig.get_schema_version(conn) == mig.CURRENT_VERSION
    cols = {r[1] for r in conn.execute("PRAGMA table_info(chunks)").fetchall()}
    for c in ("snapshot_id", "content_hash", "created_by", "confidence",
              "char_start", "printed_page", "line_start"):
        assert c in cols
    conn.close()


def test_migrate_is_idempotent(tmp_path):
    _, conn = _fresh_db(tmp_path)
    assert mig.migrate(conn) == mig.CURRENT_VERSION
    assert mig.migrate(conn) == mig.CURRENT_VERSION  # second run is a no-op
    conn.close()


def test_backfill_tags_legacy_rows(tmp_path):
    _, conn = _fresh_db(tmp_path)
    mig.migrate(conn)
    conn.execute("INSERT INTO documents(document_id, source_pdf, sha256, title,"
                 " autosar_release, platform, module, document_type, page_count, quality)"
                 " VALUES (?,?,?,?,?,?,?,?,?,?)",
                 ("doc-x", "f.pdf", "sha", "t", "4.4.0", "Classic", "CanIf",
                  "SWS", 10, 0.9))
    conn.execute("INSERT INTO chunks(chunk_id, document_id, source_pdf, sha256,"
                 " page_start, page_end, pdf_page_index, autosar_release, platform,"
                 " module, document_type, section_number, section_title,"
                 " requirement_ids, api_names, ecu_parameters, parent_chunk_id,"
                 " chunk_kind, text, normalized_text)"
                 " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 ("c1", "doc-x", "f.pdf", "sha", 1, 1, 0, "4.4.0", "Classic",
                  "CanIf", "SWS", "1", "Title", "[]", "[]", "[]", "", "atomic",
                  "hello world text", "hello world text"))
    stats = mig.backfill(conn)
    assert stats["documents"] == 1 and stats["chunks"] == 1
    row = conn.execute("SELECT snapshot_id, content_hash, created_by, confidence "
                       "FROM chunks WHERE chunk_id='c1'").fetchone()
    assert row[0] == "run-legacy-baseline" and row[2] == "parser"
    assert row[1] == mig.content_hash("hello world text") and row[3] == 0.9
    # idempotent: second backfill touches nothing
    assert mig.backfill(conn)["chunks"] == 0
    conn.close()


def test_arxml_summary_lists_swc_and_ports():
    text = ("<?xml version=\"1.0\"?><AUTOSAR><AR-PACKAGES><AR-PACKAGE>"
            "<SHORT-NAME>Pkg</SHORT-NAME><ELEMENTS>"
            "<APPLICATION-SW-COMPONENT-TYPE><SHORT-NAME>BrakeCtrl</SHORT-NAME>"
            "<PORTS><P-PORT-PROTOTYPE><SHORT-NAME>P_BrakeCmd</SHORT-NAME></P-PORT-PROTOTYPE>"
            "</PORTS></APPLICATION-SW-COMPONENT-TYPE>"
            "</ELEMENTS></AR-PACKAGE></AR-PACKAGES></AUTOSAR>")
    s = ps._arxml_summary(text)
    assert "BrakeCtrl" in s and "P_BrakeCmd" in s  # was silently "" before Phase 2


def test_context_chunks_keep_ecu_parameters_and_full_id_sets():
    from src.ingestion.pdf_extract import PageText
    para = ("7.1 Title [SWS_CanIf_00001] [SWS_CanIf_00002] " + "word " * 300)
    pages = [PageText(0, para, len(para))]
    out = build_chunks("doc-t", "f.pdf", "sha", "4.4.0", "Classic", "CanIf", "SWS", pages)
    atomics = [c for c in out if c.chunk_kind == "atomic"]
    assert atomics and all(len(c.requirement_ids) >= 2 for c in atomics)  # no [:10] loss
    ctx = [c for c in out if c.chunk_kind == "context"]
    assert ctx and all(hasattr(c, "ecu_parameters") for c in ctx)


def test_bracket_requirement_families_detected():
    sig = extract_signals("see [SWS_Com_00001] and [constr_1234] and [SRS_BSW_00001]")
    assert "SWS_Com_00001" in sig["requirement_ids"]
    assert "constr_1234" in sig["requirement_ids"]
    assert "SRS_BSW_00001" in sig["requirement_ids"]


def test_docling_pages_are_null_not_page_one():
    pg = ParsedPage(0, "para one " * 30 + "\n\n" + "para two " * 30, 0)
    pg.page_unknown = True
    out = build_chunks("doc-d", "f.pdf", "sha", "", "", "", "SWS", [pg])
    assert out and all(c.page_start is None and c.pdf_page_index is None for c in out)


def test_citations_render_na_for_null_pages():
    from src.generation.citations import citation_block
    b = citation_block([{"chunk_id": "c", "source_pdf": "f", "page_start": None,
                         "page_end": None}])
    assert "n/a" in b and "None" not in b


def test_fingerprint_detects_content_change(tmp_path):
    from src.indexing.hybrid import db_fingerprint
    _, conn = _fresh_db(tmp_path)
    mig.migrate(conn)
    conn.execute("INSERT INTO chunks(chunk_id) VALUES ('a')")
    conn.commit()
    fp1 = db_fingerprint(str(tmp_path / "m.db"))
    conn.execute("UPDATE chunks SET chunk_id='b' WHERE chunk_id='a'")
    conn.commit()
    fp2 = db_fingerprint(str(tmp_path / "m.db"))
    assert fp1 != fp2 and fp1["count"] == fp2["count"] == 1  # same count, new hash
    conn.close()


def test_pipeline_version_prefers_rag_spelling(monkeypatch):
    import importlib
    monkeypatch.setenv("RAG_PIPELINE_VERSION", "v9")
    monkeypatch.delenv("ASRBRAIN_PIPELINE_VERSION", raising=False)
    import src.config.settings as s
    importlib.reload(s)
    assert s.Settings().pipeline_version == "v9"
    monkeypatch.delenv("RAG_PIPELINE_VERSION", raising=False)
    monkeypatch.setenv("ASRBRAIN_PIPELINE_VERSION", "v8")
    importlib.reload(s)
    assert s.Settings().pipeline_version == "v8"
    monkeypatch.delenv("ASRBRAIN_PIPELINE_VERSION", raising=False)
    importlib.reload(s)
    assert s.Settings().pipeline_version == "v2"
    assert os.environ.get("RAG_PIPELINE_VERSION", "v2") == "v2"


def test_migrate_v3_creates_graph_store(tmp_path):
    from src.ingestion import migrations as mig
    conn = sqlite3.connect(str(tmp_path / "g.db"))
    assert mig.migrate(conn) == 3
    assert mig.migrate(conn) == 3  # idempotent
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"graph_nodes", "graph_edges", "trace_links"} <= names
    for tbl, col in (("graph_nodes", "snapshot_id"), ("graph_edges", "is_inferred"),
                     ("trace_links", "evidence")):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()}
        assert col in cols
    conn.close()
