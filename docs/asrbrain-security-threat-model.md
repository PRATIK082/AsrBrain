# Security Threat Model (concise)

- Cross-tenant leakage: mitigated by mandatory `tenant_id` filter + `check_access` on every new endpoint; Qdrant/OpenSearch/graph writes must add payload filters before production (open item).
- Cloud exfiltration of ARXML/code/vendor docs: default-deny (`local_only`); cloud only on explicit policy + public classification; redaction map never leaves local boundary.
- Prompt/confidential-data disclosure (OWASP LLM06): classification before routing; no chain-of-thought in API/logs; SSE events carry status only.
- Unsafe XML: DOCTYPE/ENTITY rejected; stdlib ET without entity expansion; XPath/lineage retained for audit.
- Regex-only "compliance" claims: banned strings (`compliant|certified|qualified|ASIL compliant`) never emitted; findings carry advisory disclaimer.
- Plugin code execution: registry is contract-only; enabling is per tenant/project; no auto-load of third-party code.
