You are a Principal AI Architect, Search Engineer, RAG Researcher, AUTOSAR Classic and Adaptive expert, document-processing engineer, and production Python architect.

You are working on an existing Rag based AUTOSAR Knowledge ChatBot with:

- Streamlit frontend
- Python backend
- RDF-based document indexing
- PDF-based AUTOSAR specifications
- Local Ollama inference
- Existing query-to-RDF retrieval pipeline
- Current factual answer accuracy of approximately 30–35%
- Corpus size of approximately 3–5 GB of AUTOSAR PDFs
- Multiple AUTOSAR Classic and Adaptive versions
- BSW, MCAL, ECUC, requirements, SWS, architecture, APIs, configuration, integration, and troubleshooting information

The existing system must be redesigned rather than cosmetically patched.

The objective is to create a production-grade, local-first AUTOSAR Knowledge ChatBot that provides citation-grounded, version-aware, technically precise answers.

The system must support:

1. AUTOSAR Classic Platform
2. AUTOSAR Adaptive Platform
3. Multiple AUTOSAR release versions
4. BSW modules
5. MCAL modules
6. ECUC configuration
7. SWS specifications
8. Requirements documents
9. Architecture descriptions
10. API and interface information
11. Configuration parameters
12. State machines and behavioral descriptions
13. Cross-version comparison
14. Dependency analysis
15. Integration guidance
16. Troubleshooting
17. Deep technical explanations
18. Exact citations to source PDF, chapter, section, requirement, and page

Do not assume that adding a larger LLM or a better prompt will solve the problem. First diagnose whether failures are caused by:

- Incorrect PDF extraction
- Missing pages
- Incorrect section boundaries
- Table loss
- Header/footer contamination
- Requirement identifiers being separated from their text
- Version metadata errors
- Wrong document classification
- Ambiguous module names
- Poor query understanding
- Retrieval recall failure
- Reranking failure
- Context truncation
- LLM synthesis errors
- Citation mismatch
- Unsupported claims
- Incorrect confidence scoring

Do not claim that the system achieves 95% accuracy without an evaluation dataset and measured results.

---

## 1. Start with repository and data audit

Before modifying code:

1. Inspect the entire repository.
2. Identify:
   - Application entry points
   - Streamlit pages
   - Existing RDF schema
   - PDF ingestion code
   - Chunking logic
   - Embedding logic
   - Retrieval logic
   - Ollama integration
   - Docker Compose files
   - Environment variables
   - Tests
   - Existing indexes
   - Existing evaluation scripts
3. Run the current system against representative queries.
4. Produce a diagnostic report containing:
   - Current architecture
   - Current data flow
   - Current dependencies
   - Current failure modes
   - Existing reusable components
   - Components that must be replaced
5. Do not delete the existing RDF functionality until an equivalent or better replacement has been validated.

Create:

```text
docs/current-state-audit.md
docs/failure-analysis.md
docs/migration-risk-register.md
```

---

## 2. Define correctness before implementation

Create a benchmark dataset before tuning retrieval.

The benchmark must contain at least these query categories:

### A. Exact lookup

Examples:

- What is the definition of CanIf?
- What is the purpose of CanIf_Init?
- What is the meaning of CanIfCtrlDrvInitHoh?

### B. Version-specific lookup

Examples:

- Explain CanIf in AUTOSAR 4.4.
- What is the CanIf configuration in AUTOSAR 4.3?
- Explain Adaptive AUTOSAR R22-11 ara::com.

### C. Cross-version comparison

Examples:

- Compare CanIf in AUTOSAR 4.2 and 4.4.
- What changed between Classic AUTOSAR 4.3 and 4.4?
- Compare SOME/IP behavior across two releases.

### D. Module relationship

Examples:

- How does CanIf interact with CanSM?
- Which module owns PduR routing?
- What is the relationship between Com, PduR, CanIf, and CanDrv?

### E. Configuration

Examples:

- How is a CanIf controller configured?
- Which ECUC parameters are mandatory?
- What is the relationship between container and sub-container parameters?

### F. API and requirements

Examples:

- Which requirement defines CanIf_Init?
- What are the preconditions for CanIf_Transmit?
- What is the return value and error behavior of this API?

### G. Troubleshooting

Examples:

- Why does CanIf_Transmit return E_NOT_OK?
- Why is a PDU not reaching the CAN driver?
- Which configuration mismatch can cause a DET error?

### H. Deep explanation

Examples:

- Explain the complete receive path from CAN hardware to application.
- Explain the interaction between Com, PduR, CanIf, CanSM, and CanDrv.
- Explain the initialization sequence of CAN communication.

For every benchmark query, store:

```json
{
  "query_id": "q-0001",
  "question": "...",
  "expected_answer_type": "exact_lookup|version_lookup|comparison|configuration|troubleshooting|deep_explanation",
  "required_versions": ["AUTOSAR_4.4"],
  "required_platforms": ["Classic"],
  "required_modules": ["CanIf"],
  "gold_source_documents": ["..."],
  "gold_pages":,[123][124]
  "gold_sections": ["..."],
  "gold_requirement_ids": ["..."],
  "gold_claims": [
    {
      "claim": "...",
      "source": "...",
      "page": 123
    }
  ]
}
```

Do not use a language model as the only evaluator. Use manually verified gold answers for the first benchmark set.

---

## 3. Build the canonical document model

Do not use RDF as the only retrieval representation.

Retain RDF for relationships and provenance, but create a canonical document store that preserves exact text, hierarchy, tables, page boundaries, and source locations.

Use the following logical entities:

```text
Document
Release
Platform
Module
Chapter
Section
Subsection
Requirement
API
ConfigurationParameter
Table
Figure
Paragraph
Chunk
Entity
Relationship
Citation
```

Every extracted unit must have a stable identifier.

Recommended identifiers:

```text
document_id
release_id
module_id
chapter_id
section_id
subsection_id
requirement_id
api_id
parameter_id
chunk_id
page_id
```

Every chunk must preserve:

```json
{
  "chunk_id": "...",
  "document_id": "...",
  "source_pdf": "...",
  "source_sha256": "...",
  "page_start": 123,
  "page_end": 124,
  "pdf_page_index": 126,
  "printed_page_number": "118",
  "autosar_release": "4.4.0",
  "platform": "Classic",
  "module": "CanIf",
  "document_type": "SWS",
  "chapter_number": "7",
  "chapter_title": "...",
  "section_number": "7.3",
  "section_title": "...",
  "subsection_number": "7.3.2",
  "subsection_title": "...",
  "requirement_ids": ["SWS_CANIF_00001"],
  "api_names": ["CanIf_Init"],
  "ecu_parameters": [],
  "entity_tags": [],
  "parent_chunk_id": "...",
  "child_chunk_ids": [],
  "text": "...",
  "normalized_text": "...",
  "table_data": null,
  "source_locator": "pdf://document/page/123"
}
```

Never lose the original text.

Store both:

1. `raw_text`
2. `normalized_text`

Normalization may remove repeated headers and footers, but must not alter technical meaning.

---

## 4. Build a reliable PDF ingestion pipeline

Use a staged ingestion pipeline:

```text
PDF discovery
    ↓
File hashing
    ↓
PDF classification
    ↓
Text extraction
    ↓
Layout extraction
    ↓
Table extraction
    ↓
Page segmentation
    ↓
Heading detection
    ↓
Requirement/API/configuration extraction
    ↓
Hierarchy reconstruction
    ↓
Metadata enrichment
    ↓
Quality validation
    ↓
Canonical storage
    ↓
Search indexing
    ↓
Graph extraction
```

Evaluate multiple PDF extraction approaches where appropriate:

- PyMuPDF
- pdfplumber
- Unstructured
- OCR only for scanned pages
- Table extraction using a layout-aware method
- Optional multimodal page interpretation for difficult figures and tables

The ingestion pipeline must detect:

- Scanned pages
- Missing text
- Broken character encoding
- Multi-column reading-order errors
- Tables incorrectly flattened into text
- Requirement identifiers separated from descriptions
- Footers inserted into paragraphs
- Headers inserted into requirements
- Page-number inconsistencies
- Duplicate pages
- Document revisions
- Different naming conventions for the same AUTOSAR release

Produce an ingestion quality report for every PDF:

```json
{
  "source_pdf": "...",
  "sha256": "...",
  "page_count": 1000,
  "pages_with_low_text":,[12][13]
  "pages_requiring_ocr":,[3]
  "tables_detected": 86,
  "requirements_detected": 1450,
  "headings_detected": 230,
  "duplicate_pages": [],
  "extraction_warnings": [],
  "quality_score": 0.94
}
```

If a source PDF fails extraction quality checks, flag it and do not silently index it as reliable content.

---

## 5. Use AUTOSAR-aware hierarchical chunking

Do not use only:

```text
1000 tokens with 100-token overlap
```

Use structure-aware chunks.

Recommended hierarchy:

```text
Document
 └── Chapter
      └── Section
           └── Subsection
                ├── Requirement
                ├── API
                ├── Configuration parameter
                ├── State-machine description
                ├── Table
                └── Paragraph
```

Create multiple searchable representations:

### Representation 1: Atomic chunk

Used for precise retrieval.

Examples:

- One requirement
- One API description
- One parameter description
- One state transition
- One table row group

### Representation 2: Context chunk

Used for answer synthesis.

Contains:

- Section heading
- Parent heading
- Several related paragraphs
- Associated table
- Requirement identifier
- Page range

### Representation 3: Parent chunk

Used when several atomic chunks from the same section are retrieved.

Contains the complete relevant section or subsection.

### Representation 4: Document summary

Contains:

- Document title
- Release
- Platform
- Module
- Document type
- Chapter list
- Main concepts
- API list
- Requirement ranges

Use parent-child retrieval or auto-merging retrieval. Hierarchical retrieval systems are designed to retrieve small leaf nodes and then merge them into larger parent contexts when multiple related children are found. [18]

Do not pass unrelated parent sections to the LLM. Parent expansion must be limited by section, module, version, and token budget.

---

## 6. Create strict metadata and version normalization

Build a release-normalization table.

Examples:

```text
AUTOSAR 4.2.2
AUTOSAR 4.3.0
AUTOSAR 4.3.1
AUTOSAR 4.4.0
R19-11
R20-11
R21-11
R22-11
R23-11
```

Represent releases with structured fields:

```json
{
  "release_family": "Classic_4.x",
  "release_label": "4.4.0",
  "release_year": null,
  "platform": "Classic",
  "major": 4,
  "minor": 4,
  "patch": 0
}
```

For Adaptive:

```json
{
  "release_family": "Adaptive_R",
  "release_label": "R22-11",
  "release_year": 2022,
  "platform": "Adaptive"
}
```

The query parser must distinguish:

- Exact release
- Release family
- Version range
- Latest release
- Multiple explicit releases
- No release specified

Examples:

```text
"CanIf in AUTOSAR 4.4"
→ exact_release = ["4.4.0"], platform = Classic

"Difference between 4.2 and 4.4"
→ comparison_releases = ["4.2.x", "4.4.x"]

"Adaptive SOME/IP"
→ platform = Adaptive

"all versions of CanIf"
→ release_constraint = none, comparison_mode = enabled
```

Never silently answer a version-specific question using another version.

If the requested release is not available, explicitly say:

```text
The requested AUTOSAR release was not found in the indexed corpus.
Available releases are: ...
```

---

## 7. Select the search architecture

Use a hybrid architecture with separate responsibilities.

Recommended production-local architecture:

```text
Canonical document store:
    PostgreSQL or DuckDB/Parquet

Keyword search:
    OpenSearch or Elasticsearch
    alternatively Qdrant BM25 for a simpler deployment

Vector search:
    Qdrant

Graph:
    Neo4j or Apache AGE/PostgreSQL
    RDF may remain as a provenance/semantic layer

Workflow:
    LangGraph or a typed Python state machine

LLM:
    Ollama

Frontend:
    Streamlit

API:
    FastAPI

Observability:
    OpenTelemetry, structured logs, Langfuse or local tracing

Evaluation:
    custom benchmark runner + Ragas/DeepEval-style metrics
```

For a fully local Docker deployment, initially prefer:

```text
FastAPI
Streamlit
Qdrant
OpenSearch
PostgreSQL
Neo4j
Ollama
Redis
```

If operational complexity is too high, implement in phases:

### Phase 1

```text
PostgreSQL
Qdrant
Ollama
FastAPI
Streamlit
```

Use Qdrant for dense vectors, BM25 sparse vectors, filters, and reranking.

### Phase 2

Add OpenSearch for stronger full-text search, field weighting, exact phrase search, fuzzy matching, and search experimentation.

### Phase 3

Add Neo4j or a graph layer for module, API, requirement, configuration, and dependency traversal.

Do not introduce Neo4j before basic document quality, metadata filtering, and retrieval evaluation are working.

Qdrant supports dense, sparse BM25, RRF fusion, and late-interaction reranking in a single multi-stage retrieval design. [2] OpenSearch supports hybrid keyword and neural queries and provides experimentation over normalization, combination methods, weights, and RRF parameters. [22]

---

## 8. Implement query understanding with structured output

Create a typed query-understanding schema:

```python
class QueryPlan(BaseModel):
    original_query: str
    normalized_query: str
    intent: Literal[
        "definition",
        "api_lookup",
        "requirement_lookup",
        "configuration",
        "comparison",
        "dependency",
        "architecture",
        "troubleshooting",
        "sequence",
        "state_machine",
        "deep_explanation",
        "unknown"
    ]
    platforms: list[str]
    modules: list[str]
    releases: list[str]
    release_mode: Literal[
        "none",
        "exact",
        "family",
        "comparison",
        "range",
        "latest"
    ]
    document_types: list[str]
    api_names: list[str]
    requirement_ids: list[str]
    configuration_parameters: list[str]
    entities: list[str]
    constraints: list[str]
    expected_evidence: list[str]
    needs_graph_search: bool
    needs_comparison_table: bool
    confidence: float
```

The query planner must identify AUTOSAR aliases.

Examples:

```text
CanIf → CAN Interface
PduR → PDU Router
CanDrv → CAN Driver
Com → AUTOSAR COM
ECUC → ECU Configuration
SWS → Software Specification
```

It must not over-normalize ambiguous terms. Preserve the original query terms for BM25 search.

The query planner must return structured JSON only.

---

## 9. Implement query rewriting and controlled expansion

Generate multiple retrieval queries, but do not allow uncontrolled hallucinated expansions.

For every query, produce:

```json
{
  "original_query": "...",
  "lexical_queries": [
    "...",
    "..."
  ],
  "semantic_queries": [
    "...",
    "..."
  ],
  "entity_queries": [
    "..."
  ],
  "requirement_queries": [
    "..."
  ],
  "comparison_queries": [
    "...",
    "..."
  ]
}
```

Expansion sources must include:

1. AUTOSAR module alias dictionary
2. API registry
3. Requirement registry
4. ECUC parameter registry
5. Known interface names
6. Ontology/graph relationships
7. LLM-generated expansions only after schema validation

Never expand “CanIf” into unrelated modules merely because an LLM associates them.

---

## 10. Implement multi-stage retrieval

The retrieval pipeline must be:

```text
User query
  ↓
Query understanding
  ↓
Version/platform/module filters
  ↓
Exact metadata retrieval
  ↓
BM25 retrieval
  ↓
Dense vector retrieval
  ↓
Optional graph retrieval
  ↓
RRF or weighted fusion
  ↓
Cross-encoder or late-interaction reranking
  ↓
Deduplication
  ↓
Parent-child expansion
  ↓
Context compression
  ↓
Evidence sufficiency check
  ↓
Answer generation
  ↓
Claim extraction
  ↓
Citation verification
  ↓
Final answer or abstention
```

Recommended initial candidate counts:

```text
Exact metadata lookup: 20
BM25: 50
Dense: 50
Graph: 20
Fusion pool: 80–120 unique chunks
Reranking pool: 40–80 chunks
Final evidence: 8–20 chunks
```

Tune these values using the benchmark, not intuition.

---

## 11. Implement metadata filtering before semantic retrieval

For exact release queries, apply hard filters before vector search.

Example:

```python
Filter(
    must=[
        FieldCondition(
            key="platform",
            match=MatchValue(value="Classic")
        ),
        FieldCondition(
            key="autosar_release",
            match=MatchValue(value="4.4.0")
        ),
        FieldCondition(
            key="module",
            match=MatchValue(value="CanIf")
        )
    ]
)
```

For a comparison query:

```python
release_filter = [
    "4.2.2",
    "4.4.0"
]
```

Retrieve both releases independently first.

Do not retrieve a mixed pool and ask the LLM to separate versions afterward.

For cross-version comparisons, enforce:

```text
each release must have independent evidence
each factual difference must cite both versions where applicable
missing evidence for one release must be reported
```

---

## 12. Implement lexical, dense, and graph search

### Dense retrieval

Evaluate at least:

- BGE-M3
- E5-large-v2
- Jina embeddings
- Nomic embeddings
- Qwen3 Embedding models where hardware permits

Do not select an embedding model by reputation. Evaluate each against the AUTOSAR benchmark.

### Sparse retrieval

Use BM25 for:

- Requirement identifiers
- API names
- ECUC parameter names
- Module names
- Exact error codes
- Configuration container names
- CamelCase and underscore tokens
- Numeric identifiers
- Version labels

Preserve technical tokenization. Generic stemming can damage tokens such as:

```text
CanIf_Init
CanIfController
SWS_CANIF_00001
CanIfTxPduCfg
E_NOT_OK
R22-11
```

Configure analyzers for:

- CamelCase splitting
- underscore preservation
- hyphen preservation
- exact keyword fields
- normalized keyword fields
- phrase matching
- identifier matching

### Graph retrieval

Extract entities and relationships:

```text
CanIf
  depends_on → CanDrv
  interacts_with → CanSM
  routes_through → PduR
  implements → CanIf_Init
  configured_by → CanIfCtrlCfg
  satisfies → SWS_CANIF_00001
```

Graph retrieval must answer relationship questions, but it must not replace source-document evidence.

Every graph edge must preserve:

```json
{
  "subject": "...",
  "predicate": "...",
  "object": "...",
  "source_chunk_id": "...",
  "source_pdf": "...",
  "page": 123,
  "release": "4.4.0"
}
```

---

## 13. Implement fusion and reranking

Use Reciprocal Rank Fusion initially:

```text
RRF(d) = Σ 1 / (k + rank_i(d))
```

Evaluate different:

```text
k ∈ {10, 20, 40, 60}
```

Evaluate weighted fusion for query types:

```text
Exact identifier query:
    BM25 0.65
    Dense 0.20
    Graph 0.15

Conceptual query:
    BM25 0.25
    Dense 0.55
    Graph 0.20

Dependency query:
    BM25 0.25
    Dense 0.25
    Graph 0.50

Configuration query:
    BM25 0.50
    Dense 0.25
    Graph 0.25
```

These are starting points only. Tune them using held-out judgments.

Use a reranker on only the candidate pool, not the complete corpus.

Evaluate:

- BGE reranker v2 M3
- Qwen3 reranker
- Cross-encoder models compatible with local GPU/CPU execution
- Qdrant late-interaction/ColBERT-style reranking where practical

A reranker receives a query-document pair and directly scores relevance, which is more precise than relying only on independent document/query embeddings. [38]

Use a two-stage ranking strategy:

```text
Stage 1: high-recall retrieval
Stage 2: expensive high-precision reranking
```

---

## 14. Implement parent-child context expansion

After reranking:

1. Group results by section and document.
2. Detect multiple hits in the same parent section.
3. Expand only related parents.
4. Preserve release and module filters.
5. Remove duplicate text.
6. Keep page and requirement boundaries.
7. Keep tables associated with their headings.
8. Keep API descriptions associated with preconditions, parameters, return values, and errors.

For every final context item, include:

```text
[Evidence ID]
Document:
AUTOSAR release:
Platform:
Module:
Document type:
Chapter:
Section:
Requirement:
Pages:
Text:
```

---

## 15. Implement context compression

Context compression must be evidence-preserving.

It may:

- Remove repeated headers
- Remove duplicate paragraphs
- Remove unrelated examples
- Select relevant sentences
- Preserve requirement identifiers
- Preserve conditions and exceptions
- Preserve “shall”, “should”, “may”, and “shall not”
- Preserve tables and parameter values
- Preserve page locations

It must not:

- Rewrite normative language
- Combine statements from different releases
- Remove negations
- Remove preconditions
- Remove exception behavior
- Merge different modules
- Merge different configuration scopes

For normative AUTOSAR text, prefer extractive compression over abstractive summarization.

---

## 16. Build a citation-grounded answer format

Every final answer must contain citations in this format:

```text
 Source: AUTOSAR_SWS_CANIF_4.4.0.pdf[4]
    Release: AUTOSAR Classic 4.4.0
    Module: CanIf
    Chapter: 7
    Section: 7.3.2
    Pages: 118–120
    Requirement: SWS_CANIF_00001
    Evidence ID: chunk-abc123
```

The UI should render clickable citations that open:

- PDF document
- Page number
- Highlighted text where technically possible

For normal questions, answer using:

```text
## Direct answer

...

## Technical explanation

...

## Configuration or integration details

...

## Version notes

...

## Sources

 ...[4]
 ...[1]
```

For comparisons, use a table:

| Topic | AUTOSAR 4.2 | AUTOSAR 4.4 | Evidence |
|---|---|---|---|
| ... | ... | ... | [1][2] |

Do not cite a document merely because it was retrieved. A citation is valid only when the cited passage supports the claim.

---

## 17. Implement claim-level answer verification

Before returning an answer:

1. Extract atomic claims from the draft answer.
2. Map each claim to one or more evidence chunks.
3. Check whether the evidence entails the claim.
4. Check version consistency.
5. Check platform consistency.
6. Check module consistency.
7. Check that all comparison claims have evidence for both sides.
8. Check that every factual claim has a citation.
9. Check for unsupported inferred behavior.
10. Check for conflicts between retrieved sources.

Use a structured verification schema:

```json
{
  "claim": "...",
  "supported": true,
  "support_score": 0.94,
  "evidence_ids": ["chunk-abc123"],
  "version_consistent": true,
  "platform_consistent": true,
  "citation_valid": true,
  "risk": "low"
}
```

If any high-risk claim is unsupported:

```text
Remove the claim
or
mark it as uncertain
or
retrieve additional evidence
```

The final answer must never contain unsupported technical facts simply because the LLM considers them likely.

---

## 18. Implement abstention and retrieval retry

Do not use a confidence score that is merely the LLM’s self-reported confidence.

Compute confidence from multiple signals:

```text
retrieval quality
metadata match
reranker score
evidence coverage
citation coverage
version consistency
cross-document agreement
answer verifier score
```

Example:

```python
confidence = (
    0.25 * retrieval_score +
    0.20 * metadata_match_score +
    0.20 * evidence_coverage +
    0.15 * citation_coverage +
    0.10 * version_consistency +
    0.10 * verifier_score
)
```

Use calibrated thresholds:

```text
High:
    evidence coverage >= 0.90
    citation coverage >= 0.95
    no version conflict
    confidence >= calibrated threshold

Medium:
    evidence coverage >= 0.70
    confidence >= calibrated threshold

Low:
    insufficient evidence or unresolved conflict
```

When evidence is insufficient:

```text
I could not verify this answer from the indexed AUTOSAR documents.

Missing evidence:
- release: AUTOSAR 4.4.0
- module: CanIf
- requested topic: CanIfController configuration

Available evidence:
...
```

Then attempt one controlled retrieval refinement:

1. Add exact identifiers.
2. Search parent sections.
3. Search related requirements.
4. Search both module and interface names.
5. Search graph neighbors.
6. Retry only once or twice.
7. Abstain if evidence remains insufficient.

---

## 19. Implement specialized query workflows

Do not force all questions through one generic chain.

### Workflow A: Exact lookup

```text
query parser
→ exact BM25
→ metadata filter
→ rerank
→ answer with citation
```

### Workflow B: Conceptual explanation

```text
query parser
→ dense + BM25
→ parent expansion
→ rerank
→ answer synthesis
→ claim verification
```

### Workflow C: Version comparison

```text
parse releases
→ retrieve independently per release
→ align concepts
→ identify additions/removals/renames/behavior changes
→ verify each difference
→ comparison table
```

### Workflow D: Dependency analysis

```text
entity extraction
→ graph traversal
→ source-document verification
→ dependency explanation
```

### Workflow E: Configuration guidance

```text
module detection
→ ECUC parameter retrieval
→ container hierarchy retrieval
→ constraints and defaults
→ related APIs/requirements
→ configuration procedure
```

### Workflow F: Troubleshooting

```text
extract symptom
→ identify error/API/module
→ search exact terms
→ graph dependency traversal
→ retrieve preconditions and failure behavior
→ generate diagnostic sequence
→ cite each diagnostic step
```

### Workflow G: Deep architecture explanation

```text
decompose into subquestions
→ parallel retrieval by module/interface
→ graph relationship retrieval
→ retrieve lifecycle/state-machine sections
→ synthesize ordered explanation
→ verify every stage
```

LangGraph is suitable for these typed workflows because it supports structured workflow routing, parallel workers, persistence, streaming, debugging, and evaluator-optimizer loops. [23]

---

## 20. Do not overuse autonomous agents

Use deterministic workflows for predictable stages:

- Version parsing
- Metadata filtering
- Retrieval
- Fusion
- Reranking
- Citation verification
- Evaluation

Use agents only for bounded decisions:

- Query decomposition
- Selecting specialized retrieval tools
- Deciding whether graph traversal is needed
- Detecting insufficient evidence
- Asking for clarification
- Planning a deep explanation

Do not allow an autonomous agent to:

- Invent document metadata
- Modify the index without validation
- Ignore version filters
- Replace evidence with general knowledge
- Produce uncited claims
- Decide that an unsupported answer is acceptable

---

## 21. Model and hardware strategy

Support local Ollama models through a configurable interface.

Create:

```text
LLM_MODEL=...
EMBEDDING_MODEL=...
RERANKER_MODEL=...
OLLAMA_BASE_URL=...
```

Evaluate answer-generation models separately from retrieval models.

For answer generation, benchmark available local models such as:

- Qwen family
- DeepSeek family
- Llama family
- Other Ollama-compatible instruction models

Do not assume a larger model always improves accuracy. A smaller model with excellent retrieval and strict citation verification can outperform a larger model with noisy context.

For local deployment:

```text
CPU-only:
    smaller embedding model
    BM25
    small reranker
    7B–14B answer model

Single GPU:
    medium embedding model
    cross-encoder reranker
    14B–32B answer model

Large GPU or multi-GPU:
    larger reranker
    30B–70B answer model
```

Use quantization only after measuring whether it harms:

- Requirement interpretation
- Version distinction
- Negation handling
- Configuration constraints
- Citation correctness

---

## 22. Build evaluation metrics

Separate retrieval metrics from answer metrics.

### Retrieval metrics

Measure:

```text
Recall@1
Recall@5
Recall@10
Recall@20
MRR
nDCG
Precision@k
Hit rate
Version-filter precision
Module-filter precision
Requirement retrieval accuracy
```

### Context metrics

Measure:

```text
Context precision
Context recall
Parent-context usefulness
Duplicate-context ratio
Noise ratio
Page citation coverage
```

### Answer metrics

Measure:

```text
Faithfulness
Claim support rate
Citation precision
Citation recall
Answer relevancy
Version correctness
Platform correctness
Comparison correctness
Abstention correctness
```

### Operational metrics

Measure:

```text
p50 latency
p95 latency
embedding latency
BM25 latency
reranking latency
LLM generation latency
GPU memory
RAM
index size
cache hit rate
```

A reported “95% accuracy” must define exactly which metric it means.

Create an evaluation report:

```text
reports/evaluation/
    baseline.json
    hybrid.json
    reranked.json
    graph.json
    validated.json
    comparison.md
```

---

## 23. Create ablation experiments

Run these experiments:

```text
A. Existing RDF retrieval
B. Dense retrieval only
C. BM25 only
D. Dense + BM25
E. Dense + BM25 + RRF
F. Dense + BM25 + reranker
G. Version filtering + hybrid retrieval
H. Hierarchical retrieval + reranker
I. Graph + hybrid retrieval
J. Hybrid + reranker + verification
```

For every experiment, report:

```text
Recall@10
MRR
Faithfulness
Citation precision
Version accuracy
Latency
Memory
```

Do not add GraphRAG or agents if they do not improve the benchmark.

---

## 24. Design the target folder structure

Create a clean structure similar to:

```text
autosar-ChatBot/
├── apps/
│   ├── api/
│   └── streamlit/
├── src/
│   ├── config/
│   ├── ingestion/
│   │   ├── discovery.py
│   │   ├── hashing.py
│   │   ├── pdf_extract.py
│   │   ├── layout_extract.py
│   │   ├── table_extract.py
│   │   ├── hierarchy.py
│   │   ├── requirements.py
│   │   ├── api_parser.py
│   │   ├── ecuс_parser.py
│   │   └── quality.py
│   ├── schema/
│   │   ├── documents.py
│   │   ├── chunks.py
│   │   ├── graph.py
│   │   └── queries.py
│   ├── indexing/
│   │   ├── qdrant_index.py
│   │   ├── opensearch_index.py
│   │   ├── postgres_store.py
│   │   └── graph_index.py
│   ├── retrieval/
│   │   ├── query_understanding.py
│   │   ├── query_rewriting.py
│   │   ├── metadata_filter.py
│   │   ├── bm25.py
│   │   ├── dense.py
│   │   ├── graph.py
│   │   ├── fusion.py
│   │   ├── reranking.py
│   │   ├── parent_child.py
│   │   └── compression.py
│   ├── workflows/
│   │   ├── exact_lookup.py
│   │   ├── comparison.py
│   │   ├── troubleshooting.py
│   │   ├── configuration.py
│   │   ├── deep_explanation.py
│   │   └── graph.py
│   ├── generation/
│   │   ├── prompts.py
│   │   ├── answer.py
│   │   ├── citations.py
│   │   └── verification.py
│   ├── evaluation/
│   │   ├── datasets.py
│   │   ├── retrieval_metrics.py
│   │   ├── answer_metrics.py
│   │   ├── ablation.py
│   │   └── reports.py
│   └── observability/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── retrieval/
│   └── evaluation/
├── data/
│   ├── raw/
│   ├── canonical/
│   ├── indexes/
│   └── benchmarks/
├── docker/
├── docker-compose.yml
├── .env.example
├── Makefile
└── README.md
```

Correct any typo in the generated structure before implementation.

---

## 25. Docker deployment

Create Docker Compose services for:

```text
api
streamlit
qdrant
opensearch
postgres
neo4j
ollama
redis
```

Use profiles so that the minimal deployment can run without every service:

```text
minimal:
    api
    streamlit
    qdrant
    ollama

standard:
    minimal
    postgres
    opensearch

full:
    standard
    neo4j
    redis
```

Provide:

```text
health checks
persistent volumes
GPU configuration
resource limits
restart policies
network isolation
environment configuration
backup instructions
index rebuild instructions
migration instructions
```

Do not store source PDFs inside Docker images.

---

## 26. Streamlit interface requirements

The frontend must expose:

- Query input
- Release selector
- Platform selector
- Module selector
- Document type selector
- Search mode
- Exact lookup mode
- Comparison mode
- Deep analysis mode
- Show retrieved evidence
- Show graph path
- Show confidence
- Show citations
- Show page previews
- Feedback buttons
- “Report incorrect answer”
- Export answer with citations

The UI must display the retrieval trace:

```text
Query plan
Applied filters
Retrieved candidates
Reranked evidence
Selected context
Answer verification
Final confidence
```

Make the trace collapsible so normal users are not overwhelmed.

---

## 27. Migration plan from the current RDF system

Create a non-destructive migration:

### Step 1

Freeze the current system and record baseline metrics.

### Step 2

Export RDF entities and relationships.

### Step 3

Map RDF nodes to canonical document IDs.

### Step 4

Retain RDF edges as graph relationships.

### Step 5

Re-extract PDFs into the canonical hierarchy.

### Step 6

Validate page-level and requirement-level alignment.

### Step 7

Create Qdrant dense and sparse indexes.

### Step 8

Create OpenSearch indexes if enabled.

### Step 9

Create graph indexes.

### Step 10

Run old and new systems against the same benchmark.

### Step 11

Enable shadow mode.

### Step 12

Compare outputs and citations.

### Step 13

Switch traffic gradually.

Do not discard RDF until the graph and provenance replacement has passed regression tests.

---

## 28. Required implementation behavior

When modifying the repository:

1. Explain the planned change before applying it.
2. Make small, verifiable commits or stages.
3. Do not rewrite unrelated code.
4. Preserve existing working functionality.
5. Add tests for every new retrieval component.
6. Add fixtures for version-specific documents.
7. Add deterministic mocks for Ollama.
8. Never silently ignore extraction errors.
9. Never silently mix releases.
10. Never return an uncited technical answer.
11. Never claim an accuracy percentage without benchmark evidence.
12. Never replace a failed retrieval stage with unsupported LLM knowledge.
13. Log every stage of the retrieval process.
14. Make model selection configurable.
15. Make index rebuilds reproducible.

---

## 29. Required deliverables

Produce the following:

```text
1. Current-state audit
2. Failure analysis
3. Target architecture document
4. Architecture diagram
5. Data model
6. Canonical metadata schema
7. PDF ingestion pipeline
8. Hierarchical chunking implementation
9. Qdrant index implementation
10. BM25 implementation
11. Optional OpenSearch implementation
12. Graph extraction implementation
13. Query-understanding schema
14. Version-routing workflow
15. Hybrid retrieval implementation
16. RRF implementation
17. Reranker integration
18. Parent-child context expansion
19. Context compression
20. Answer generator
21. Claim-level verifier
22. Citation validator
23. Confidence and abstention logic
24. Benchmark dataset format
25. Evaluation runner
26. Ablation experiments
27. Docker Compose files
28. Streamlit UI updates
29. Migration plan
30. Operations guide
31. Troubleshooting guide
32. Test suite
```

At the end, report:

```text
Implemented
Partially implemented
Blocked
Needs human validation
Known limitations
Measured benchmark results
Next highest-value improvement
```

Do not report a target accuracy as an achieved accuracy unless it was measured on the benchmark.