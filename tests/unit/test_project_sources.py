"""Project sources: local folder ingest with scoping + retrieval grounding."""
import json
import os
import sqlite3

from src.ingestion import project_sources as ps
from src.retrieval.metadata_filter import apply_filters
from src.schema.queries import QueryPlan

ARXML_SAMPLE = """<?xml version="1.0"?>
<AUTOSAR><AR-PACKAGES><AR-PACKAGE><SHORT-NAME>Pkg</SHORT-NAME><ELEMENTS>
<APPLICATION-SW-COMPONENT-TYPE><SHORT-NAME>BrakeCtrl</SHORT-NAME>
<PORTS><P-PORT-PROTOTYPE><SHORT-NAME>P_BrakeCmd</SHORT-NAME></P-PORT-PROTOTYPE>
<R-PORT-PROTOTYPE><SHORT-NAME>R_WheelSpeed</SHORT-NAME></R-PORT-PROTOTYPE></PORTS>
</APPLICATION-SW-COMPONENT-TYPE></ELEMENTS></AR-PACKAGE></AR-PACKAGES></AUTOSAR>
"""

C_SAMPLE = """#include "Rte_BrakeCtrl.h"
void BrakeCtrl_Main(void) { uint8 x = 0; (void)x; }
"""


def test_register_and_ingest_local_folder(tmp_path, monkeypatch):
    d = tmp_path / "ecu"
    d.mkdir()
    (d / "swc.arxml").write_text(ARXML_SAMPLE)
    (d / "brake.c").write_text(C_SAMPLE)
    reg = tmp_path / "sources.json"
    db = str(tmp_path / "canon.db")
    rec = ps.register_source("BrakeECU", str(d), kind="mixed",
                             scope_type="customer_project", scope_name="CustX-Brake",
                             registry=str(reg))
    assert rec["scope_type"] == "customer_project"
    res = ps.ingest_source(rec["source_id"], canonical_db=db, registry=str(reg))
    assert res["files"] == 2 and res["chunks"] >= 2
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    titles = [r[0] for r in conn.execute("SELECT section_title FROM chunks").fetchall()]
    conn.close()
    assert n == res["chunks"]
    assert any("CustX-Brake" in t for t in titles)
    assert os.path.exists(reg)


def test_bad_scope_rejected(tmp_path):
    try:
        ps.register_source("X", str(tmp_path), scope_type="nope",
                           registry=str(tmp_path / "s.json"))
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_project_chunks_survive_spec_filters():
    chunks = [
        {"chunk_id": "ps-abc", "module": "", "platform": "", "autosar_release": "",
         "document_type": "code", "normalized_text": "BrakeCtrl main"},
        {"chunk_id": "t1", "module": "CanIf", "platform": "Classic",
         "autosar_release": "4.4.0", "document_type": "text", "normalized_text": "CanIf spec"},
    ]
    plan = QueryPlan(original_query="q", intent="definition", releases=["4.4.0"], platforms=["Classic"],
                      modules=["CanIf"], release_mode="exact")
    out = apply_filters(chunks, plan)
    ids = {c["chunk_id"] for c in out}
    assert "ps-abc" in ids and "t1" in ids


def test_token_caps_file_and_settings():
    from src.config.settings import TOKEN_CAPS
    assert TOKEN_CAPS["concise"] > 0 and TOKEN_CAPS["detailed"] > TOKEN_CAPS["concise"]
    assert os.path.exists(os.path.join("config", "generation.yaml"))


def test_diagram_prompt_allows_project_evidence():
    from src.generation.prompts import build_prompt
    ev = [{"chunk_id": "ps-1", "source_pdf": "[customer:X] swc.arxml", "autosar_release": "",
           "platform": "", "module": "", "document_type": "arxml",
           "section_number": "", "section_title": "[customer:X] swc.arxml",
           "page_start": 0, "page_end": 0, "requirement_ids": [],
           "compressed": "SWC BrakeCtrl: P_BrakeCmd", "normalized_text": "SWC BrakeCtrl"}]
    p = build_prompt("draw the flow diagram of BrakeCtrl", ev)
    assert "mermaid" in p.lower()
