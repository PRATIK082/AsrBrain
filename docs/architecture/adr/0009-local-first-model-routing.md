# ADR-0009 — Local-first model routing with a default-deny data policy

- **Status:** accepted
- **Date:** 2026-10-21
- **Relates to:** `docs/architecture/target-architecture.md` §6.4, §6.5

## Context

`src/security/` already contains the right primitives, and none of them are wired
into the request path:

- `SecurityContext` with tenant/project/workspace, roles, vendor scopes, data
  classification and a `cloud_policy`; `check_access()` is default-deny;
- `classify_content()` — default-deny: ARXML, source code, vendor/OEM documents and
  credentials are classified `confidential` and are **not** cloud-eligible; PII and
  private IPs likewise;
- `redact()` / `restore()` with reversible tokens (`<VIN_001>`, `<INTERNAL_IP_001>`,
  `<EMAIL_001>`, `<PROJECT_001>`) whose token map must never leave the boundary;
- `model_routing/router.py::route()` with a `LOCAL_ONLY_TASKS` set;
- `observability/logging.py::log_stage()`.

But `/api/chat` accepts a per-request `provider: "openai_compat"` with a per-request
`api_key`, and any caller can therefore push copyrighted AUTOSAR specification text
and customer ARXML to an external provider with no classification, no redaction, no
policy check and no audit record. `settings.cloud_routing_enabled` defaults to
`false` and `strict_local_only` to `true`, but **nothing reads them on the request
path**.

For an engineering tool whose corpus is licensed AUTOSAR specifications and customer
project sources, that is the highest-severity risk in the repository.

## Decision

1. **Local-first is the default and the enforcement point.** Cloud routing is
   permitted only when a tenant policy explicitly allows it *and* the content
   classification of the request permits it. `strict_local_only` and
   `cloud_routing_enabled` become effective gates on the request path, not
   documentation.
2. **Classification runs before any outbound request.** The request payload is
   classified (`classify_content`); if the classification forbids cloud egress, the
   request is either redacted (`cloud_redacted_only`) or refused with
   `NEEDS_ENGINEER_REVIEW` / `INSUFFICIENT_EVIDENCE` semantics — never silently sent.
3. **The tenant policy outranks the request.** A per-request `provider` may only
   *narrow* the allowed set; it can never widen it. `SecurityContext.cloud_policy`
   and the `ModelRoutingPolicy` table decide.
4. **The token map never crosses the boundary.** Redaction tokens are mapped back
   only in the local response.
5. **Every routing decision is auditable.** The audit trail records: task, chosen
   route, reason, classification, whether redaction was applied, model, latency.
6. **Secrets come only from configuration providers** (env / config file), never from
   code, never from logs, never from a stored request. A per-request API key stays
   in memory for that request only — as today — and is never persisted.
7. **Copyrighted specification content is never embedded** in prompts, fixtures or
   generated documents beyond allowed metadata, user content, or short original
   commentary. Test fixtures are synthetic.

## Consequences

**Positive**

- The highest-severity risk identified in the audit is closed by construction.
- Routing becomes explainable after the fact, which is what an auditor asks for.
- The existing `src/security/*` and `src/model_routing/*` code stops being dead
  weight and becomes the enforced policy.

**Negative**

- Some workflows that "worked" by sending everything to a cloud model will now be
  refused or redacted — a deliberate behaviour change, and it may surprise users.
- The security context must be plumbed through the pipeline (Phase 2–5), which is
  cross-cutting work.
- Redaction is lossy for the external call: the cloud model sees placeholders, which
  can reduce answer quality — an accepted trade for confidential data.

**Rejected alternatives**

- *Warn in the README and trust the user* — the current state; the threat model
  explicitly requires enforcement.
- *Block cloud routing entirely* — rejects the legitimate `cloud_redacted_only`
  use case that the existing policy module was written for.
- *Rely on `settings` flags alone* — flags without a code path that reads them are
  documentation, not a control.
