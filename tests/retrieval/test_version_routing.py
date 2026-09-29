from src.indexing.hybrid import HybridIndex
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
    assert all(c["autosar_release"] == "4.4" for c in res["evidence"])
