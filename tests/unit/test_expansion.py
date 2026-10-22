"""Parent expansion: merge atomics into shared parents without duplicating evidence."""
from src.retrieval.context import parent_expand


def _chunk(cid, parent="", score=0.5):
    return {"chunk_id": cid, "parent_chunk_id": parent, "rerank_score": score,
            "normalized_text": "t", "section_title": "s"}


def test_parent_merge_replaces_atomics():
    by_id = {"P": _chunk("P", score=0.1)}
    ranked = [_chunk("A1", "P", 0.9), _chunk("A2", "P", 0.8), _chunk("X", "", 0.7)]
    out = parent_expand(ranked, by_id)
    ids = [c["chunk_id"] for c in out]
    assert ids == ["P", "X"]
    assert out[0]["merged_from"] == ["A1", "A2"]


def test_parent_candidate_not_duplicated():
    # The parent itself is often a ranked candidate too (context chunks are
    # retrieved). It must appear once — as the merge — never twice.
    by_id = {"P": _chunk("P", score=0.1)}
    ranked = [_chunk("P", "", 0.95), _chunk("A1", "P", 0.9), _chunk("A2", "P", 0.8)]
    out = parent_expand(ranked, by_id)
    ids = [c["chunk_id"] for c in out]
    assert ids == ["P"]


def test_single_atomic_has_no_parent():
    by_id = {"P": _chunk("P", score=0.1)}
    ranked = [_chunk("A1", "P", 0.9), _chunk("X", "", 0.7)]
    assert [c["chunk_id"] for c in parent_expand(ranked, by_id)] == ["A1", "X"]


def test_identifier_match_word_boundaries():
    from src.retrieval.reranking import identifier_matches
    toks = {"sws_canif_00072", "explain"}
    assert identifier_matches(toks, "SWS_CANIF_00072")
    assert not identifier_matches(toks, "SWS_CANIF_0007")  # near-miss, no prefix rule
    assert not identifier_matches({"sws_x_11"}, "SWS_X_1")  # substring trap
    assert identifier_matches({"prs_e2e_03176"}, "PRS_E2E_")  # truncated stored id
    assert not identifier_matches(toks, "ab")  # too short


def _ev(text, title=""):
    return {"chunk_id": "c", "section_title": title, "normalized_text": text}


def test_model_classifier_pure_class_def():
    from src.retrieval.context import is_model_structure
    text = ("Class CouplingElement Package M2::AUTOSARTemplates::SystemTemplate Note "
            "A CouplingElement connects EcuInstances. Aggregated by EthernetCluster "
            "Base ARObject CollectableElement atp.recommendedPackage CouplingElements")
    assert is_model_structure(_ev(text))


def test_model_classifier_mapping_table_is_config():
    from src.retrieval.context import is_model_structure
    text = ("BSW Module BSW Context EthIf BSW Parameter EthIfSwitchPortGroup "
            "ECUC-PARAM-CONTAINER-DEF BSW Description Template Description M2 Parameter "
            "Mapping Rule Mapping Type 1:1 mapping full ECUC_EthIf_00038 The host port "
            "shall be part of all groups. Class Mapping shall apply.")
    assert not is_model_structure(_ev(text))


def test_model_classifier_traffic_class_prose_is_config():
    # "Traffic Class" tables say "Class" — must not misfile as model structure.
    from src.retrieval.context import is_model_structure
    text = ("Table 3.71: Port to Traffic Class mapping. Traffic Class Prio 0 7 "
            "The Traffic Class mapping shall be configured per ingress port.")
    assert not is_model_structure(_ev(text))


def test_order_evidence_config_first_model_last():
    from src.retrieval.context import is_model_structure, order_evidence
    model_text = ("Class CouplingPort Package M2::X Aggregated by CouplingElement "
                  "Base ARObject atp.recommendedPackage Note text here.")
    cfg = _ev("The host port shall be part of all EthIfSwitchPortGroups. ECUC- mapping.")
    mod = _ev(model_text)
    out = order_evidence([mod, cfg])
    assert [c["normalized_text"] for c in out] == [cfg["normalized_text"],
                                                  mod["normalized_text"]]
    # same set, only reordered
    assert {c["normalized_text"] for c in out} == {cfg["normalized_text"],
                                                  mod["normalized_text"]}
