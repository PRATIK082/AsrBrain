from src.retrieval.modalities import requirement_search, api_search, table_search, figure_search
from src.config.settings import settings


def test_requirement_exact_field_priority():
    rows = requirement_search(settings.canonical_db, "PRS_SOMEIP")
    assert len(rows) >= 1
    assert any("PRS_SOMEIP" in " ".join(r.get("requirement_ids", "[]")) for r in rows)


def test_table_figure_stores_queryable():
    assert isinstance(table_search(settings.canonical_db, "SOMEIP"), list)
    assert isinstance(figure_search(settings.canonical_db, "Figure"), list)
