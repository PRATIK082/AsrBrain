"""Unit tests for the traceability matrix, coverage, orphans and impact.

The language is deliberately careful: a requirement with a test case has
*evidence available for review*. It is never "compliant", and nothing here
may say so.
"""
from src.traceability.matrix import (
    coverage_report,
    impact_of_requirement,
    orphan_report,
    traceability_matrix,
)


def _requirements():
    return [
        {"id": "REQ-1", "title": "First", "status": "open", "review_state": "approved"},
        {"id": "REQ-2", "title": "Second", "status": "open", "review_state": "approved"},
        {"id": "REQ-3", "title": "Third", "status": "open", "review_state": "approved"},
    ]


def _links():
    return [
        {"id": "l1", "source_type": "requirement", "source_id": "REQ-1",
         "target_type": "test_case", "target_id": "TC-1", "review_state": "approved"},
        {"id": "l2", "source_type": "requirement", "source_id": "REQ-2",
         "target_type": "test_case", "target_id": "TC-2", "review_state": "proposed"},
    ]


def _test_cases():
    return [
        {"id": "TC-1", "name": "test one", "suite": "unit"},
        {"id": "TC-2", "name": "test two", "suite": "unit"},
    ]


def _results():
    return [
        {"id": "res-1", "run_id": "run-1", "test_case_id": "TC-1", "status": "passed"},
        {"id": "res-2", "run_id": "run-1", "test_case_id": "TC-2", "status": "failed"},
    ]


def test_the_matrix_has_one_row_per_requirement():
    matrix = traceability_matrix(_requirements(), _links(), _test_cases(), _results())
    assert len(matrix["rows"]) == len(_requirements())
    assert [r["requirement_id"] for r in matrix["rows"]] == ["REQ-1", "REQ-2", "REQ-3"]


def test_a_row_carries_its_linked_test_cases():
    matrix = traceability_matrix(_requirements(), _links(), _test_cases(), _results())
    rows = {r["requirement_id"]: r for r in matrix["rows"]}
    assert [t["id"] for t in rows["REQ-1"]["test_cases"]] == ["TC-1"]
    assert rows["REQ-1"]["test_cases"][0]["name"] == "test one"
    assert rows["REQ-1"]["test_cases"][0]["latest_status"] == "passed"
    assert rows["REQ-3"]["test_cases"] == []


def test_the_reverse_list_has_one_entry_per_test_case():
    matrix = traceability_matrix(_requirements(), _links(), _test_cases(), _results())
    assert len(matrix["reverse"]) == len(_test_cases())
    assert [r["test_case_id"] for r in matrix["reverse"]] == ["TC-1", "TC-2"]
    assert matrix["reverse"][0]["name"] == "test one"


def test_the_reverse_list_resolves_the_requirement_of_a_test_case():
    matrix = traceability_matrix(_requirements(), _links(), _test_cases(), _results())
    assert matrix["reverse"][0]["requirements"] == ["REQ-1"]


def test_an_approved_link_counts_as_accepted():
    matrix = traceability_matrix(_requirements(), _links(), _test_cases(), _results())
    rows = {r["requirement_id"]: r for r in matrix["rows"]}
    assert rows["REQ-1"]["accepted_links"] == 1
    assert rows["REQ-1"]["proposed_links"] == 0
    assert rows["REQ-1"]["evidence"] == "available for review"


def test_a_reviewed_link_counts_as_accepted():
    links = [{"id": "l1", "source_type": "requirement", "source_id": "REQ-1",
              "target_type": "test_case", "target_id": "TC-1", "review_state": "reviewed"}]
    matrix = traceability_matrix(_requirements(), links, _test_cases(), _results())
    rows = {r["requirement_id"]: r for r in matrix["rows"]}
    assert rows["REQ-1"]["accepted_links"] == 1
    assert rows["REQ-1"]["evidence"] == "available for review"


def test_a_proposed_link_is_not_accepted():
    matrix = traceability_matrix(_requirements(), _links(), _test_cases(), _results())
    rows = {r["requirement_id"]: r for r in matrix["rows"]}
    assert rows["REQ-2"]["accepted_links"] == 0
    assert rows["REQ-2"]["proposed_links"] == 1
    assert rows["REQ-2"]["evidence"] == "not yet reviewed"


def test_the_coverage_report_counts_accepted_proposed_and_unlinked():
    report = coverage_report(_requirements(), _links(), _test_cases(), _results())
    assert report["requirements"] == 3
    assert report["with_accepted_link"] == 1
    assert report["with_proposed_link_only"] == 1
    assert report["without_any_link"] == 1


def test_the_coverage_report_lists_the_failing_requirements():
    report = coverage_report(_requirements(), _links(), _test_cases(), _results())
    assert report["failing"] == 1
    assert report["failing_requirements"] == ["REQ-2"]


def test_the_coverage_statement_offers_evidence_and_claims_no_compliance():
    report = coverage_report(_requirements(), _links(), _test_cases(), _results())
    statement = report["statement"]
    assert "evidence available for review" in statement
    assert "compliant" not in statement.lower()


def test_the_orphan_report_lists_a_requirement_without_links():
    report = orphan_report(_requirements(), _links(), _test_cases())
    assert report["orphan_requirements"] == ["REQ-3"]
    assert report["counts"]["orphan_requirements"] == 1


def test_the_orphan_report_lists_a_test_case_without_links():
    links = _links()
    cases = _test_cases() + [{"id": "TC-9", "name": "test nine", "suite": "unit"}]
    report = orphan_report(_requirements(), links, cases)
    assert "TC-9" in report["orphan_test_cases"]


def test_the_orphan_report_does_not_list_a_linked_test_case():
    # A test case that has a reviewed link is not an orphan.
    report = orphan_report(_requirements(), _links(), _test_cases())
    assert "TC-1" not in report["orphan_test_cases"]


def test_the_impact_set_contains_the_descendants():
    requirements = [
        {"id": "REQ-P", "title": "Parent"},
        {"id": "REQ-C", "title": "Child"},
        {"id": "REQ-G", "title": "Grandchild"},
        {"id": "REQ-X", "title": "Unrelated"},
    ]
    children = {"REQ-C": "REQ-P", "REQ-G": "REQ-C"}
    impact = impact_of_requirement("REQ-P", requirements, [], children)
    assert impact["requirement_id"] == "REQ-P"
    assert impact["title"] == "Parent"
    assert "REQ-C" in impact["impacted"]
    assert "REQ-G" in impact["impacted"]
    assert "REQ-X" not in impact["impacted"]
    assert "REQ-P" not in impact["impacted"]
    assert impact["count"] == len(impact["impacted"])


def test_the_impact_set_contains_the_requirements_that_share_a_test_case():
    requirements = [{"id": "REQ-1", "title": "First"}, {"id": "REQ-2", "title": "Second"}]
    links = [
        {"id": "l1", "source_type": "requirement", "source_id": "REQ-1",
         "target_type": "test_case", "target_id": "TC-1", "review_state": "approved"},
        {"id": "l2", "source_type": "requirement", "source_id": "REQ-2",
         "target_type": "test_case", "target_id": "TC-1", "review_state": "approved"},
    ]
    impact = impact_of_requirement("REQ-1", requirements, links, {})
    assert impact["impacted"] == ["REQ-2"]
