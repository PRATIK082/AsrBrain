from src.indexing.hybrid import HybridIndex
from src.retrieval.metadata_filter import _release_match
from src.retrieval.pipeline import RetrievalPipeline
from tests.fixtures.version_docs import CLASSIC_42, CLASSIC_44


def _pipe():
    chunks = [dict(CLASSIC_42), dict(CLASSIC_44)]
    idx = HybridIndex()
    idx.build(chunks)
    return RetrievalPipeline(idx, chunks)


def test_version_filter_no_mixing():
    pipe = _pipe()
    res = pipe.retrieve("CanIf_Init in AUTOSAR 4.4")
    assert res["plan"]["release_mode"] == "exact"
    # chunks carry full labels ("4.4.0"), the query a short one ("4.4"): family
    # membership — not string equality — is the no-mixing criterion.
    assert res["evidence"], "exact-release question must return its own release"
    assert all(_release_match(c["autosar_release"], ["4.4"]) for c in res["evidence"])
    assert not any(c["autosar_release"] == "4.2.2" for c in res["evidence"])
