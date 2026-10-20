"""Unit tests for the GraphRAG knowledge-graph store."""
from __future__ import annotations

import pytest

from src.graphrag.store import GraphStore, TraceLink, node_id, normalize_label


@pytest.fixture()
def store(tmp_path):
    st = GraphStore(str(tmp_path / "graph.db"))
    yield st
    st.close()


def test_node_id_and_normalize():
    assert node_id("requirement", " SWS_Com_00123 ") == "requirement:SWS_Com_00123"
    assert normalize_label("  a   b ") == "a b"


def test_upsert_node_merges_properties(store):
    nid = store.upsert_node("requirement", "SWS_Com_00123", {"release": "R21-11"},
                             source="spec.pdf")
    store.upsert_node("requirement", "SWS_Com_00123", {"chunk_id": "c1"})
    node = store.get_node(nid)
    assert node is not None
    assert node["type"] == "requirement"
    assert node["properties"]["release"] == "R21-11"
    assert node["properties"]["chunk_id"] == "c1"
    assert store.count_nodes() == 1
    assert store.count_nodes("requirement") == 1
    assert store.count_nodes("api") == 0


def test_upsert_node_ignores_empty_label(store):
    assert store.upsert_node("module", "   ") == ""
    assert store.count_nodes() == 0


def test_edges_and_degree(store):
    a = store.upsert_node("api", "CanIf_Init")
    b = store.upsert_node("requirement", "SWS_CanIf_00123")
    store.upsert_edge(a, b, "satisfies", confidence=0.6, is_inferred=True,
                      provenance={"chunk_id": "c1"})
    store.degree()
    assert store.count_edges() == 1
    assert store.get_node(a)["degree"] == 1
    edge = store.edges_of(a)[0]
    assert edge["rel"] == "satisfies"
    assert edge["is_inferred"] is True
    assert edge["direction"] == "out"
    assert edge["provenance"]["chunk_id"] == "c1"


def test_self_loop_edge_is_ignored(store):
    a = store.upsert_node("api", "CanIf_Init")
    store.upsert_edge(a, a, "calls")
    assert store.count_edges() == 0


def test_neighbors_and_shortest_path(store):
    a = store.upsert_node("requirement", "SWS_CanIf_00123")
    b = store.upsert_node("api", "CanIf_Init")
    c = store.upsert_node("function", "CanIf_Main")
    store.upsert_edge(a, b, "satisfies")
    store.upsert_edge(b, c, "calls")
    sub = store.neighbors(a, depth=2)
    assert sub["node_count"] == 3
    assert sub["edge_count"] == 2
    assert sub["root"] == a

    path = store.shortest_path(a, c, max_depth=5)
    assert path["found"] is True
    assert path["path"] == [a, b, c]

    missing = store.shortest_path(a, "function:Nope", max_depth=3)
    assert missing["found"] is False
    assert missing["path"] == []


def test_communities_roundtrip(store):
    store.upsert_node("api", "A")
    store.upsert_node("api", "B")
    store.replace_communities([
        {"community_id": "c001", "title": "APIs", "summary": "api cluster",
         "members": ["api:A", "api:B"], "level": 0, "properties": {}},
    ])
    comms = store.list_communities()
    assert len(comms) == 1
    assert comms[0]["member_count"] == 2
    assert comms[0]["title"] == "APIs"
    assert store.get_node("api:A")["community"] == "c001"
    assert store.get_community("c001")["community_id"] == "c001"
    assert store.get_community("c999") is None


def test_trace_links_filters(store):
    store.add_trace_link(TraceLink(link_id="l1", source_type="api", source_id="api:A",
                                   target_type="requirement", target_id="requirement:R1",
                                   link_type="satisfies", confidence=0.7,
                                   evidence=["chunk c1"], is_inferred=False))
    store.add_trace_link(TraceLink(link_id="l2", source_type="test_case", source_id="test_case:T1",
                                   target_type="requirement", target_id="requirement:R1",
                                   link_type="covers", confidence=0.9,
                                   evidence=["annotation"], is_inferred=False))
    assert len(store.trace_links()) == 2
    assert len(store.trace_links(target_type="requirement")) == 2
    only = store.trace_links(source_type="test_case")
    assert len(only) == 1
    assert only[0]["target_id"] == "requirement:R1"
    assert only[0]["evidence"] == ["annotation"]


def test_stats_shape(store):
    store.upsert_node("api", "A")
    store.upsert_node("requirement", "R1")
    store.upsert_edge("api:A", "requirement:R1", "satisfies", is_inferred=True)
    stats = store.stats()
    assert stats["nodes"] == 2
    assert stats["edges"] == 1
    assert stats["inferred_edges"] == 1
    assert stats["nodes_by_type"]["api"] == 1
    assert stats["edges_by_rel"]["satisfies"] == 1


def test_clear_and_reopen(tmp_path):
    path = str(tmp_path / "graph.db")
    st = GraphStore(path)
    st.upsert_node("api", "A")
    st.commit()
    st.clear()
    assert st.count_nodes() == 0
    st.close()

    st2 = GraphStore(path)
    assert st2.count_nodes() == 0
    st2.close()
