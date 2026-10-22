"""Unit tests for the evaluation metric library."""
import math

from src.evaluation import metrics as M


def test_content_tokens_drops_stopwords():
    assert "the" not in M.content_tokens("What is the purpose of SOME/IP?")
    assert "purpose" in M.content_tokens("What is the purpose of SOME/IP?")


def test_extract_identifiers_finds_requirement_and_api_names():
    ids = M.extract_identifiers("The rule SWS_CanIf_00012 requires CanIf_Transmit to return E_NOT_OK.")
    assert "SWS_CanIf_00012" in ids
    assert "CanIf_Transmit" in ids
    assert M.extract_identifiers("The CanIf module routes frames.") == ["CanIf"]


def test_extract_exact_tokens_includes_numbers_with_units():
    toks = M.extract_exact_tokens("The timeout shall not exceed 500 ms per cycle.")
    assert any("500" in t for t in toks)


def test_claim_supported_requires_the_identifier_verbatim():
    chunk = "The requirement SWS_CanIf_00012 mandates a timeout of 500 ms."
    assert M.claim_supported("SWS_CanIf_00012 mandates a timeout.", chunk)
    assert not M.claim_supported("SWS_CanIf_99999 mandates a timeout.", chunk)


def test_claim_supported_falls_back_to_content_words():
    chunk = "The Com module routes signals to the PduR at runtime."
    assert M.claim_supported("Com routes signals to the PduR.", chunk)
    assert not M.claim_supported("The CanTp module handles diagnostics.", chunk)


def test_citation_precision_counts_supported_pairs():
    verdicts = [
        {"claim": "SWS_CanIf_00012 mandates a timeout.", "cited_chunk_texts": ["SWS_CanIf_00012 mandates a timeout."]},
        {"claim": "SWS_CanIf_99999 mandates a timeout.", "cited_chunk_texts": ["SWS_CanIf_00012 mandates a timeout."]},
    ]
    assert M.citation_precision(verdicts) == 0.5


def test_citation_recall_counts_only_gold_evidence_that_was_cited():
    assert M.citation_recall(["a", "b"], ["a", "b", "c"], ["a"]) == 0.5
    assert M.citation_recall(["a"], [], []) == 0.0
    assert M.citation_recall([], ["a"], ["a"]) == 0.0


def test_context_precision_and_recall():
    assert M.context_recall(["a", "x"], ["a", "b"]) == 0.5
    assert M.context_precision(["a", "x"], ["a", "b"]) == 0.5
    assert M.context_recall([], ["a"]) == 0.0


def test_faithfulness_is_zero_without_claims():
    assert M.faithfulness([], ["some evidence"]) == 0.0
    claims = ["SWS_CanIf_00012 shall apply."]
    assert M.faithfulness(claims, ["SWS_CanIf_00012 shall apply."]) == 1.0
    assert M.faithfulness(claims, ["nothing relevant"]) == 0.0


def test_rouge1_f1():
    assert M.rouge1_f1("the cat sat", "the cat sat") == 1.0
    assert M.rouge1_f1("completely different words", "the cat sat") == 0.0
    partial = M.rouge1_f1("the cat ran", "the cat sat")
    assert 0.0 < partial < 1.0


def test_exact_id_match():
    assert M.exact_id_match(["SWS_CanIf_00012"], "see SWS_CanIf_00012 for details") == 1.0
    assert M.exact_id_match(["SWS_CanIf_00012"], "see SWS_CanIf_99999") == 0.0


def test_hallucinated_id_rate_finds_identifiers_absent_from_the_evidence():
    rate, bad = M.hallucinated_id_rate("SWS_CanIf_99999 is required.", ["the real evidence"])
    assert rate == 1.0
    assert "SWS_CanIf_99999" in bad
    rate2, bad2 = M.hallucinated_id_rate("SWS_CanIf_00012 is required.", ["SWS_CanIf_00012 is required."])
    assert rate2 == 0.0
    assert bad2 == []


def test_abstention_accuracy_is_not_circular():
    # answerable + answered -> correct
    assert M.abstention_accuracy(True, False) == 1.0
    # answerable + abstained -> wrong
    assert M.abstention_accuracy(True, True) == 0.0
    # unanswerable + abstained -> correct
    assert M.abstention_accuracy(False, True) == 1.0
    # unanswerable + answered -> wrong
    assert M.abstention_accuracy(False, False) == 0.0


def test_percentile_uses_nearest_rank():
    vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert M.percentile(vals, 50) == 5
    assert M.percentile(vals, 95) == 10
    assert M.percentile(vals, 0) == 1
    assert M.percentile([], 50) == 0.0


def test_wilson_interval_contains_the_proportion():
    lo, hi = M.wilson_interval(50, 100)
    assert lo < 0.5 < hi
    assert 0.0 <= lo <= hi <= 1.0
    assert M.wilson_interval(0, 0) == (0.0, 0.0)


def test_mean_ci95_contains_the_mean():
    vals = [0.1, 0.2, 0.3, 0.4, 0.5]
    mean = sum(vals) / len(vals)
    lo, hi = M.mean_ci95(vals)
    assert lo <= mean <= hi
    assert M.mean_ci95([]) == (0.0, 0.0)


def test_mean_ci95_never_excludes_its_own_mean():
    # Regression guard: the Wilson interval is for proportions of trials, not for means of
    # ratios. Using it for a mean produced intervals that excluded the mean itself.
    vals = [0.09] * 30 + [0.02] * 5
    mean = sum(vals) / len(vals)
    lo, hi = M.mean_ci95(vals)
    assert lo <= mean <= hi
    assert math.isfinite(lo) and math.isfinite(hi)


def test_estimate_tokens_and_cost():
    assert M.estimate_tokens("abcd" * 10) == 10
    assert M.cost_usd("a" * 400, "b" * 400, 0.0, 0.0) == 0.0
    assert M.cost_usd("a" * 400, "b" * 400, 1.0, 2.0) > 0


def test_methods_document_every_proxy():
    for name in ("faithfulness", "answer_relevance", "answer_correctness",
                 "citation_precision", "abstention_accuracy", "hallucinated_id_rate"):
        assert name in M.METHODS
        assert M.METHODS[name]
