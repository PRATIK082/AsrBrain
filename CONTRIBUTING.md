# Contributing to AsrBrain

Thanks for helping make AUTOSAR engineering knowledge easier to explore and verify. Contributions of all sizes are welcome: reproducible bug reports, documentation corrections, parser improvements, retrieval/evaluation cases, UI/API changes, and tests.

## Before starting

1. Search [open issues](https://github.com/PRATIK082/AsrBrain/issues) to avoid duplicates.
2. For a new capability or requirement, open a [feature/requirement request](https://github.com/PRATIK082/AsrBrain/issues/new?template=feature_request.yml) before investing in a large change.
3. For a defect, use the [bug report form](https://github.com/PRATIK082/AsrBrain/issues/new?template=bug_report.yml) and include minimal, reproducible steps.
4. For substantial changes, discuss the scope in an issue first and submit a focused pull request.

## Local checks

Use the repository's documented environment and run the checks relevant to your change:

```bash
pip install -r requirements.txt
make test
```

For benchmark, retrieval, or answer-quality changes, also run:

```bash
make eval
```

If a check cannot be run, state why in the pull request. Never report a test as passing unless you ran it.

## Contribution principles

- Keep changes focused, explain the user problem, and document any behavior or configuration changes.
- Add or update tests for bug fixes and new behavior. For retrieval or generation changes, add a small, reproducible evaluation case where practical.
- Preserve evidence provenance: when changing answer behavior, test citation correctness, source pages/identifiers, version handling, and abstention where evidence is insufficient.
- Use synthetic, public, or appropriately licensed fixtures. Do not commit proprietary AUTOSAR specification PDFs/text, OEM/customer data, confidential project files, credentials, API keys, or production ECU configurations.
- Do not claim certification, compliance, or guaranteed correctness from a successful test or a cited answer.
- Keep dependencies justified and update setup/docs when adding one.

## Pull request checklist

- [ ] The change solves a described issue or clearly explains its use case.
- [ ] Tests/evaluation were added or updated where appropriate.
- [ ] Relevant checks were run; unrun checks are identified honestly.
- [ ] Docs, examples, and configuration references are updated.
- [ ] No secrets, proprietary standards content, or customer material are included.

Maintainers review contributions as time permits. Opening an issue or PR does not guarantee acceptance, but clear scope and reproducible evidence make review easier.
