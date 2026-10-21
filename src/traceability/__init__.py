"""Requirements and test intelligence (Phase 6).

The packages here normalise requirements, ingest test results, and relate the
two through **trace links with a review state**. A machine may *propose* a
link; only a human can approve it. Nothing in this package asserts a
standard — it records the evidence that is available for review.
"""

from .matrix import (
    ACCEPTED_REVIEW_STATES,
    coverage_report,
    impact_of_requirement,
    orphan_report,
    traceability_matrix,
)
from .requirements import (
    LINK_REVIEW_STATES,
    REVIEW_STATES,
    Requirement,
    ingest_requirements,
    ingest_requirements_csv,
    ingest_requirements_json,
    normalise_requirement,
)
from .store import Finding, TraceabilityStore
from .tests import (
    TestCase,
    TestResult,
    TestRun,
    cluster_failures,
    ingest_junit_xml,
    ingest_test_results_csv,
    test_adapters,
)

__all__ = [
    "ACCEPTED_REVIEW_STATES",
    "Finding",
    "LINK_REVIEW_STATES",
    "REVIEW_STATES",
    "Requirement",
    "TestCase",
    "TestResult",
    "TestRun",
    "TraceabilityStore",
    "cluster_failures",
    "coverage_report",
    "impact_of_requirement",
    "ingest_junit_xml",
    "ingest_requirements",
    "ingest_requirements_csv",
    "ingest_requirements_json",
    "ingest_test_results_csv",
    "normalise_requirement",
    "orphan_report",
    "test_adapters",
    "traceability_matrix",
]
