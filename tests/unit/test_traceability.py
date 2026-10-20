"""Unit tests for the traceability tools (requirement <-> code <-> test case)."""
from __future__ import annotations

import pytest

from src.graphrag.builder import build_graph
from src.graphrag.store import GraphStore, TraceLink
from src.tools import traceability


@pytest.fixture()
def store(tmp_path):
    st = GraphStore(str(tmp_path / "g.db"))
    st.upsert_node("requirement", "SWS_CanIf_00123")
    st.upsert_node("api", "CanIf_Init")
    st.upsert_node("function", "CanIf_Main")
    st.upsert_node("test_case", "TEST_CanIf_Transmit")
    st.add_trace_link(TraceLink(link_id="l1", source_type="api", source_id="api:CanIf_Init",
                                target_type="requirement", target_id="requirement:SWS_CanIf_00123",
                                link_type="satisfies", confidence=0.7, is_inferred=True,
                                evidence=["chunk c1"]))
    st.add_trace_link(TraceLink(link_id="l2", source_type="test_case",
                                source_id="test_case:TEST_CanIf_Transmit",
                                target_type="requirement", target_id="requirement:SWS_CanIf_00123",
                                link_type="covers", confidence=0.95, is_inferred=False,
                                evidence=["annotation"]))
    st.commit()
    yield st
    st.close()


def test_trace_links_filters(store):
    res = traceability.trace_links(store=store)
    assert res["count"] == 2
    only = traceability.trace_links(source_type="test_case", store=store)
    assert only["count"] == 1
    assert only["links"][0]["link_type"] == "covers"


def test_trace_requirements_resolves_direct_and_linked(store):
    res = traceability.trace_requirements("SWS_CanIf_00123", store=store)
    assert res["count"] >= 1
    reqs = {r["requirement"] for r in res["requirements"]}
    assert "requirement:SWS_CanIf_00123" in reqs


def test_trace_requirements_empty_query(store):
    res = traceability.trace_requirements("", store=store)
    assert res["count"] == 0
    assert res["requirements"] == []


def test_trace_tests_finds_covering_test_cases(store):
    res = traceability.trace_tests("SWS_CanIf_00123", store=store)
    assert res["count"] >= 1
    assert res["tests"][0]["test_case"] == "test_case:TEST_CanIf_Transmit"
    assert res["tests"][0]["covers"] == "requirement:SWS_CanIf_00123"


def test_trace_matrix_reports_requirement_ids_and_rows(store):
    res = traceability.trace_matrix(store=store)
    assert res["requirements"] >= 1
    assert "requirement:SWS_CanIf_00123" in res["requirement_ids"]
    assert res["row_count"] >= 1
    assert res["module"] == "*"


def test_trace_gaps_lists_uncovered_requirements(store):
    res = traceability.trace_gaps(store=store)
    assert res["total_requirements"] >= 1
    assert isinstance(res["without_code"], list)
    assert isinstance(res["without_test"], list)


def test_trace_requirements_falls_back_to_module_names(store):
    """A free-text query is resolved through the deterministic identifier extraction."""
    st = GraphStore(":memory:")
    st.upsert_node("module", "CanIf")
    st.upsert_node("api", "CanIf_Init")
    st.add_trace_link(TraceLink(link_id="m1", source_type="api", source_id="api:CanIf_Init",
                                target_type="requirement", target_id="requirement:SWS_CanIf_00123",
                                link_type="satisfies", confidence=0.7, is_inferred=True,
                                evidence=["chunk c1"]))
    st.commit()
    res = traceability.trace_requirements("explain CanIf initialization", store=st)
    reqs = {r["requirement"] for r in res["requirements"]}
    assert "requirement:SWS_CanIf_00123" in reqs
    st.close()


def test_traceability_tools_use_the_injected_store(tmp_path):
    """The tools must not fall back to the global store when one is supplied."""
    st = GraphStore(str(tmp_path / "g.db"))
    st.upsert_node("requirement", "SWS_X_00001")
    res = traceability.trace_matrix(module="X", store=st)
    assert res["module"] == "X"
    st.close()


def test_build_graph_trace_links_feed_the_tools(tmp_path):
    st = GraphStore(str(tmp_path / "g.db"))
    chunks = [{
        "chunk_id": "c1", "document_id": "d1", "source_pdf": "s.pdf", "page_start": 1,
        "module": "CanIf", "autosar_release": "R21-11", "requirement_ids": ["SWS_CanIf_00123"],
        "api_names": ["CanIf_Init"], "ecu_parameters": [], "text": "", "normalized_text": "",
    }]
    src = tmp_path / "canif.c"
    src.write_text("void CanIf_Main(void){ Rte_Read_Speed(&v); }", encoding="utf-8")
    test = tmp_path / "test_canif.c"
    test.write_text("/* @covers SWS_CanIf_00123 */ void TEST_CanIf_Transmit(void){}", encoding="utf-8")
    build_graph(st, chunks, code_roots=[str(tmp_path)], clear=True)

    matrix = traceability.trace_matrix(store=st)
    assert matrix["requirements"] >= 1
    gaps = traceability.trace_gaps(store=st)
    assert gaps["total_requirements"] >= 1
    st.close()
