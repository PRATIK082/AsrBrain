from src.ingestion.chunking import build_chunks


class P:
    def __init__(self, i, t):
        self.index = i
        self.text = t


def test_chunk_ids_stable_and_paged():
    pages = [P(0, "SWS_CANIF_00001 CanIf_Init shall initialize the module.\n\nSecond paragraph here with enough words " * 4)]
    c1 = build_chunks("d", "f.pdf", "s", "4.4.0", "Classic", "CanIf", "SWS", pages)
    c2 = build_chunks("d", "f.pdf", "s", "4.4.0", "Classic", "CanIf", "SWS", pages)
    assert [c.chunk_id for c in c1] == [c.chunk_id for c in c2]
    assert all(c.page_start == 1 for c in c1)
    assert any(c.requirement_ids for c in c1)
