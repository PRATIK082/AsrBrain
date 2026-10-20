"""Unit tests for the deterministic Mermaid mindmap renderer."""
from __future__ import annotations

from src.tools.mindmap import (build_mindmap, mindmap_from_evidence, mindmap_from_graph,
                               mindmap_from_outline, render_mermaid, sanitize, tree_from_pairs)


def test_sanitize_strips_mermaid_unsafe_characters():
    assert sanitize('a "b" `c`') == "a b c"
    assert sanitize("x" * 200).endswith("…")
    assert sanitize("") == "untitled"


def test_render_mermaid_uses_mindmap_block_and_root_shape():
    tree = {"label": "CanIf", "children": [{"label": "Init", "children": [{"label": "Rte"}]}]}
    out = render_mermaid(tree)
    lines = out.splitlines()
    assert lines[0] == "mindmap"
    assert lines[1].strip().startswith("n1((")
    assert lines[2].strip().startswith("n2[")
    assert "n3[" in out


def test_render_mermaid_is_deterministic():
    tree = {"label": "root", "children": [{"label": "a"}, {"label": "b"}]}
    assert render_mermaid(tree) == render_mermaid(tree)


def test_tree_from_pairs_skips_empty_branches():
    tree = tree_from_pairs([("Requirements", ["SWS_Com_00123"]), ("Empty", [])], "topic")
    assert tree["label"] == "topic"
    assert len(tree["children"]) == 1
    assert tree["children"][0]["label"] == "Requirements"


def test_mindmap_from_evidence_groups_documents_and_requirements():
    evidence = [
        {"chunk_id": "c1", "source_pdf": "spec.pdf", "section_title": "3.1 Init",
         "module": "CanIf", "requirement_ids": ["SWS_CanIf_00123"],
         "api_names": ["CanIf_Init"]},
    ]
    res = mindmap_from_evidence(evidence, "CanIf")
    assert res["source"] == "evidence"
    assert res["mermaid"].startswith("mindmap")
    assert res["citations"]["spec.pdf - 3.1 Init"] == "c1"
    assert res["node_count"] >= 1
    assert res["empty"] is False


def test_mindmap_from_outline():
    res = mindmap_from_outline([{"label": "Branch", "children": [{"label": "Leaf"}]}], "Topic")
    assert res["source"] == "outline"
    assert "Branch" in res["mermaid"]
    assert res["empty"] is False


def test_mindmap_from_empty_evidence_is_empty():
    res = mindmap_from_evidence([], "Topic")
    assert res["empty"] is True


def test_mindmap_from_graph_and_build_entrypoint(tmp_path):
    from src.graphrag.store import GraphStore
    store = GraphStore(str(tmp_path / "g.db"))
    store.upsert_node("requirement", "SWS_CanIf_00123")
    store.upsert_node("api", "CanIf_Init")
    store.upsert_node("module", "CanIf")
    store.upsert_edge("api:CanIf_Init", "requirement:SWS_CanIf_00123", "satisfies")
    store.degree()

    res = mindmap_from_graph(store, "CanIf_Init", depth=2)
    assert res["source"] == "graph"
    assert "CanIf_Init" in res["mermaid"]
    assert res["node_count"] >= 1

    auto = build_mindmap(topic="CanIf_Init", source="auto", store=store)
    assert auto["mermaid"].startswith("mindmap")

    outline = build_mindmap(topic="T", source="outline", store=store,
                            outline=[{"label": "X"}])
    assert outline["source"] == "outline"

    evidence = build_mindmap(topic="T", source="evidence", store=store,
                             evidence=[{"chunk_id": "c1", "source_pdf": "s.pdf"}])
    assert evidence["source"] == "evidence"
    store.close()
