"""Tests for the typed graph store (ADR-0004, ADR-0007, ADR-0011)."""
import pytest

from src.graph import (
    EdgeProvenance,
    GraphEdge,
    GraphNode,
    SqliteGraphStore,
    UnknownRelationError,
    UnknownTypeError,
)


@pytest.fixture()
def store(tmp_path):
    s = SqliteGraphStore(str(tmp_path / "graph.db"))
    yield s
    s.close()


def test_an_unknown_node_type_is_rejected_at_write_time():
    with pytest.raises(UnknownTypeError):
        GraphNode("n1", "vibes", "Vibes")


def test_an_unknown_relation_is_rejected_at_write_time():
    with pytest.raises(UnknownRelationError):
        GraphEdge("n1", "looks_like", "n2")


def test_every_edge_carries_provenance(store):
    store.upsert_nodes([GraphNode("a", "software_component", "A"),
                        GraphNode("b", "port", "B")])
    edge = GraphEdge("a", "has_port", "b", EdgeProvenance(
        artifact_version_id="av-1", source_location_id="sl-9",
        extraction_method="arxml-parser", confidence=1.0, is_inferred=False))
    store.upsert_edges([edge])
    stored = store.list_edges()[0]
    assert stored["provenance"]["artifact_version_id"] == "av-1"
    assert stored["provenance"]["source_location_id"] == "sl-9"
    assert stored["provenance"]["extraction_method"] == "arxml-parser"
    assert stored["provenance"]["is_inferred"] is False


def test_an_inferred_edge_is_marked(store):
    store.upsert_nodes([GraphNode("a", "module", "A"), GraphNode("b", "module", "B")])
    store.upsert_edges([GraphEdge("a", "co_mentioned_with", "b",
                                  EdgeProvenance(is_inferred=True, confidence=0.7))])
    assert store.stats()["inferred_edges"] == 1
    assert store.list_edges()[0]["provenance"]["is_inferred"] is True


def test_upsert_is_idempotent(store):
    store.upsert_nodes([GraphNode("a", "module", "A")])
    store.upsert_nodes([GraphNode("a", "module", "A2")])
    store.upsert_edges([GraphEdge("a", "depends_on", "b")])
    store.upsert_edges([GraphEdge("a", "depends_on", "b")])
    assert store.stats()["nodes"] == 1
    assert store.stats()["edges"] == 1


def test_neighbors_returns_the_documented_neighbourhood(store):
    store.upsert_nodes([GraphNode("a", "software_component", "A"),
                        GraphNode("p", "port", "P"),
                        GraphNode("i", "interface", "I")])
    store.upsert_edges([GraphEdge("a", "has_port", "p"),
                        GraphEdge("p", "references_interface", "i")])
    result = store.neighbors("a", depth=2)
    ids = {n["id"] for n in result["nodes"]}
    assert ids == {"a", "p", "i"}
    assert len(result["edges"]) == 2


def test_neighbors_can_filter_by_predicate(store):
    store.upsert_nodes([GraphNode("a", "module", "A"),
                        GraphNode("b", "module", "B"),
                        GraphNode("c", "module", "C")])
    store.upsert_edges([GraphEdge("a", "depends_on", "b"),
                        GraphEdge("a", "co_mentioned_with", "c")])
    result = store.neighbors("a", depth=1, predicate="depends_on")
    assert {n["id"] for n in result["nodes"]} == {"a", "b"}


def test_paths_finds_the_shortest_route(store):
    store.upsert_nodes([GraphNode(n, "module", n) for n in ("a", "b", "c")])
    store.upsert_edges([GraphEdge("a", "depends_on", "b"),
                        GraphEdge("b", "depends_on", "c")])
    paths = store.paths("a", "c")
    assert paths
    assert paths[0]["nodes"] == ["a", "b", "c"]


def test_no_path_returns_an_empty_list(store):
    store.upsert_nodes([GraphNode("a", "module", "A"), GraphNode("b", "module", "B")])
    assert store.paths("a", "b") == []


def test_stats_reports_the_shape_of_the_graph(store):
    store.upsert_nodes([GraphNode("a", "module", "A"), GraphNode("p", "port", "P")])
    store.upsert_edges([GraphEdge("a", "has_port", "p")])
    stats = store.stats()
    assert stats["nodes"] == 2
    assert stats["edges"] == 1
    assert stats["backend"] == "sqlite"
    assert stats["node_types"] == {"module": 1, "port": 1}


def test_subgraph_collects_the_neighbourhood(store):
    store.upsert_nodes([GraphNode("a", "module", "A"),
                        GraphNode("b", "module", "B"),
                        GraphNode("c", "module", "C")])
    store.upsert_edges([GraphEdge("a", "depends_on", "b")])
    result = store.subgraph(["a"], depth=1)
    assert {n["id"] for n in result["nodes"]} == {"a", "b"}
