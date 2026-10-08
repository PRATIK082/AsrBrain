# AsrBrain Current-State Audit (Phase 2 baseline, branch `feature/enterprise-ai-orchestration-phase2-phase3`)

- Baseline tests: 41 passed, 2 pre-existing integration failures (`test_chat_api` mocked-LLM expectations; need real index/LLM).
- Existing core preserved: PDF RAG, hybrid retrieval, citations, version-aware routing, chat store, FastAPI + Streamlit, Docker.
- New additive packages (no existing behavior replaced): `src/security`, `src/ingestion/arxml`,
  `src/diff`, `src/code_intelligence`, `src/model_routing`, `src/plugins`, `src/generation/enterprise_prompts.py`.
- Feature flags (reversible): `ASRBRAIN_PIPELINE_VERSION`, `ASRBRAIN_ARXML_ENABLED`, `ASRBRAIN_DIFF_ENABLED`,
  `ASRBRAIN_CODE_INTELLIGENCE_ENABLED`, `ASRBRAIN_CLOUD_ROUTING_ENABLED`, `ASRBRAIN_STRICT_LOCAL_ONLY`,
  `ASRBRAIN_VENDOR_PLUGINS_ENABLED`.
- New endpoints: `GET /api/policies/effective`, `POST /api/arxml/upload`, `GET /api/arxml/artifacts|topology|nodes/{id}/neighbors`, `POST /api/diff`, `POST /api/code/analyze`.
- Human-in-the-loop: diff/code-review/arxml-upload responses carry warnings, unresolved refs, advisory disclaimers; approvals remain user actions in UI.
