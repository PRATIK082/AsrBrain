"""Unit tests for the scope-first retrieval filter (Phase 5)."""
from src.retrieval.scope import Scope, apply_scope, scope_from_dict


def _chunk(chunk_id: str, **over) -> dict:
    base = {
        "chunk_id": chunk_id,
        "autosar_release": "R24-11",
        "platform": "Foundation",
        "module": "Com",
        "document_type": "TPS",
    }
    base.update(over)
    return base


def test_an_empty_scope_keeps_everything():
    chunks = [_chunk("a"), _chunk("b", module="CanIf")]
    result = apply_scope(chunks, Scope())
    assert len(result.kept) == 2
    assert result.dropped == {}
    assert result.unapplied == []


def test_a_release_filter_drops_the_other_release():
    chunks = [_chunk("a", autosar_release="R24-11"), _chunk("b", autosar_release="R22-11")]
    result = apply_scope(chunks, Scope(releases=["R24-11"]))
    assert [c["chunk_id"] for c in result.kept] == ["a"]
    assert result.dropped.get("release") == 1


def test_module_and_platform_filters_apply():
    chunks = [
        _chunk("a", module="Com", platform="Foundation"),
        _chunk("b", module="CanIf", platform="Adaptive"),
    ]
    result = apply_scope(chunks, Scope(modules=["Com"], platforms=["Foundation"]))
    assert [c["chunk_id"] for c in result.kept] == ["a"]


def test_a_filter_the_corpus_cannot_express_is_reported_as_unapplied():
    chunks = [_chunk("a")]
    result = apply_scope(chunks, Scope(project_id="p1", branch="main", ecu="Ecu1"))
    assert set(result.unapplied) == {"project_id", "branch", "ecu"}
    # The filter did NOT silently drop everything.
    assert len(result.kept) == 1


def test_the_report_never_hides_a_drop():
    chunks = [_chunk("a", autosar_release="R24-11"), _chunk("b", autosar_release="R22-11")]
    report = apply_scope(chunks, Scope(releases=["R24-11"])).to_dict()
    assert report["kept"] == 1
    assert report["total"] == 2
    assert report["dropped_total"] == 1
    assert report["dropped"]["release"] == 1


def test_scope_from_dict_reads_every_dimension():
    scope = scope_from_dict({
        "project_id": "p1", "branch": "main", "ecu": "Ecu1", "vendor": "v",
        "tenant_id": "t1", "releases": ["R24-11"], "platforms": ["Foundation"],
        "modules": ["Com"], "document_types": ["TPS"], "source_types": ["spec"],
        "artifact_versions": ["av-1"], "access_policy": {"role": "engineer"},
    })
    assert scope.project_id == "p1"
    assert scope.releases == ["R24-11"]
    assert scope.access_policy == {"role": "engineer"}
    assert not scope.is_empty()


def test_a_dict_scope_is_accepted():
    chunks = [_chunk("a", module="Com"), _chunk("b", module="CanIf")]
    result = apply_scope(chunks, {"modules": ["Com"]})
    assert [c["chunk_id"] for c in result.kept] == ["a"]
