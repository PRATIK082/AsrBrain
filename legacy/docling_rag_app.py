import streamlit as st
import os
import sys
from datetime import datetime

st.set_page_config(
    page_title="Docling RAG - Technical Document Search",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

from docling_rag_v2 import DoclingRAG, generate_response, check_ollama_connection

if "rag_system" not in st.session_state:
    st.session_state.rag_system = None
if "index_built" not in st.session_state:
    st.session_state.index_built = False
if "ollama_checked" not in st.session_state:
    st.session_state.ollama_checked = False
    ollama_available, ollama_msg = check_ollama_connection()
    st.session_state.ollama_available = ollama_available
    st.session_state.ollama_msg = ollama_msg
    st.session_state.ollama_checked = True


def initialize_rag():
    if st.session_state.rag_system is None:
        with st.spinner("Initializing Docling RAG system..."):
            st.session_state.rag_system = DoclingRAG(
                db_path="docling_rag.db",
                chunk_size=500,
                overlap=100,
                embedding_dim=10000,
                top_k=5,
            )
    return st.session_state.rag_system


def process_pdfs(rag_system: DoclingRAG, folder_path: str = "pdf"):
    if not os.path.exists(folder_path):
        st.error(f"Folder '{folder_path}' not found!")
        return None

    with st.spinner(
        "Processing PDF documents... This may take a while for large documents."
    ):
        result = rag_system.process_folder(folder_path)

    return result


st.title("📚 Docling RAG - Technical Document Search")

st.markdown("""
**RAG System for Technical & Research Documents**

This system uses:
- **Docling** - Advanced PDF processing and document understanding
- **TF-IDF Embeddings** - Optimized for technical and research documents  
- **Hybrid Search** - Combines semantic similarity with keyword matching
- **NumPy** - Fast vector similarity search (no FAISS required)
""")

if not st.session_state.get("ollama_available", True):
    st.error(
        f"⚠️ Ollama Connection Error: {st.session_state.get('ollama_msg', 'Unknown error')}\n\nMake sure Ollama is running and the model is downloaded."
    )
else:
    st.success("✅ Ollama connected")

with st.sidebar:
    st.header("⚙️ Configuration")

    st.subheader("Indexing Settings")
    chunk_size = st.slider("Chunk Size", 200, 1000, 500, help="Size of text chunks")
    overlap = st.slider("Overlap", 0, 200, 100, help="Overlap between chunks")
    embedding_dim = st.slider("Embedding Dimensions", 5000, 20000, 10000, step=1000)

    st.subheader("Search Settings")
    top_k = st.slider("Top K Results", 1, 20, 5)
    search_mode = st.radio(
        "Search Mode",
        ["Hybrid (Semantic + Keyword)", "Semantic Only", "Keyword Only"],
        help="Hybrid combines semantic similarity with keyword matching",
    )

    st.subheader("LLM Settings")
    llm_model = st.selectbox(
        "LLM Model",
        ["qwen3:14b", "qwen3:8b", "llama3:8b", "mistral:7b", "phi3:14b"],
        index=0,
    )

    st.subheader("PDF Folder")
    pdf_folder = st.text_input("PDF Folder Path", "pdf")

    st.subheader("Actions")
    force_reprocess = st.checkbox(
        "Force Reprocess All", value=False, help="Re-process all PDFs even if unchanged"
    )

    if st.button("🔄 Process PDFs", type="primary"):
        if st.session_state.rag_system:
            with st.spinner("Processing PDF documents..."):
                result = st.session_state.rag_system.process_folder(
                    pdf_folder, force_reprocess=force_reprocess
                )
            if result:
                st.session_state.index_built = True
                st.success(
                    f"New: {result.get('new_files', 0)}, Skipped: {result.get('skipped', 0)}, Deleted: {result.get('deleted_files', 0)}"
                )
                if result.get("failed"):
                    st.warning(f"Failed: {len(result['failed'])} files")

    if st.button("🔍 Build Search Index"):
        if st.session_state.rag_system:
            with st.spinner("Building search index..."):
                st.session_state.rag_system.build_index()
                st.session_state.index_built = True
            st.success("Index built successfully!")

    if st.session_state.rag_system:
        doc_count = st.session_state.rag_system.database.get_document_count()
        processed_files = st.session_state.rag_system.database.get_processed_files()
        st.info(f"📄 {len(processed_files)} PDFs indexed | {doc_count} chunks")

rag = initialize_rag()

if not st.session_state.index_built:
    with st.spinner("Building search index from database..."):
        try:
            rag.build_index()
            st.session_state.index_built = True
            st.success("Index ready!")
        except Exception as e:
            st.warning(f"No index found. Process some PDFs first. Error: {e}")

st.divider()

col1, col2 = st.columns([2, 1])

with col1:
    query = st.text_input(
        "🔎 Search Query",
        placeholder="Enter your question about the documents...",
        help="Ask questions about the content of your PDF documents",
    )

with col2:
    st.write("")
    st.write("")
    search_button = st.button("Search", type="primary", use_container_width=True)

if search_button and query:
    if not st.session_state.index_built:
        st.error("Please build the index first by processing PDFs!")
    else:
        with st.spinner("Searching documents..."):
            use_hybrid = "Hybrid" in search_mode

            if "Keyword" in search_mode:
                results = rag.hybrid_search(
                    query, top_k=top_k, semantic_weight=0.3, keyword_weight=0.7
                )
            elif "Semantic" in search_mode:
                results = rag.search(query, top_k=top_k)
            else:
                results = rag.hybrid_search(query, top_k=top_k)

        if results:
            st.success(f"Found {len(results)} relevant passages")

            st.subheader("📄 Generated Answer")

            if st.session_state.get("ollama_available", False):
                with st.spinner("Generating answer with LLM..."):
                    response_data = generate_response(
                        query, rag, llm_model=llm_model, use_hybrid=use_hybrid
                    )
                st.markdown(response_data.get("response", "No response generated"))
            else:
                st.warning("Ollama not available. Showing search results only.")
                for i, result in enumerate(results, 1):
                    st.markdown(f"**{i}. Relevance: {result['score']:.2%}**")
                    st.text(
                        result["text"][:500] + "..."
                        if len(result["text"]) > 500
                        else result["text"]
                    )
                    st.markdown("---")

            with st.expander("View Source Passages"):
                st.subheader("📚 Source Documents")
                for i, result in enumerate(results, 1):
                    st.markdown(f"**Result {i}** (Relevance: {result['score']:.2%})")
                    st.markdown(
                        f"📁 *{result['metadata'].get('file_path', 'Unknown')}*"
                    )
                    st.markdown("---")
                    st.text(result["text"])
                    st.markdown("---")
        else:
            st.warning(
                "No relevant documents found. Try a different query or process more documents."
            )

st.divider()

with st.expander("ℹ️ About This System"):
    st.markdown("""
    ### Docling RAG System
    
    This is a lightweight RAG (Retrieval Augmented Generation) system optimized for:
    
    - **Technical Documentation** - Manuals, specifications, API docs
    - **Research Papers** - Academic papers, technical reports
    - **Scientific Articles** - Papers with complex terminology
    
    ### Key Features:
    
    1. **Docling Integration** - Uses state-of-the-art document processing
    2. **TF-IDF Embeddings** - No GPU required, works great for technical text
    3. **Hybrid Search** - Combines semantic understanding with keyword precision
    4. **NumPy Vector Search** - Fast similarity search without FAISS
    
    ### No Heavy Dependencies:
    - ❌ No PyTorch
    - ❌ No CUDA required
    - ❌ No sentence-transformers
    - ❌ No FAISS
    - ✅ Pure Python + NumPy + Scikit-learn (optional)
    """)

current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"Last updated: {current_time}")
