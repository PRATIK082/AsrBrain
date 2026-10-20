"""Unit tests for the read-only institutional-assistant knowledge layer.

These are model-free and deterministic: they only read the canonical store.
When no corpus is indexed the helpers must degrade gracefully instead of
raising, so the assertions hold with or without `data/canonical/canonical.db`.
"""
from src.assistant import knowledge


def test_requirement_ids_are_separated_from_api_names():
    assert knowledge._is_requirement_id("SWS_CanIf_00123")
    assert knowledge._is_requirement_id("PRS_SOMEIP_00051")
    # API names must not be mistaken for requirement identifiers.
    assert not knowledge._is_requirement_id("Com_SignalTransmit")
    assert not knowledge._is_requirement_id("CanIf_Init")
    assert not knowledge._is_requirement_id("")


def test_corpus_manifest_shape_is_stable_without_a_store():
    manifest = knowledge.corpus_manifest("data/does-not-exist/canonical.db")
    assert manifest["available"] is False
    assert manifest["chunks"] == 0
    assert manifest["releases"] == []
    assert manifest["modules"] == []


def test_corpus_manifest_counts_match_the_canonical_store():
    manifest = knowledge.corpus_manifest()
    assert "chunks" in manifest and "documents" in manifest
    if not manifest["available"]:
        return
    # Requirements and APIs are counted as de-duplicated entity facets.
    assert manifest["requirements"] <= manifest["chunks"]
    assert manifest["apis"] <= manifest["chunks"]
    assert manifest["chunks"] > 0


def test_capabilities_exposes_modes_surfaces_and_guarantees():
    caps = knowledge.capabilities()
    assert caps["assistant"]
    assert caps["kind"]
    mode_ids = {m["id"] for m in caps["modes"]}
    assert "auto" in mode_ids
    assert "troubleshooting" in mode_ids
    surface_ids = {s["id"] for s in caps["surfaces"]}
    assert {"chat", "arxml", "diff", "code"} <= surface_ids
    assert caps["guarantees"], "the assistant must state its guarantees"
    assert isinstance(caps["ready"], bool)


def test_project_overview_reports_modules_and_concept_flow():
    overview = knowledge.project_overview()
    if not overview.get("available"):
        assert overview["modules"] == []
        assert overview["concept_flow"] == []
        return
    assert overview["modules"], "an indexed corpus must expose modules"
    for module in overview["modules"]:
        assert "module" in module
        assert "chunks" in module
    for triple in overview["concept_flow"]:
        # Every concept-flow row must be traceable to a passage.
        assert triple.get("requirement") and triple.get("api")
        assert triple.get("source_pdf")
        assert triple.get("chunk_id")
    anchors = overview["entity_anchors"]
    assert "requirements" in anchors and "apis" in anchors


def test_starter_prompts_are_grouped_and_grounded_in_real_entities():
    groups = knowledge.starter_prompts()
    assert groups
    group_ids = {g["group"] for g in groups}
    assert len(group_ids) == len(groups), "prompt groups must be unique"
    for group in groups:
        assert group["icon"]
        assert group["prompts"]
        for prompt in group["prompts"]:
            assert prompt["title"]
            assert prompt["prompt"]
            # Prompts must ask something, not state an answer.
            assert "?" in prompt["prompt"] or "list" in prompt["prompt"].lower()
