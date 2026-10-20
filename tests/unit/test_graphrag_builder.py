"""Unit tests for deterministic GraphRAG extraction, building and retrieval."""
from __future__ import annotations

import pytest

from src.graphrag.builder import build_graph
from src.graphrag.community import detect_communities
from src.graphrag.extractor import (extract_chunk_entities, extract_code_entities,
                                    extract_test_entities, module_of_symbol, seed_labels)
from src.graphrag.retrieval import global_search, hybrid_search, local_search, rrf_fuse
from src.graphrag.store import GraphStore


def _chunk(**kw):
    base = {"chunk_id": "c1", "document_id": "doc1", "source_pdf": "spec.pdf",
            "page_start": 10, "module": "CanIf", "autosar_release": "R21-11",
            "platform": "P1", "requirement_ids": [], "api_names": [], "ecu_parameters": [],
            "text": "", "normalized_text": ""}
    base.update(kw)
    return base


def test_extract_chunk_entities_creates_nodes_and_relations():
    chunk = _chunk(requirement_ids=["SWS_CanIf_00123"], api_names=["CanIf_Init"],
                   ecu_parameters=["CanIfCtrlCfg"], text="The CanIf module shall ...")
    ents, rels = extract_chunk_entities(chunk)
    types = {e.type for e in ents}
    assert "requirement" in types
    assert "api" in types
    assert "ecuc_parameter" in types
    assert "module" in types
    rels_by = {(r.src_type, r.rel, r.dst_type) for r in rels}
    assert ("api", "satisfies", "requirement") in rels_by
    assert ("document", "contains", "requirement") in rels_by


def test_extract_chunk_entities_drops_requirement_family_prefixes():
    chunk = _chunk(requirement_ids=["PRS_E2E_", "SWS_Com_00123"])
    ents, _ = extract_chunk_entities(chunk)
    labels = {e.label for e in ents if e.type == "requirement"}
    assert labels == {"SWS_Com_00123"}


def test_extract_code_entities_finds_functions_and_rte_calls():
    src = """
#include "CanIf.h"
void CanIf_Main(void) {
    Rte_Read_Speed(&value);
    CanIf_Transmit(pdu);
}
"""
    ents, rels = extract_code_entities("canif.c", src)
    labels = {e.label for e in ents}
    assert "CanIf_Main" in labels
    assert "Rte_Read_Speed" in labels
    assert any(r.rel == "calls" for r in rels)
    assert any(r.rel == "implements" for r in rels)


def test_extract_test_entities_links_annotations():
    src = """
/* @covers SWS_CanIf_00123 */
void TEST_CanIf_Transmit(void) { }
"""
    ents, rels = extract_test_entities("test_canif.c", src)
    labels = {e.label for e in ents}
    assert "TEST_CanIf_Transmit" in labels
    assert "SWS_CanIf_00123" in labels
    assert any(r.rel in ("covers", "covered_by") for r in rels)


def test_module_of_symbol_and_seed_labels():
    assert module_of_symbol("CanIf_Init") == "CanIf"
    assert module_of_symbol("Nothing") == ""
    seeds = seed_labels("Trace SWS_CanIf_00123 through CanIf_Main")
    assert "SWS_CanIf_00123" in seeds
    assert "CanIf" in seeds


@pytest.fixture()
def built(tmp_path):
    st = GraphStore(str(tmp_path / "g.db"))
    chunks = [
        _chunk(chunk_id="c1", requirement_ids=["SWS_CanIf_00123"], api_names=["CanIf_Init"]),
        _chunk(chunk_id="c2", document_id="doc2", module="Com",
               requirement_ids=["SWS_Com_00123"], api_names=["Com_MainLoop"]),
    ]
    code = tmp_path / "canif.c"
    code.write_text("void CanIf_Main(void) { Rte_Read_Speed(&v); }", encoding="utf-8")
    test = tmp_path / "test_canif.c"
    test.write_text("/* @covers SWS_CanIf_00123 */ void TEST_CanIf_Transmit(void){}", encoding="utf-8")
    stats = build_graph(st, chunks, code_roots=[str(tmp_path)], clear=True)
    yield st, stats
    st.close()


def test_build_graph_creates_expected_vocabulary(built):
    st, stats = built
    assert stats["nodes"] > 0
    assert stats["edges"] > 0
    assert stats["traces"] > 0
    types = stats["nodes_by_type"]
    assert types.get("requirement", 0) >= 2
    assert types.get("api", 0) >= 2
    assert types.get("function", 0) >= 1
    assert types.get("test_case", 0) >= 1
    assert st.get_node("requirement:SWS_CanIf_00123") is not None


def test_build_graph_produces_trace_links(built):
    st, _ = built
    links = st.trace_links()
    assert links
    kinds = {l["link_type"] for l in links}
    assert "satisfies" in kinds
    assert any(l["source_type"] == "test_case" for l in links)


def test_detect_communities_assigns_members(built):
    st, _ = built
    comms = detect_communities(st)
    assert comms
    for c in comms:
        assert c["community_id"].startswith("c")
        assert c["title"]
    st.replace_communities(comms)
    assert st.list_communities()


def test_local_search_finds_seed_neighbourhood(built):
    st, _ = built
    res = local_search(st, "SWS_CanIf_00123", depth=2, limit=50)
    assert res["mode"] == "local"
    assert res["seed_nodes"]
    assert res["node_count"] >= 1


def test_global_search_ranks_communities(built):
    st, _ = built
    st.replace_communities(detect_communities(st))
    res = global_search(st, "CanIf", limit=5)
    assert res["mode"] == "global"
    assert res["community_count"] >= 1


def test_hybrid_search_merges_channels(built):
    st, _ = built
    st.replace_communities(detect_communities(st))
    res = hybrid_search(st, "CanIf_Init", depth=2, local_limit=20)
    assert res["mode"] == "hybrid"
    assert "nodes" in res and "communities" in res
    assert res["node_count"] >= 1


def test_rrf_fuse_is_deterministic():
    a = ["x", "y", "z"]
    b = ["y", "x"]
    first = rrf_fuse([a, b])
    second = rrf_fuse([a, b])
    assert first == second
    assert first[0][0] in ("x", "y")
