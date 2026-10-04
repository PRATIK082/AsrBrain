import asyncio
from src.schema.canonical import CanonicalContent, make_content_id, from_chunk
from src.ingestion.processors import (TextProcessor, RequirementProcessor, TableProcessor,
                                      ImageProcessor, DiagramProcessor, EquationProcessor)
from src.generation.routing import route_task, check_privacy, STRICT_SYSTEM
from src.retrieval.planner import plan
from src.retrieval.modality_fusion import fuse, SPEC_WEIGHTS
from src.retrieval.context_rules import assemble, to_spec_claim, include_image
from src.schema.multimodal_graph import TypedEdge, Provenance, NODES, RELATIONS
from src.indexing.collections import payload_for, collection_for, EXACT_KEYWORD_FIELDS
from src.ingestion.parser_adapter import route_parser


def _c(**kw):
    base = dict(content_id="x", document_id="d", content_type="text", source_pdf="p", source_sha256="s")
    base.update(kw)
    return CanonicalContent(**base)


def test_canonical_provenance():
    c = _c(page_index=118, section="7.3.2", autosar_release="AUTOSAR_4.4.0", platform="Classic")
    p = c.provenance()
    assert p["page_index"] == 118 and p["release"] == "AUTOSAR_4.4.0"
    assert c.generated_description is None  # supplementary, never authoritative by default


def test_processors():
    t = asyncio.run(TextProcessor().process(_c(raw_text="SWS_CanIf_00001  The module shall init  See 7.1")))
    assert "SWS_CanIf_00001" in (t.structured_data or {})["references"]
    r = asyncio.run(RequirementProcessor().process(_c(raw_text="SWS_X_1 The stack shall not drop frames unless DET.")))
    assert r.content_type == "requirement" and "shall not" in (r.structured_data or {})["modals"]
    tab = _c(content_type="table", structured_data={"rows": [["Param", "Val"], ["CanIfTxPduCfg", "1"]]})
    tab = asyncio.run(TableProcessor().process(tab))
    assert tab.table_markdown and "<table>" in (tab.table_html or "")
    img = asyncio.run(ImageProcessor().process(_c(content_type="image", caption="CanIf_Init flow")))
    assert img.structured_data and img.generated_description is None
    dg = asyncio.run(DiagramProcessor().process(_c(content_type="diagram", caption="AUTOSAR logo cover")))
    assert dg.structured_data["is_decorative"]
    eq = asyncio.run(EquationProcessor().process(_c(content_type="equation", equation_latex="x^2")))
    assert eq.structured_data["latex_preserved"]


def test_routing_privacy():
    assert "Do not mix AUTOSAR releases" in STRICT_SYSTEM
    try:
        check_privacy("local_only", "openai_compat", True, False)
        assert False
    except PermissionError:
        pass
    try:
        check_privacy("never_send_document_images", "openai_compat", False, True)
        assert False
    except PermissionError:
        pass
    assert route_task("diagram_analysis", "local_only", ollama_model="m")["kind"] == "ollama"


def test_planner_isolation():
    p = plan("Compare CanIf in AUTOSAR 4.2 and 4.4")
    assert p["comparison_mode"] and len(p["release_branches"]) == 2
    assert "diagram" in p["required_modalities"] or "table" in p["required_modalities"]
    q = plan("Show the communication path from application to CAN hardware")
    assert "diagram" in q["required_modalities"]


def test_fusion_weights():
    assert abs(sum(SPEC_WEIGHTS["api_lookup"]) - 1.0) < 1e-6
    out = fuse({"a": 1.0, "b": 0.1}, {"b": 1.0, "c": 0.2}, {"a": 0.5}, {}, intent="api_lookup")
    assert out["a"] > out["c"]  # lexical dominates exact lookup


def test_context_rules_no_mix():
    ev = [{"content_type": "text", "autosar_release": "4.4", "score": 0.9},
          {"content_type": "text", "autosar_release": "4.2", "score": 0.9}]
    got = assemble(ev, ["text"], release_filter=["4.4"])
    assert all(e["autosar_release"] == "4.4" for e in got)
    assert not include_image({"score": 0.9}, ["text"], 1)  # no visual need → excluded
    assert include_image({"score": 0.9, "caption": "path", "page_index": 3}, ["diagram"], 1)
    claim = to_spec_claim("x", ["a"], True, True, True, 0.95)
    assert set(claim) == {"claim", "supported", "evidence_ids", "citation_valid",
                          "release_consistent", "platform_consistent", "support_score"}


def test_graph_provenance():
    e = TypedEdge(subject="CanIf_Init", subject_type="api", predicate="defined_in",
                  object="CanIf", object_type="module",
                  provenance=Provenance(source_pdf="sws.pdf", page_index=118,
                                        release="AUTOSAR_4.4.0", platform="Classic",
                                        confidence=0.94, is_inferred=False))
    assert e.model_valid()
    assert "diagram" in NODES and "differs_from" in RELATIONS


def test_collections_exact():
    c = _c(content_type="table", requirement_ids=["SWS_CANIF_00001"], api_names=["CanIf_Init"])
    pl = payload_for(c)
    assert pl["requirement_ids"] == ["SWS_CANIF_00001"] and "requirement_ids" in EXACT_KEYWORD_FIELDS
    assert collection_for("diagram") == "diagram" and collection_for("weird") == "text"
    assert route_parser("x.pdf", {"scanned_pages": [1]}) == "pymupdf"
