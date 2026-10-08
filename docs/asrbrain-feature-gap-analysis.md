# Feature Gap Analysis → Phase 2/3 Coverage

| Capability | Before | Now | Test | Rollback |
|---|---|---|---|---|
| ARXML typed parse/graph | gap (text-only) | safe parser + models + graph projection + topology API | `test_arxml_parse_topology`, `test_arxml_rejects_doctype` | `ASRBRAIN_ARXML_ENABLED=false` |
| RBAC/tenant isolation | gap | `SecurityContext` + server-side `check_access` + per-artifact tenant filter | `test_security_tenant_denial` | remove ctx params (endpoints 404-deny) |
| Classification/cloud routing | gap | deterministic classifier + default-deny router + redaction map (local-only) | `test_policy_arxml_local_only`, `test_redaction_roundtrip` | `ASRBRAIN_STRICT_LOCAL_ONLY=true` |
| Cross-version/cross-artifact diff | gap (LLM-only) | deterministic `diff_records` + ARXML topology diff + `/api/diff` | `test_diff_records` | `ASRBRAIN_DIFF_ENABLED=false` |
| Code advisory + RTE trace | gap | preflight checks (advisory wording) + RTE call mapping + `/api/code/analyze` | `test_code_advisory_labels` | `ASRBRAIN_CODE_INTELLIGENCE_ENABLED=false` |
| Vendor plugins | gap | contract + tenant-scoped registry | `test_plugin_registry_isolation` | `ASRBRAIN_VENDOR_PLUGINS_ENABLED=false` |
| Model router | partial (provider select) | policy router, local-only tasks | `test_model_router_local_only_tasks` | fall back to direct provider |
| Enterprise prompts | gap | ARXML-to-code + migration diagnostic templates | template render covered by import | delete file |

Remaining (P2/P3 next): React ARXML Explorer/Diff Studio/Code Review UI, Qdrant/OpenSearch mandatory-filter enforcement,
VLM diagram pipeline, SARIF adapter, full eval categories B–Q.
