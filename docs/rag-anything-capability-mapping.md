# RAG-Anything Capability Mapping (clean-room, no dependency)

No HKUDS/RAG-Anything code cloned, imported, or copied. Only architectural capabilities reproduced via internal interfaces.

| Required capability | Existing implementation | Missing | Planned implementation | Test |
|---|---|---|---|---|
| 1 Text processing | chunking.py, pdf_extract.py | spec TextProcessor | `processors.TextProcessor` | test_processors text |
| 2 Multi-format docs | pypdf/PyMuPDF/Docling adapters | async adapter + DOCX/XLSX | `parser_adapter.py` | test_parser_adapter |
| 3 Multi-module docs | metadata infer_module | — | reuse + planner module filter | version_routing |
| 4 Multimodal processing | tables/figures stores | unified processors | `processors.py` ×6 | test_processors |
| 5 Table processing | find_tables rows | markdown/html/json + spanning | `TableProcessor` | test_processors table |
| 6 Image processing | figures + image_path/ocr | VLM desc + entity/rel links | `ImageProcessor` | test_processors image |
| 7 Diagram processing | figure kind | diagram-vs-decorative + arrows | `DiagramProcessor` | test_processors diagram |
| 8 Equation processing | figure kind=equation | LaTeX + image + links | `EquationProcessor` | test_processors equation |
| 9 VLM-enhanced analysis | ProviderSpec | VisionProvider + routing | `routing.py` | test_routing privacy |
| 10 LLM text/table interp | complete()/prompts | task routing | `routing route_task` | test_routing tasks |
| 11 Multimodal context assembly | context.py compress | modality inclusion rules | `context_rules.py` | test_context_rules |
| 12 Multimodal KG | GraphEdge | node/rel vocab + provenance | `multimodal_graph.py` | test_graph_provenance |
| 13 Vector DB retrieval | qdrant_index.py, hybrid.py | typed collections contract | `collections.py` | test_collections |
| 14 Graph retrieval | retrieval/graph.py | cross-modal traversal | planner.needs_graph | version_routing |
| 15 Vector-graph fusion | fusion.py RRF | spec weights + modality | `modality_fusion.py` | test_modality_fusion |
| 16 Modality-aware ranking | modalities.py, reranking | planner weights | `planner.py` | test_planner |
| 17 Cross-modal retrieval | parent_expand | related_content_ids | CanonicalContent links | test_canonical |
| 18 Version-aware filtering | metadata_filter.py | exact-before-assembly | planner + verify | version_routing |
| 19 Cross-version comparison | comparison prompt | independent branches + align | planner comparison mode | test_answer comparison |
| 20 Requirement traceability | requirement_ids/api_names | shall/should/may + links | `RequirementProcessor` | test_processors req |
| 21 API/ECUC lookup | API_RE, ecu_parameters | exact keyword (no stemming) | collections EXACT_FIELDS | test_collections |
| 22 Citation-grounded answers | citations.py, prompts.py | strict prompt | STRICT_SYSTEM const | test_answer |
| 23 Claim-level validation | verification.py | spec JSON keys | `to_spec_claim()` | test_verification |
| 24 Local/cloud routing | ProviderSpec ollama/compat | privacy policy gate | `routing.check_privacy` | test_routing privacy |
| 25 Chatbox-like chat | Streamlit + React + SSE | event catalogue | chatbox-integration-plan | chat_api/history |
