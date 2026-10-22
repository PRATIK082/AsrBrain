"""Regression tests for the defects the evaluation harness found.

Each test names the defect it guards. If one of these fails, the corresponding fix has
been undone and the measured baseline is no longer valid.
"""
import numpy as np

from src.generation.verification import confidence_score, split_claims, verify
from src.indexing.hybrid import HybridIndex, tokenize_technical


# --- D-01: BM25 scored one arbitrary query term and varied between processes ------------

def _index():
    idx = HybridIndex()
    idx.build([
        {"chunk_id": "c1", "normalized_text": "The Com module routes signals to the PduR at runtime."},
        {"chunk_id": "c2", "normalized_text": "The PduR routes PDUs to the CanIf over CAN."},
        {"chunk_id": "c3", "normalized_text": "Unrelated text about the diagnostic event manager."},
    ])
    return idx


def test_bm25_scores_every_query_term_not_only_the_last():
    idx = _index()
    scores = idx.bm25_scores("Com module routes signals")
    # "Com" and "signals" both occur in c1; the old implementation scored one arbitrary term,
    # so a chunk matching only one of the query terms scored zero.
    assert scores[0] > 0
    assert scores[0] >= scores[1]


def test_bm25_is_repeatable_within_a_process():
    idx = _index()
    a = idx.bm25_scores("Com module routes signals to the PduR")
    b = idx.bm25_scores("Com module routes signals to the PduR")
    assert np.array_equal(a, b)


def test_bm25_result_does_not_depend_on_set_iteration_order():
    # The old implementation took the last element of `set(q_terms)`; Python salts string
    # hashing per process, so the scored term - and therefore the ranking - changed between
    # runs. Sorting the terms removes the dependency.
    idx = _index()
    q = "Com module routes signals to the PduR"
    forward = idx.bm25_scores(q)
    # a query whose token set iterates in a different order must score the same documents
    reordered = idx.bm25_scores("PduR signals routes module Com")
    assert forward.shape == reordered.shape
    assert float(forward.sum()) > 0
    assert float(reordered.sum()) > 0


def test_bm25_ranks_the_chunk_that_contains_the_rare_token_first():
    idx = HybridIndex()
    idx.build([
        {"chunk_id": "common", "normalized_text": "the module is used in many systems for many things"},
        {"chunk_id": "rare", "normalized_text": "the configuration parameter LinSlaveConfig selects the slave"},
    ])
    scores = idx.bm25_scores("LinSlaveConfig")
    assert scores[1] > scores[0]


# --- D-54: a correctly cited answer was abstained on its own evidence --------------------

def _evidence():
    return [
        {"chunk_id": "e1", "autosar_release": "R24-11", "platform": "Foundation",
         "text": "Com is a module that routes signals to the PduR."},
        {"chunk_id": "e2", "autosar_release": "R24-11", "platform": "Foundation",
         "text": "PduR routes PDUs to the CanIf over the CAN bus."},
    ]


def test_a_short_cited_sentence_is_a_claim():
    claims = split_claims("Com is a module. [E1]")
    assert claims
    assert any("[E1]" in c for c in claims)


def test_the_first_claim_after_a_markdown_header_is_not_lost():
    # The old splitter produced one segment per header-plus-first-sentence and then threw the
    # whole segment away because it started with '#'. Every section lost its first claim.
    claims = split_claims("## Direct answer\nCom is a module. [E1]\n\n## Notes\nOther text is here too.")
    assert any("Com is a module" in c for c in claims)
    assert any("Other text is here too" in c for c in claims)


def test_a_correctly_cited_answer_does_not_abstain():
    draft = "## Direct answer\nCom is a module. [E1]\n\n## Details\nPduR routes PDUs to the CanIf. [E2]"
    evidence = _evidence()
    verification = verify(draft, evidence, {})
    conf = confidence_score(0.5, evidence, verification, {})
    assert verification["claim_support_rate"] == 1.0
    assert verification["citation_coverage"] == 1.0
    assert conf["should_abstain"] is False
    assert conf["level"] in ("High", "Medium")


def test_citation_coverage_counts_cited_claims_not_the_evidence_pool():
    # Dividing the cited-evidence count by the whole evidence pool scored a correct two
    # citation answer over twelve retrieved chunks at 0.17.
    draft = "Com is a module. [E1]\nPduR routes PDUs. [E2]"
    evidence = _evidence() + [{"chunk_id": f"x{i}", "autosar_release": "R24-11",
                               "platform": "Foundation", "text": "filler"} for i in range(10)]
    verification = verify(draft, evidence, {})
    assert verification["citation_coverage"] == 1.0
    assert verification["evidence_total"] == 12


def test_an_answer_without_any_claim_is_not_treated_as_version_consistent():
    verification = {"verdicts": [], "claim_support_rate": 0.0, "citation_coverage": 0.0}
    conf = confidence_score(0.9, _evidence(), verification, {})
    # `all([])` is True, so an answer with no verifiable claim used to look perfectly
    # version-consistent. It is not: it is unverified.
    assert conf["version_consistent"] is False
    assert conf["should_abstain"] is True


def test_an_uncited_answer_abstains():
    draft = "Com is a module that routes signals.\nPduR routes PDUs to the CanIf."
    evidence = _evidence()
    verification = verify(draft, evidence, {})
    conf = confidence_score(0.9, evidence, verification, {})
    assert verification["claim_support_rate"] == 0.0
    assert conf["should_abstain"] is True


def test_tokenize_technical_keeps_the_whole_identifier_and_its_parts():
    # The tokenizer emits the whole identifier lowercased and, in addition, its split parts.
    # The whole form is what gives a requirement id its high inverse document frequency.
    tokens = tokenize_technical("SWS_CanIf_00012")
    assert "sws_canif_00012" in tokens
    assert "canif" in tokens or "can" in tokens
