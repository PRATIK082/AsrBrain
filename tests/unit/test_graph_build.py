"""Graph builder unit tests: deterministic ids, provenance, ARXML projection."""
import json

from src.graph.build import build_arxml, build_spec, edge_id


def _chunk(cid="c1", doc="d1", reqs=None, apis=None, ecucs=None, module="CanIf"):
    reqs = reqs or []
    apis = apis or []
    text = " ".join(reqs + apis) + " are specified together here."
    return {"chunk_id": cid, "document_id": doc, "source_pdf": "f.pdf",
            "page_start": 3, "autosar_release": "4.4.0", "platform": "Classic",
            "module": module, "chunk_kind": "atomic", "normalized_text": text,
            "requirement_ids": reqs,
            "api_names": apis, "ecu_parameters": ecucs or []}


def _doc(doc="d1"):
    return {"document_id": doc, "source_pdf": "f.pdf", "title": "SWS_CanIf.pdf",
            "autosar_release": "4.4.0"}


def test_spec_build_nodes_edges_links():
    nodes, edges, links = build_spec(
        [_chunk(reqs=["SWS_CANIF_1", "SWS_CANIF_2"], apis=["CanIf_Init"],
                ecucs=["CanIfCtrlMode"])],
        [_doc()], "run-t")
    by_id = {n["node_id"]: n for n in nodes}
    assert {"document:d1", "module:CanIf", "requirement:SWS_CANIF_1",
            "requirement:SWS_CANIF_2", "api:CanIf_Init",
            "ecuc:CanIfCtrlMode"} <= set(by_id)
    for n in nodes:
        assert n["snapshot_id"] == "run-t" and n["created_by"] == "parser"
        assert n["content_hash"]
    rels = {(e["src"], e["rel"], e["dst"]) for e in edges}
    assert ("document:d1", "contains", "requirement:SWS_CANIF_1") in rels
    assert ("requirement:SWS_CANIF_1", "references", "requirement:SWS_CANIF_2") in rels
    assert ("api:CanIf_Init", "satisfies", "requirement:SWS_CANIF_1") in rels
    assert links and links[0]["link_id"].startswith("tr-satisfies::")
    assert links[0]["snapshot_id"] == "run-t"


def test_edge_ids_deterministic():
    assert edge_id("a", "references", "b") == edge_id("a", "references", "b")
    assert edge_id("a", "references", "b") != edge_id("a", "contains", "b")


def test_inferred_edges_flagged():
    _, edges, _ = build_spec([_chunk(reqs=["SWS_CANIF_1", "SWS_CANIF_2"])],
                             [_doc()], "run-t")
    inferred = [e for e in edges if e["rel"] == "references"]
    exact = [e for e in edges if e["rel"] == "contains"]
    assert inferred and all(e["is_inferred"] == 1 for e in inferred)
    assert exact and all(e["is_inferred"] == 0 for e in exact)


def test_arxml_projection(tmp_path):
    from src.ingestion.arxml.parser import parse_arxml
    p = tmp_path / "swc.arxml"
    p.write_text(
        '<?xml version="1.0"?><AUTOSAR><AR-PACKAGES><AR-PACKAGE>'
        "<SHORT-NAME>Pkg</SHORT-NAME><ELEMENTS>"
        "<APPLICATION-SW-COMPONENT-TYPE><SHORT-NAME>BrakeCtrl</SHORT-NAME>"
        "<PORTS><P-PORT-PROTOTYPE><SHORT-NAME>P_Brake</SHORT-NAME></P-PORT-PROTOTYPE>"
        "</PORTS></APPLICATION-SW-COMPONENT-TYPE>"
        "</ELEMENTS></AR-PACKAGE></AR-PACKAGES></AUTOSAR>")
    topo = parse_arxml(p)
    nodes, edges = build_arxml([topo], "run-t")
    rels = {(e["src"], e["rel"]) for e in edges}
    assert any(r == "CONTAINS" for _, r in rels)
    assert all(n["snapshot_id"] == "run-t" for n in nodes)
    prov = json.loads(edges[0]["provenance"])
    assert prov["source_sha256"] and "artifact_id" in prov
