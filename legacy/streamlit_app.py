import streamlit as st
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import torch
from pdf_rag_system import (
    VectorDatabase,
    retrieve_relevant_chunks,
    db,
    has_file_been_processed,
    get_existing_vectors_and_chunks,
    process_pdf,
    split_text_into_chunks,
    create_embeddings_and_index,
    generate_response,
    load_vectors_from_database,
    create_faiss_index_from_database,
)
from doclong_rag import (
    DocLongRAG,
    db_doclong,
    process_all_pdfs_doclong,
    query_doclong,
    initialize_doclong_database,
)
import os

import ollama

llm = ollama

st.set_page_config(page_title="PDF RAG System - Query Interface", layout="wide")

st.title("PDF RAG System - Query Interface")

st.sidebar.header("RAG Configuration")
rag_mode = st.sidebar.radio(
    "Select RAG Mode:",
    ("Standard RAG", "DocLong RAG"),
    index=0,
    help="Standard RAG: Fast retrieval with smaller chunks\nDocLong RAG: Better for long documents with hierarchical chunking and parent-document retrieval",
)

model = SentenceTransformer(
    "all-mpnet-base-v2", device="cuda" if torch.cuda.is_available() else "cpu"
)


def load_standard_rag():
    db._initialize_database()
    folder_path = "pdf"
    processed_files = set()

    for row in db.get_all_vectors():
        if isinstance(row, tuple):
            _, _, metadata_str = row
            try:
                metadata = eval(metadata_str)
                file_path = metadata.get("file_path", "")
                if file_path:
                    processed_files.add(file_path)
            except:
                continue

    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".pdf"):
                file_path = os.path.join(root, file)

                if file_path in processed_files:
                    continue
                if has_file_been_processed(file_path, db):
                    continue

                processed_files.add(file_path)

                text = process_pdf(file_path)
                chunks = split_text_into_chunks(text)

                chunks, embeddings = get_existing_vectors_and_chunks(db, file_path)

                if not chunks:
                    if not os.path.exists(file_path):
                        continue

                    text = process_pdf(file_path)
                    chunks = split_text_into_chunks(text)

                    index, embeddings = create_embeddings_and_index(chunks)

                    for i, embedding in enumerate(embeddings):
                        metadata = {
                            "chunk": chunks[i],
                            "index": i,
                            "file_path": file_path,
                        }
                        db.insert_vector(embedding, metadata)

                else:
                    index = faiss.IndexIVFFlat(
                        faiss.IndexFlatL2(embeddings.shape[1]),
                        embeddings.shape[1],
                        min(128, len(embeddings)),
                    )
                    index.train(embeddings[: min(500, len(embeddings))])
                    index.add(embeddings)

    return True


if rag_mode == "DocLong RAG":
    initialize_doclong_database()

    @st.cache_resource
    def load_doclong_index():
        folder_path = "pdf"
        process_all_pdfs_doclong(folder_path, model)
        return True

    doclong_setup = load_doclong_index()

    if doclong_setup:
        st.info(
            "DocLong RAG Mode: Using hierarchical chunking for better long document handling"
        )

        query = st.text_input("Enter your query:")

        if st.button("Search"):
            if query:
                status_container = st.empty()
                status_container.markdown(
                    "### Processing query with DocLong RAG... Please wait"
                )

                result = query_doclong(query, model)

                status_container.markdown("### Processing complete")

                st.write("\nGenerated Response:")
                st.write(result.get("response", ""))
                st.write(f"\nRetrieved {result.get('retrieved_docs', 0)} documents")
            else:
                st.warning("Please enter a query.")
else:
    setup = load_standard_rag()

    if setup:
        query = st.text_input("Enter your query:")

        if st.button("Search"):
            if query:
                status_container = st.empty()
                status_container.markdown("### Processing query... Please wait")

                stop_button = st.button("Wait/Stop")

                if not stop_button:
                    st.write("## Relevant Chunks from the PDF:")
                    relevant_chunks = generate_response(query, db, model, llm)

                    if isinstance(relevant_chunks, dict):
                        th = relevant_chunks.get("thinking", "")
                        rp = relevant_chunks.get("response", "")
                    else:
                        th = ""
                        rp = str(relevant_chunks)

                    status_container.markdown("### Processing complete")

                    st.write("\nGenerated Thinking:\n")
                    st.write(th)
                    st.write("\nGenerated Response:\n")
                    st.write(rp)
                else:
                    status_container.markdown("### Processing paused")
                    st.warning(
                        "Processing has been paused. You can resume by clicking 'Search' again."
                    )
            else:
                st.warning("Please enter a query.")
    else:
        st.error("Failed to load Standard RAG. Please check your system.")
