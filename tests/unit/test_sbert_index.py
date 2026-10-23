"""SBERT backend seam (ADR-0002): injectable encoder, no model download in tests."""
import numpy as np

from src.indexing.hybrid import HybridIndex


def _stub_encoder(texts):
    vecs = []
    for t in texts:
        v = np.array([len(t), sum(ord(c) for c in t) % 97, len(t.split()), 1.0])
        vecs.append(v)
    return np.stack(vecs)


def _chunks():
    return [{"chunk_id": f"c{i}", "section_title": f"Sec {i}",
             "normalized_text": f"software component runnable entity port {i}"}
            for i in range(5)]


def test_sbert_build_stores_normalised_matrix():
    idx = HybridIndex(backend="sbert", model="stub", encoder=_stub_encoder)
    idx.build(_chunks())
    assert idx.doc_matrix.shape == (5, 4)
    assert np.allclose(np.linalg.norm(idx.doc_matrix, axis=1), 1.0)
    assert idx.model == "stub"


def test_sbert_dense_scores_cosine_shape():
    idx = HybridIndex(backend="sbert", model="stub", encoder=_stub_encoder)
    idx.build(_chunks())
    s = idx.dense_scores("software component")
    assert s.shape == (5,) and np.all(s <= 1.0 + 1e-6)


def test_sbert_save_load_roundtrip_backend(tmp_path):
    idx = HybridIndex(backend="sbert", model="stub", encoder=_stub_encoder)
    idx.build(_chunks())
    p = str(tmp_path / "sbert")
    idx.save(p)
    back = HybridIndex.load(p)
    assert back.backend == "sbert" and back.model == "stub"
    assert np.allclose(back.doc_matrix, idx.doc_matrix)


def test_tfidf_default_unchanged():
    idx = HybridIndex()
    assert idx.backend == "tfidf"
    idx.build(_chunks())
    assert idx.vocab and idx.idf is not None
