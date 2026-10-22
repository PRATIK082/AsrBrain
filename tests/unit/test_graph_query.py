"""Trace query path: satisfies / references / neighborhood over a fixture store."""
import sqlite3

from src.graph.build import build_spec, persist
from src.graph.query import neighbors, trace_question


def _db(tmp_path):
    from src.ingestion.migrations import migrate
    db = str(tmp_path / "g.db")
    conn = sqlite3.connect(db)
    migrate(conn)
    chunks = [
        {"chunk_id": "c1", "document_id": "d1", "source_pdf": "f.pdf",
         "page_start": 1, "autosar_release": "R24-11", "platform": "Foundation",
         "module": "", "chunk_kind": "atomic", "normalized_text":
         "CanIf_Init implements SWS_CANIF_00072 here.",
         "requirement_ids": ["SWS_CANIF_00072"], "api_names": ["CanIf_Init"],
         "ecu_parameters": []},
        {"chunk_id": "c2", "document_id": "d1", "source_pdf": "f.pdf",
         "page_start": 2, "autosar_release": "R24-11", "platform": "Foundation",
         "module": "", "chunk_kind": "atomic", "normalized_text":
         "Upstream requirements of SWS_CANIF_00072: SWS_CANIF_00073.",
         "requirement_ids": ["SWS_CANIF_00072", "SWS_CANIF_00073"],
         "api_names": [], "ecu_parameters": []},
    ]
    docs = [{"document_id": "d1", "source_pdf": "f.pdf", "title": "SWS_CanIf.pdf",
             "autosar_release": "R24-11"}]
    nodes, edges, links = build_spec(chunks, docs, "run-t")
    persist(conn, nodes, edges, links, "run-t")
    conn.close()
    return db


def test_satisfies_question(tmp_path):
    out = trace_question(_db(tmp_path), "Which APIs satisfy SWS_CANIF_00072?")
    assert "api:CanIf_Init" in out["node_ids"]
    assert out["chunk_ids"] == ["c1"]
    assert out["provenance"] and out["provenance"][0]["page"] == 1


def test_references_question(tmp_path):
    out = trace_question(_db(tmp_path),
                         "Which requirements does SWS_CANIF_00072 reference?")
    assert "requirement:SWS_CANIF_00073" in out["node_ids"]
    assert out["chunk_ids"] == ["c2"]


def test_connects_to_neighborhood(tmp_path):
    out = trace_question(_db(tmp_path), "What connects to CanIf_Init?")
    assert "requirement:SWS_CANIF_00072" in out["node_ids"]


def test_unknown_identifier_returns_empty(tmp_path):
    out = trace_question(_db(tmp_path), "Which APIs satisfy SWS_NOPE_00001?")
    assert out["node_ids"] == ["requirement:SWS_NOPE_00001"]
    assert out["edge_ids"] == [] and out["chunk_ids"] == []


def test_neighbors_depth(tmp_path):
    nb = neighbors(_db(tmp_path), "api:CanIf_Init", depth=1)
    assert "requirement:SWS_CANIF_00072" in {n["node_id"] for n in nb["nodes"]}
