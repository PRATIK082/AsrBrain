"""Unit tests for test-result ingestion and failure clustering (Phase 6).

A result is a fact about a run, not a verdict about the product. The tests
pin the mapping of the CI report formats onto one model and the grouping of
failures by message shape.
"""
from src.traceability import tests as traceability_tests
from src.traceability.tests import (
    cluster_failures,
    ingest_junit_xml,
    ingest_test_results_csv,
)

# The model classes and test_adapters() are reached through the module: a
# "Test*" class or a "test_*" function in this module's namespace would be
# collected by pytest as a test class or test function.

JUNIT_XML = (
    '<testsuite name="unit" tests="3" time="0.5">'
    '<testcase classname="tests.test_a" name="test_ok" time="0.1"/>'
    '<testcase classname="tests.test_a" name="test_bad" time="0.2">'
    '<failure message="expected 1 got 2">traceback</failure>'
    "</testcase>"
    '<testcase classname="tests.test_a" name="test_skip" time="0.0">'
    '<skipped message="not now"/>'
    "</testcase>"
    "</testsuite>"
)

RESULTS_CSV = (
    "name,class,status,duration,message\n"
    "test_ok,tests.test_a,pass,120,\n"
    "test_bad,tests.test_a,fail,0.5,boom\n"
    "test_skip,tests.test_a,skip,0,pending\n"
)


def test_junit_xml_returns_cases_a_run_and_results():
    cases, run, results = ingest_junit_xml(JUNIT_XML, run_id="run-1")
    assert len(cases) == 3
    assert all(isinstance(c, traceability_tests.TestCase) for c in cases)
    assert isinstance(run, traceability_tests.TestRun)
    assert len(results) == 3
    assert all(isinstance(r, traceability_tests.TestResult) for r in results)
    assert run.id == "run-1"
    assert run.suite == "unit"
    assert cases[0].id == "tests.test_a::test_ok"


def test_a_passing_case_becomes_a_passed_result():
    _cases, _run, results = ingest_junit_xml(JUNIT_XML, run_id="run-1")
    by_name = {r.name: r for r in results}
    assert by_name["test_ok"].status == "passed"
    assert by_name["test_ok"].message == ""


def test_a_failure_becomes_a_failed_result_with_the_message():
    _cases, _run, results = ingest_junit_xml(JUNIT_XML, run_id="run-1")
    by_name = {r.name: r for r in results}
    assert by_name["test_bad"].status == "failed"
    assert by_name["test_bad"].message == "expected 1 got 2"


def test_a_skipped_case_becomes_a_skipped_result():
    _cases, _run, results = ingest_junit_xml(JUNIT_XML, run_id="run-1")
    by_name = {r.name: r for r in results}
    assert by_name["test_skip"].status == "skipped"
    assert by_name["test_skip"].message == "not now"


def test_the_run_summary_counts_add_up():
    _cases, run, results = ingest_junit_xml(JUNIT_XML, run_id="run-1")
    summary = run.summary
    assert summary["total"] == len(results) == 3
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["skipped"] == 1
    counted = (summary["passed"] + summary["failed"] + summary["skipped"]
               + summary["error"] + summary["unknown"])
    assert counted == summary["total"]


def test_csv_results_return_the_same_triple():
    cases, run, results = ingest_test_results_csv(RESULTS_CSV, run_id="run-2")
    assert len(cases) == 3
    assert isinstance(run, traceability_tests.TestRun)
    assert len(results) == 3
    assert run.id == "run-2"
    assert cases[0].id == "tests.test_a::test_ok"


def test_csv_status_aliases_are_mapped():
    _cases, _run, results = ingest_test_results_csv(RESULTS_CSV, run_id="run-2")
    by_name = {r.name: r for r in results}
    assert by_name["test_ok"].status == "passed"
    assert by_name["test_bad"].status == "failed"
    assert by_name["test_skip"].status == "skipped"
    assert by_name["test_bad"].message == "boom"


def test_the_csv_run_summary_counts_add_up():
    _cases, run, results = ingest_test_results_csv(RESULTS_CSV, run_id="run-2")
    assert run.summary["total"] == len(results) == 3
    assert run.summary["passed"] == 1
    assert run.summary["failed"] == 1
    assert run.summary["skipped"] == 1


def _failure(result_id: str, message: str, case_id: str = "") -> traceability_tests.TestResult:
    return traceability_tests.TestResult(
        id=result_id, run_id="run-1", test_case_id=case_id,
        name=result_id, status="failed", message=message)


def test_failures_with_the_same_message_shape_are_clustered():
    results = [
        _failure("r1", "Timeout after 30 seconds waiting for port 8080", "c1"),
        _failure("r2", "Timeout after 60 seconds waiting for port 9090", "c2"),
    ]
    clusters = cluster_failures(results)
    assert len(clusters) == 1
    assert clusters[0]["count"] == 2
    assert clusters[0]["test_cases"] == ["c1", "c2"]
    assert clusters[0]["key"] == "timeout after <n> seconds waiting for port <n>"


def test_cluster_failures_accepts_plain_dicts():
    # The store returns dicts, the module returns dataclasses: both are input.
    results = [
        {"id": "r1", "run_id": "run-1", "test_case_id": "c1", "name": "r1",
         "status": "failed", "message": "Timeout after 30 seconds waiting for port 8080"},
        {"id": "r2", "run_id": "run-1", "test_case_id": "c2", "name": "r2",
         "status": "failed", "message": "Timeout after 60 seconds waiting for port 9090"},
    ]
    clusters = cluster_failures(results)
    assert len(clusters) == 1
    assert clusters[0]["count"] == 2
    assert clusters[0]["test_cases"] == ["c1", "c2"]


def test_a_different_message_forms_its_own_cluster():
    results = [
        _failure("r1", "Timeout after 30 seconds waiting for port 8080", "c1"),
        _failure("r2", "Timeout after 60 seconds waiting for port 9090", "c2"),
        _failure("r3", "Null pointer dereference in handler", "c3"),
    ]
    clusters = cluster_failures(results)
    assert len(clusters) == 2
    # The bigger cluster comes first.
    assert clusters[0]["count"] == 2
    assert clusters[1]["count"] == 1
    assert clusters[1]["test_cases"] == ["c3"]


def test_only_failures_and_errors_are_clustered():
    results = [
        traceability_tests.TestResult(id="r1", run_id="run-1", status="passed", message="all good"),
        traceability_tests.TestResult(id="r2", run_id="run-1", status="skipped", message="not now"),
    ]
    assert cluster_failures(results) == []


def test_the_adapters_are_listed():
    adapters = traceability_tests.test_adapters()
    names = [a["name"] for a in adapters]
    assert names == ["junit_xml", "test_csv"]
    assert adapters[0]["extensions"] == [".xml"]
    assert adapters[1]["extensions"] == [".csv"]
    assert all(a["description"] for a in adapters)
