# Legacy prototypes (superseded — not used by the current app)

These files are the pre-rebuild experiments, kept for reference only:

| File | What it was |
|---|---|
| `streamlit_app.py` | First Streamlit UI (Standard vs DocLong radio) |
| `docling_rag_app.py` / `docling_rag_v2.py` | TF-IDF + optional Docling UI/engine |
| `doclong_rag.py` | Parent/small-chunk hierarchical experiment |
| `pdf_rag_system.py` | Original FAISS + BM25 RAG |
| `database.py` | Original SQLite vector store (JSON-metadata fix applied before freeze) |

Nothing under `src/`, `apps/`, or `tests/` imports from here. The supported code is
`apps/streamlit/app.py` (chat UI) + `apps/api/main.py` (API) + `src/` (engine).
Do not extend these files; delete this folder once nobody needs the reference.
