# Phase 2/3 Migration + Rollback Plan

1. Snapshot DB/indexes/config; record baseline (41 passed / 2 pre-existing fails).
2. Deploy branch with all flags default-safe (`STRICT_LOCAL_ONLY=true`, `CLOUD_ROUTING=false`).
3. Backfill small ARXML + PDF sample; exercise `/api/arxml/*`, `/api/diff`, `/api/code/analyze`.
4. Shadow-compare old vs new chat answers; run cross-tenant denial + routing policy tests.
5. Enable per-flag rollout; keep old RDF/index path until validation passes.
6. Rollback: set `ASRBRAIN_ARXML_ENABLED=false`, `ASRBRAIN_DIFF_ENABLED=false`,
   `ASRBRAIN_CODE_INTELLIGENCE_ENABLED=false`, or checkout `feature/multimodal-rag-chatbox-upgrade`; no existing tables were mutated.
