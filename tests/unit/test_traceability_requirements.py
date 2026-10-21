"""Unit tests for requirement normalisation (Phase 6).

Every source spells the same requirement differently. The module must fold
those spellings into one shape, keep the columns it does not recognise, and
never claim more than the data says.
"""
from src.traceability.requirements import (
    LINK_REVIEW_STATES,
    REVIEW_STATES,
    Requirement,
    ingest_requirements_csv,
    ingest_requirements_json,
    normalise_requirement,
)


def test_the_id_aliases_all_map_to_the_canonical_id():
    assert normalise_requirement({"req_id": "R1"}).id == "R1"
    assert normalise_requirement({"requirement_id": "R2"}).id == "R2"
    assert normalise_requirement({"key": "R3"}).id == "R3"


def test_the_title_aliases_map_to_the_canonical_title():
    assert normalise_requirement({"id": "R1", "summary": "A summary"}).title == "A summary"
    assert normalise_requirement({"id": "R2", "name": "A name"}).title == "A name"


def test_test_method_maps_to_the_verification_method():
    assert normalise_requirement({"id": "R1", "test_method": "T"}).verification_method == "T"


def test_an_unrecognised_verification_column_is_not_promoted():
    # "verif" is not one of the documented aliases, so it must not be turned
    # into a verification_method - it stays where the source put it.
    requirement = normalise_requirement({"id": "R1", "verif": "T"})
    assert requirement.verification_method == ""
    assert requirement.properties["verif"] == "T"


def test_unknown_columns_are_kept_in_properties():
    requirement = normalise_requirement(
        {"id": "R1", "title": "A title", "owner": "ana", "ticket": "A-12"})
    assert requirement.properties["owner"] == "ana"
    assert requirement.properties["ticket"] == "A-12"
    # A column that *is* recognised is not duplicated into the properties.
    assert "title" not in requirement.properties


def test_the_status_spellings_are_normalised():
    assert normalise_requirement({"id": "R1", "status": "in progress"}).status == "in-progress"
    assert normalise_requirement({"id": "R2", "status": "done"}).status == "implemented"
    assert normalise_requirement({"id": "R3", "status": "rejected"}).status == "rejected"
    assert normalise_requirement({"id": "R4", "status": "obsolete"}).status == "rejected"


def test_an_unknown_status_is_kept_but_lowercased():
    assert normalise_requirement({"id": "R1", "status": "Deferred"}).status == "deferred"


def test_an_id_is_sanitised():
    # _clean_id replaces every run of characters outside [A-Za-z0-9_.-] with a
    # single underscore and then strips the underscores at both ends.
    assert normalise_requirement({"id": "REQ 001/ABC"}).id == "REQ_001_ABC"
    assert normalise_requirement({"id": "  spaced id  "}).id == "spaced_id"


def test_the_parent_id_is_sanitised_the_same_way():
    assert normalise_requirement({"id": "R1", "parent_id": "REQ 0/1"}).parent_id == "REQ_0_1"


def test_the_project_and_artifact_version_are_carried():
    requirement = normalise_requirement({"id": "R1"}, project_id="p1", artifact_version_id="av1")
    assert requirement.project_id == "p1"
    assert requirement.artifact_version_id == "av1"


def test_a_normalised_requirement_is_machine_extracted_until_a_human_looks():
    assert normalise_requirement({"id": "R1"}).review_state == "machine-extracted"


def test_csv_ingestion_skips_blank_rows_and_rows_without_an_id():
    text = ("req_id,summary,status,owner\n"
            "REQ-1,First requirement,in progress,ana\n"
            ",No id at all,open,ana\n"
            ",,,\n"
            "REQ-2,Second requirement,done,bo\n")
    requirements = ingest_requirements_csv(text)
    assert [r.id for r in requirements] == ["REQ-1", "REQ-2"]
    assert [r.title for r in requirements] == ["First requirement", "Second requirement"]
    assert requirements[0].status == "in-progress"
    assert requirements[1].status == "implemented"
    # The column the module does not recognise is preserved, not dropped.
    assert requirements[0].properties["owner"] == "ana"


def test_csv_ingestion_returns_requirement_objects():
    requirements = ingest_requirements_csv("id,title\nR1,One\n")
    assert all(isinstance(r, Requirement) for r in requirements)


def test_json_ingestion_accepts_a_bare_list():
    requirements = ingest_requirements_json('[{"id": "J-1", "title": "One"}]')
    assert [r.id for r in requirements] == ["J-1"]
    assert requirements[0].title == "One"


def test_json_ingestion_accepts_an_object_with_a_requirements_key():
    text = '{"requirements": [{"requirement_id": "J-2", "summary": "Two"}]}'
    requirements = ingest_requirements_json(text)
    assert [r.id for r in requirements] == ["J-2"]
    assert requirements[0].title == "Two"


def test_json_ingestion_skips_rows_without_an_id():
    assert ingest_requirements_json('[{"title": "no id"}]') == []


def test_the_link_review_states_are_the_five_documented_states():
    assert LINK_REVIEW_STATES == ("proposed", "machine-extracted", "reviewed",
                                   "approved", "rejected")
    assert len(LINK_REVIEW_STATES) == 5


def test_the_requirement_review_states_are_the_four_documented_states():
    assert REVIEW_STATES == ("machine-extracted", "reviewed", "approved", "rejected")
    assert len(REVIEW_STATES) == 4
