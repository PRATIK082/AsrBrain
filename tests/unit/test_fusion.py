from src.retrieval.fusion import rrf


def test_rrf_prefers_top_ranked():
    s = rrf([["a", "b"], ["b", "a"]], k=60)
    assert set(s) == {"a", "b"}
    s2 = rrf([["a"], ["a"]], k=60)
    assert s2["a"] > s["a"]
