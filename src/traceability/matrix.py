"""The traceability matrix, coverage and impact (Phase 6).

The matrix answers one question in both directions: **for every requirement,
which test cases verify it — and for every test case, which requirement it
verifies.**

The language of this module is deliberately careful. A requirement that has a
test case has **evidence available for review**. It is *not* "compliant", it is
*not* "ISO 26262 verified", and nothing here ever asserts a standard. Only a
qualified human can approve a link, and only an approved link counts as
evidence.
"""
from __future__ import annotations

__all__ = [
    "coverage_report",
    "impact_of_requirement",
    "orphan_report",
    "traceability_matrix",
]

#: Link review states that count as evidence a human has looked at.
ACCEPTED_REVIEW_STATES = ("reviewed", "approved")


def _is_accepted(link: dict) -> bool:
    return str(link.get("review_state") or "") in ACCEPTED_REVIEW_STATES


def traceability_matrix(requirements: list[dict], links: list[dict],
                        test_cases: list[dict] | None = None,
                        results: list[dict] | None = None) -> dict:
    """Build the requirement ↔ test-case matrix.

    `links` are trace links with `source_type`/`source_id`/`target_type`/
    `target_id`/`review_state`.
    """
    test_cases = test_cases or []
    results = results or []
    cases_by_id = {c.get("id"): c for c in test_cases}
    latest_status: dict[str, str] = {}
    for result in results:
        case_id = result.get("test_case_id") or ""
        if case_id:
            latest_status[case_id] = str(result.get("status") or "unknown")

    # A trace link may be recorded in either direction
    # (requirement -> test_case or test_case -> requirement). Both are indexed
    # both ways, so the matrix and the orphan report see the same links.
    by_requirement: dict[str, list[dict]] = {}
    by_test: dict[str, list[dict]] = {}
    for link in links:
        src_type = str(link.get("source_type") or "")
        dst_type = str(link.get("target_type") or "")
        src_id = str(link.get("source_id") or "")
        dst_id = str(link.get("target_id") or "")
        if src_type == "requirement" and dst_type == "test_case":
            by_requirement.setdefault(src_id, []).append(link)
            by_test.setdefault(dst_id, []).append(link)
        elif src_type == "test_case" and dst_type == "requirement":
            by_requirement.setdefault(dst_id, []).append(link)
            by_test.setdefault(src_id, []).append(link)

    rows = []
    for requirement in requirements:
        req_id = str(requirement.get("id") or "")
        links_out = by_requirement.get(req_id, []) + by_test.get(req_id, [])
        accepted = [l for l in links_out if _is_accepted(l)]
        proposed = [l for l in links_out if not _is_accepted(l)]
        test_ids: list[str] = []
        for link in links_out:
            if link.get("source_type") == "requirement":
                test_ids.append(str(link.get("target_id") or ""))
            else:
                test_ids.append(str(link.get("source_id") or ""))
        test_ids = [t for t in dict.fromkeys(test_ids) if t]
        statuses = [latest_status.get(t, "unknown") for t in test_ids]
        rows.append({
            "requirement_id": req_id,
            "title": requirement.get("title", ""),
            "status": requirement.get("status", ""),
            "review_state": requirement.get("review_state", ""),
            "test_cases": [
                {"id": t, "name": (cases_by_id.get(t) or {}).get("name", ""),
                 "suite": (cases_by_id.get(t) or {}).get("suite", ""),
                 "latest_status": latest_status.get(t, "unknown")}
                for t in test_ids
            ],
            "accepted_links": len(accepted),
            "proposed_links": len(proposed),
            "evidence": "available for review" if accepted else "not yet reviewed",
        })

    reverse = []
    for case in test_cases:
        case_id = str(case.get("id") or "")
        links_in = by_test.get(case_id, [])
        accepted = [l for l in links_in if _is_accepted(l)]
        reverse.append({
            "test_case_id": case_id,
            "name": case.get("name", ""),
            "suite": case.get("suite", ""),
            "requirements": [str(l.get("source_id")) if l.get("source_type") == "requirement"
                             else str(l.get("target_id")) for l in links_in],
            "accepted_links": len(accepted),
            "evidence": "available for review" if accepted else "not yet reviewed",
        })

    return {"rows": rows, "reverse": reverse,
            "counts": {"requirements": len(requirements), "test_cases": len(test_cases),
                       "links": len(links)}}


def coverage_report(requirements: list[dict], links: list[dict],
                    test_cases: list[dict] | None = None,
                    results: list[dict] | None = None) -> dict:
    """Summarise the coverage that is **available for review**.

    The report counts what exists; it never asserts a standard and never
    reports a percentage that could be read as a compliance score.
    """
    matrix = traceability_matrix(requirements, links, test_cases, results)
    rows = matrix["rows"]
    with_accepted = [r for r in rows if r["accepted_links"] > 0]
    with_any = [r for r in rows if r["test_cases"]]
    failing = [r for r in rows
               if any(t["latest_status"] in ("failed", "error") for t in r["test_cases"])]
    return {
        "requirements": len(rows),
        "with_accepted_link": len(with_accepted),
        "with_proposed_link_only": len([r for r in rows
                                        if r["accepted_links"] == 0 and r["test_cases"]]),
        "without_any_link": len([r for r in rows if not r["test_cases"]]),
        "failing": len(failing),
        "failing_requirements": [r["requirement_id"] for r in failing],
        "statement": "evidence available for review - this is not a compliance claim; "
                     "a qualified human approves the links",
        "counts": matrix["counts"],
    }


def orphan_report(requirements: list[dict], links: list[dict],
                  test_cases: list[dict] | None = None) -> dict:
    """Requirements without a test case, and test cases without a requirement."""
    matrix = traceability_matrix(requirements, links, test_cases)
    orphan_requirements = [r["requirement_id"] for r in matrix["rows"] if not r["test_cases"]]
    orphan_tests = [r["test_case_id"] for r in matrix["reverse"] if not r["requirements"]]
    return {
        "orphan_requirements": orphan_requirements,
        "orphan_test_cases": orphan_tests,
        "counts": {"orphan_requirements": len(orphan_requirements),
                   "orphan_test_cases": len(orphan_tests)},
        "statement": "orphans are reported for review; they are not automatically "
                     "failures and they are not automatically defects",
    }


def impact_of_requirement(requirement_id: str, requirements: list[dict],
                           links: list[dict], children: dict | None = None) -> dict:
    """What else is affected when a requirement changes.

    The impact set is the requirement's descendants plus the requirements that
    share a test case with it — the two relationships the trace links record.
    """
    children = children or {}
    by_id = {str(r.get("id")): r for r in requirements}
    direct = [c for c, parent in children.items() if parent == requirement_id]
    impacted: set[str] = set(direct)

    # Descendants, transitively.
    frontier = list(direct)
    while frontier:
        current = frontier.pop()
        for child, parent in children.items():
            if parent == current and child not in impacted:
                impacted.add(child)
                frontier.append(child)

    # Requirements that share a test case with the one under change.
    by_test: dict[str, set[str]] = {}
    for link in links:
        if link.get("source_type") == "requirement" and link.get("target_type") == "test_case":
            by_test.setdefault(str(link.get("target_id")), set()).add(str(link.get("source_id")))
        elif link.get("target_type") == "requirement" and link.get("source_type") == "test_case":
            by_test.setdefault(str(link.get("source_id")), set()).add(str(link.get("target_id")))
    for case_id, req_ids in by_test.items():
        if requirement_id in req_ids:
            impacted |= (req_ids - {requirement_id})

    impacted.discard(requirement_id)
    return {
        "requirement_id": requirement_id,
        "title": (by_id.get(requirement_id) or {}).get("title", ""),
        "impacted": sorted(impacted),
        "count": len(impacted),
        "statement": "the impact set is derived from recorded trace links and the "
                     "requirement hierarchy; it is an aid for review, not a verdict",
    }
