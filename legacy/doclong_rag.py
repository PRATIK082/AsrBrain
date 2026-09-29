import os
import numpy as np
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import faiss
from typing import List, Tuple, Dict, Any, Optional, Union
from rank_bm25 import BM25Okapi
from database import VectorDatabase
import ollama

llm = ollama


class DocLongRAG:
    def __init__(
        self,
        db: VectorDatabase,
        model: SentenceTransformer,
        small_chunk_size: int = 300,
        large_chunk_size: int = 1500,
        overlap: int = 100,
        small_overlap: int = 50,
    ):
        self.db = db
        self.model = model
        self.small_chunk_size = small_chunk_size
        self.large_chunk_size = large_chunk_size
        self.overlap = overlap
        self.small_overlap = small_overlap

    def process_pdf(self, file_path: str) -> str:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text

    def split_into_parent_chunks(self, text: str) -> List[str]:
        words = text.split()
        chunks = []
        for i in range(0, len(words), self.large_chunk_size - self.overlap):
            chunk = " ".join(words[i : i + self.large_chunk_size])
            chunks.append(chunk)
        return chunks

    def split_into_small_chunks(self, text: str) -> List[str]:
        words = text.split()
        chunks = []
        for i in range(0, len(words), self.small_chunk_size - self.small_overlap):
            chunk = " ".join(words[i : i + self.small_chunk_size])
            chunks.append(chunk)
        return chunks

    def create_parent_embeddings(self, chunks: List[str]) -> np.ndarray:
        embeddings = self.model.encode(chunks, convert_to_tensor=True).cpu().numpy()
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings

    def create_small_embeddings(self, chunks: List[str]) -> np.ndarray:
        embeddings = self.model.encode(chunks, convert_to_tensor=True).cpu().numpy()
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings

    def create_faiss_index(self, embeddings: np.ndarray) -> faiss.Index:
        d = embeddings.shape[1]
        num_clusters = min(128, len(embeddings))

        if len(embeddings) < num_clusters:
            num_clusters = max(1, len(embeddings))

        index = faiss.IndexIVFFlat(faiss.IndexFlatL2(d), d, num_clusters)

        train_size = min(500, len(embeddings))
        if train_size > 0:
            index.train(embeddings[:train_size])
        index.add(embeddings)
        return index

    def process_and_store_document(self, file_path: str):
        text = self.process_pdf(file_path)

        parent_chunks = self.split_into_parent_chunks(text)
        small_chunks = self.split_into_small_chunks(text)

        parent_embeddings = self.create_parent_embeddings(parent_chunks)
        small_embeddings = self.create_small_embeddings(small_chunks)

        for i, (chunk, embedding) in enumerate(zip(parent_chunks, parent_embeddings)):
            metadata = {
                "chunk": chunk,
                "index": i,
                "file_path": file_path,
                "chunk_type": "parent",
            }
            self.db.insert_vector(embedding, metadata)

        for i, (chunk, embedding) in enumerate(zip(small_chunks, small_embeddings)):
            parent_idx = (
                i
                * (self.small_chunk_size - self.small_overlap)
                // max(1, self.large_chunk_size - self.overlap)
            )
            metadata = {
                "chunk": chunk,
                "index": i,
                "file_path": file_path,
                "chunk_type": "small",
                "parent_index": parent_idx,
            }
            self.db.insert_vector(embedding, metadata)

    def retrieve_with_parent_documents(
        self, query: str, top_k_small: int = 10, top_k_parents: int = 5
    ) -> List[Dict[str, Any]]:
        all_vectors = self.db.get_all_vectors()

        small_chunks = []
        small_embeddings = []
        parent_chunks = []
        parent_embeddings = []

        for row in all_vectors:
            if isinstance(row, tuple):
                _, embedding, metadata_str = row
            else:
                continue

            try:
                metadata = eval(metadata_str)
            except:
                continue

            chunk_type = metadata.get("chunk_type", "parent")
            embedding_array = np.frombuffer(embedding, dtype=np.float32)

            if chunk_type == "small":
                small_chunks.append(metadata)
                small_embeddings.append(embedding_array)
            else:
                parent_chunks.append(metadata)
                parent_embeddings.append(embedding_array)

        if not small_embeddings or not parent_embeddings:
            return []

        small_embeddings = np.array(small_embeddings)
        parent_embeddings = np.array(parent_embeddings)

        query_embedding = (
            self.model.encode([query], convert_to_tensor=True).cpu().numpy()
        )
        query_embedding = query_embedding / np.linalg.norm(
            query_embedding, axis=1, keepdims=True
        )

        small_index = self.create_faiss_index(small_embeddings)
        parent_index = self.create_faiss_index(parent_embeddings)

        small_distances, small_indices = small_index.search(
            query_embedding, top_k_small
        )
        parent_distances, parent_indices = parent_index.search(
            query_embedding, top_k_parents
        )

        retrieved_parents = []
        for idx in parent_indices[0]:
            if idx < len(parent_chunks):
                retrieved_parents.append(
                    {
                        "chunk": parent_chunks[idx].get("chunk", ""),
                        "file_path": parent_chunks[idx].get("file_path", ""),
                        "distance": parent_distances[0][
                            list(parent_indices[0]).index(idx)
                        ],
                        "chunk_type": "parent",
                    }
                )

        return retrieved_parents

    def retrieve_hybrid(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        all_vectors = self.db.get_all_vectors()

        chunks = []
        embeddings = []

        for row in all_vectors:
            if isinstance(row, tuple):
                _, embedding, metadata_str = row
            else:
                continue

            try:
                metadata = eval(metadata_str)
            except:
                continue

            chunks.append(metadata)
            embeddings.append(np.frombuffer(embedding, dtype=np.float32))

        if not embeddings:
            return []

        embeddings = np.array(embeddings)

        query_embedding = (
            self.model.encode([query], convert_to_tensor=True).cpu().numpy()
        )
        query_embedding = query_embedding / np.linalg.norm(
            query_embedding, axis=1, keepdims=True
        )

        index = self.create_faiss_index(embeddings)

        faiss_distances, faiss_indices = index.search(query_embedding, top_k)

        tokenized_corpus = [c.get("chunk", "").split() for c in chunks]
        bm25 = BM25Okapi(tokenized_corpus)
        bm25_scores = bm25.get_scores(query.split())
        bm25_indices = np.argsort(-bm25_scores)[:top_k]

        combined_scores = {}

        for rank, idx in enumerate(faiss_indices[0]):
            if idx < len(chunks):
                faiss_score = 1 / (1 + faiss_distances[0][rank])
                combined_scores[idx] = combined_scores.get(idx, 0) + faiss_score

        for idx in bm25_indices:
            if idx < len(chunks):
                bm25_score = bm25_scores[idx]
                max_bm25 = max(bm25_scores) if max(bm25_scores) > 0 else 1
                normalized_bm25 = bm25_score / max_bm25
                combined_scores[idx] = combined_scores.get(idx, 0) + normalized_bm25

        sorted_indices = sorted(
            combined_scores.keys(), key=lambda x: combined_scores[x], reverse=True
        )

        results = []
        for idx in sorted_indices[:top_k]:
            if idx < len(chunks):
                results.append(
                    {
                        "chunk": chunks[idx].get("chunk", ""),
                        "file_path": chunks[idx].get("file_path", ""),
                        "score": combined_scores[idx],
                        "chunk_type": chunks[idx].get("chunk_type", "parent"),
                    }
                )

        return results

    def generate_response(
        self, query: str, use_parent_retrieval: bool = True
    ) -> Dict[str, Union[str, int]]:
        if use_parent_retrieval:
            relevant_docs = self.retrieve_with_parent_documents(query)
        else:
            relevant_docs = self.retrieve_hybrid(query)

        if not relevant_docs:
            return {
                "response": "No relevant documents found.",
                "thinking": "",
                "retrieved_docs": 0,
            }

        context = "\n\n".join([doc["chunk"] for doc in relevant_docs])

        prompt = f"""Based on the following context documents, please answer the question accurately and thoroughly.

Context:
{context}

Question: {query}

Please provide a detailed answer based on the context above."""

        try:
            response = ollama.generate(
                model="qwen3:14b",
                prompt=prompt,
                options={"temperature": 0.3, "num_ctx": 8192},
            )

            thinking = (
                response.get("response", "")[:500] if response.get("response") else ""
            )

            return {
                "response": response.get("response", "No response generated"),
                "thinking": thinking,
                "retrieved_docs": len(relevant_docs),
            }
        except Exception as e:
            return {
                "response": f"Error generating response: {str(e)}",
                "thinking": "",
                "retrieved_docs": 0,
            }


db_doclong = VectorDatabase("doclong_database.db")


def initialize_doclong_database():
    db_doclong._initialize_database()


def process_pdf_doclong(file_path: str) -> str:
    doclong = DocLongRAG(db_doclong, None)
    return doclong.process_pdf(file_path)


def split_text_into_chunks_doclong(
    text: str, chunk_size: int = 500, overlap: int = 50
) -> List[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i : i + chunk_size])
        chunks.append(chunk)
    return chunks


def get_or_create_doclong_rag(model: SentenceTransformer) -> DocLongRAG:
    return DocLongRAG(db_doclong, model)


def process_all_pdfs_doclong(folder_path: str, model: SentenceTransformer):
    doclong = DocLongRAG(db_doclong, model)
    processed_files = set()

    for row in db_doclong.get_all_vectors():
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
                    print(f"File {file_path} already processed. Skipping.")
                    continue

                processed_files.add(file_path)
                print(f"Processing {file_path}...")
                doclong.process_and_store_document(file_path)
                print(f"Completed {file_path}")


def query_doclong(query: str, model: SentenceTransformer) -> Dict[str, Union[str, int]]:
    doclong = DocLongRAG(db_doclong, model)
    return doclong.generate_response(query, use_parent_retrieval=True)
