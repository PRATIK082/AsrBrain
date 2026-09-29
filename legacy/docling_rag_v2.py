import os
import re
import json
import sqlite3
import hashlib
import numpy as np
import httpx
from typing import List, Tuple, Dict, Any, Optional
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

OLLAMA_HOST = "http://127.0.0.1:11434"

try:
    from docling.document_converter import DocumentConverter
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.backend.pypdf_backend import PyPdfDocumentBackend

    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False
    print("Docling not available, falling back to pypdf")

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("Scikit-learn not available")


@dataclass
class DocumentChunk:
    chunk_id: int
    text: str
    embedding: np.ndarray
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "embedding": self.embedding.tolist(),
            "metadata": self.metadata,
        }


class TFIDFEmbedder:
    def __init__(
        self,
        max_features: int = 10000,
        ngram_range: Tuple[int, int] = (1, 2),
        min_df: int = 1,
    ):
        self.max_features = max_features
        self.ngram_range = ngram_range
        self.min_df = min_df
        self.vectorizer = None
        self.vocabulary_ = None
        self.idf_ = None

    def fit_transform(self, texts: List[str]) -> np.ndarray:
        if not SKLEARN_AVAILABLE:
            return self._simple_tfidf_fit_transform(texts)

        def custom_tokenizer(text):
            text = text.lower()
            text = re.sub(r"(\w+)/(\w+)", r"\1\2", text)
            text = re.sub(r"[^a-z0-9\s]", " ", text)
            tokens = text.split()
            return [t for t in tokens if len(t) > 1]

        self.vectorizer = TfidfVectorizer(
            max_features=self.max_features,
            ngram_range=self.ngram_range,
            min_df=self.min_df,
            max_df=0.95,
            sublinear_tf=True,
            tokenizer=custom_tokenizer,
            token_pattern=None,
        )
        embeddings = self.vectorizer.fit_transform(texts)
        self.vocabulary_ = self.vectorizer.vocabulary_
        self.idf_ = self.vectorizer.idf_
        return embeddings.toarray()

    def transform(self, texts: List[str]) -> np.ndarray:
        if not SKLEARN_AVAILABLE:
            return self._simple_tfidf_transform(texts)

        if self.vectorizer is None:
            raise ValueError("Vectorizer not fitted. Call fit_transform first.")
        embeddings = self.vectorizer.transform(texts)
        return embeddings.toarray()

    def transform(self, texts: List[str]) -> np.ndarray:
        if not SKLEARN_AVAILABLE:
            return self._simple_tfidf_transform(texts)

        if self.vectorizer is None:
            raise ValueError("Vectorizer not fitted. Call fit_transform first.")
        embeddings = self.vectorizer.transform(texts)
        return embeddings.toarray()

    def _simple_tfidf_fit_transform(self, texts: List[str]) -> np.ndarray:
        self._build_vocabulary(texts)
        return self._compute_tfidf(texts)

    def _simple_tfidf_transform(self, texts: List[str]) -> np.ndarray:
        return self._compute_tfidf(texts)

    def _build_vocabulary(self, texts: List[str]):
        word_doc_freq = defaultdict(int)
        word_total_freq = defaultdict(int)
        total_docs = len(texts)

        for text in texts:
            words = set(self._tokenize(text))
            for word in words:
                word_doc_freq[word] += 1
                word_total_freq[word] += 1

        filtered_words = {
            word: freq for word, freq in word_doc_freq.items() if freq >= self.min_df
        }

        sorted_words = sorted(filtered_words.items(), key=lambda x: x[1], reverse=True)
        self.vocabulary_ = {
            word: idx for idx, (word, _) in enumerate(sorted_words[: self.max_features])
        }
        self.idf_ = {
            word: np.log(total_docs / (freq + 1)) + 1
            for word, freq in filtered_words.items()
            if word in self.vocabulary_
        }

    def _compute_tfidf(self, texts: List[str]) -> np.ndarray:
        dim = len(self.vocabulary_)
        embeddings = np.zeros((len(texts), dim))

        for i, text in enumerate(texts):
            tokens = self._tokenize(text)
            tf = defaultdict(int)
            for token in tokens:
                tf[token] += 1

            max_tf = max(tf.values()) if tf else 1

            for token, count in tf.items():
                if token in self.vocabulary_:
                    idx = self.vocabulary_[token]
                    tf_norm = 0.5 + 0.5 * count / max_tf
                    idf = self.idf_.get(token, 1.0)
                    embeddings[i, idx] = tf_norm * idf

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        embeddings = embeddings / norms

        return embeddings

    def _tokenize(self, text: str) -> List[str]:
        text = text.lower()
        # Replace common technical abbreviations with slashes to keep them as single tokens
        text = re.sub(r"(\w+)/(\w+)", r"\1\2", text)  # Convert SOME/IP -> SOMEIP
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        tokens = text.split()
        return [t for t in tokens if len(t) > 1]


class NumpyVectorStore:
    def __init__(self, embedding_dim: int):
        self.embedding_dim = embedding_dim
        self.embeddings: List[np.ndarray] = []
        self.chunks: List[DocumentChunk] = []
        self.chunk_id_counter = 0

    def add_chunk(self, text: str, embedding: np.ndarray, metadata: Dict[str, Any]):
        chunk = DocumentChunk(
            chunk_id=self.chunk_id_counter,
            text=text,
            embedding=embedding,
            metadata=metadata,
        )
        self.embeddings.append(embedding)
        self.chunks.append(chunk)
        self.chunk_id_counter += 1
        return chunk.chunk_id

    def search(
        self, query_embedding: np.ndarray, top_k: int = 5
    ) -> List[Tuple[DocumentChunk, float]]:
        if not self.embeddings:
            return []

        query_embedding = query_embedding.reshape(1, -1)
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)

        all_embeddings = np.array(self.embeddings)
        all_norms = np.linalg.norm(all_embeddings, axis=1, keepdims=True)
        all_norms = np.where(all_norms == 0, 1, all_norms)
        normalized_embeddings = all_embeddings / all_norms

        similarities = np.dot(normalized_embeddings, query_norm.T).flatten()

        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if similarities[idx] > 0:
                results.append((self.chunks[idx], float(similarities[idx])))

        return results

    def get_all_chunks(self) -> List[DocumentChunk]:
        return self.chunks

    def clear(self):
        self.embeddings = []
        self.chunks = []
        self.chunk_id_counter = 0


class SQLiteVectorDatabase:
    def __init__(self, db_path: str = "docling_rag.db"):
        self.db_path = db_path
        self._initialize_database()

    def _initialize_database(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS chunks
                     (id INTEGER PRIMARY KEY, text TEXT, embedding BLOB, metadata TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS documents
                     (id INTEGER PRIMARY KEY, file_path TEXT, title TEXT, 
                      processed_at TEXT, chunk_count INTEGER, file_hash TEXT)""")
        conn.commit()
        conn.close()

    def insert_chunk(self, text: str, embedding: np.ndarray, metadata: dict) -> int:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO chunks (text, embedding, metadata) VALUES (?, ?, ?)",
            (text, embedding.tobytes(), json.dumps(metadata)),
        )
        conn.commit()
        chunk_id = c.lastrowid
        conn.close()
        return chunk_id

    def get_all_chunks(self) -> List[Tuple[str, np.ndarray, dict]]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT text, embedding, metadata FROM chunks")
        rows = c.fetchall()
        conn.close()

        results = []
        for text, embedding_blob, metadata_str in rows:
            embedding = np.frombuffer(embedding_blob, dtype=np.float32)
            metadata = json.loads(metadata_str)
            results.append((text, embedding, metadata))
        return results

    def get_chunks_by_file(self, file_path: str) -> List[Tuple[str, np.ndarray, dict]]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT text, embedding, metadata FROM chunks WHERE metadata LIKE ?",
            (f"%{file_path}%",),
        )
        rows = c.fetchall()
        conn.close()

        results = []
        for text, embedding_blob, metadata_str in rows:
            embedding = np.frombuffer(embedding_blob, dtype=np.float32)
            metadata = json.loads(metadata_str)
            results.append((text, embedding, metadata))
        return results

    def chunk_exists(self, file_path: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*) FROM chunks WHERE metadata LIKE ?", (f"%{file_path}%",)
        )
        count = c.fetchone()[0]
        conn.close()
        return count > 0

    def clear_file_chunks(self, file_path: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM chunks WHERE metadata LIKE ?", (f"%{file_path}%",))
        conn.commit()
        conn.close()

    def get_document_count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(DISTINCT metadata) FROM chunks WHERE metadata LIKE '%file_path%'"
        )
        count = c.fetchone()[0]
        conn.close()
        return count

    def get_processed_files(self) -> Dict[str, str]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT file_path, file_hash FROM documents")
        rows = c.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows if row[0]}

    def save_document_record(self, file_path: str, chunk_count: int, file_hash: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO documents (file_path, processed_at, chunk_count, file_hash) VALUES (?, ?, ?, ?)",
            (file_path, datetime.now().isoformat(), chunk_count, file_hash),
        )
        conn.commit()
        conn.close()

    def remove_document_record(self, file_path: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM documents WHERE file_path = ?", (file_path,))
        conn.commit()
        conn.close()


class DoclingRAG:
    def __init__(
        self,
        db_path: str = "docling_rag.db",
        chunk_size: int = 500,
        overlap: int = 100,
        embedding_dim: int = 10000,
        top_k: int = 5,
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.top_k = top_k

        self.database = SQLiteVectorDatabase(db_path)
        self.embedder = TFIDFEmbedder(
            max_features=embedding_dim, ngram_range=(1, 2), min_df=1
        )
        self.vector_store: Optional[NumpyVectorStore] = None
        self.document_converter = None

        if DOCLING_AVAILABLE:
            self._init_docling()

    def _get_file_hash(self, file_path: str) -> str:
        """Get file hash based on modification time and size for quick change detection"""
        stat = os.stat(file_path)
        hash_input = f"{file_path}_{stat.st_mtime}_{stat.st_size}"
        return hashlib.md5(hash_input.encode()).hexdigest()

    def _init_docling(self):
        try:
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = False
            pipeline_options.do_table_structure = False

            self.document_converter = DocumentConverter(
                format_options={InputFormat.PDF: pipeline_options}
            )
        except Exception as e:
            print(f"Failed to initialize Docling: {e}")
            self.document_converter = None

    def process_document(
        self, file_path: str, force_reprocess: bool = False
    ) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_hash = self._get_file_hash(file_path)
        processed_files = self.database.get_processed_files()

        if file_path in processed_files and not force_reprocess:
            if processed_files[file_path] == file_hash:
                print(f"File {file_path} unchanged. Skipping.")
                return self._load_from_database(file_path)

        print(f"Processing {file_path} (hash changed or new file)")
        if self.database.chunk_exists(file_path):
            self.database.clear_file_chunks(file_path)

        text = self._extract_text(file_path)
        chunks = self._split_into_chunks(text)

        print(f"Processing {len(chunks)} chunks from {file_path}")

        embeddings = self.embedder.fit_transform(chunks)

        for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
            metadata = {
                "file_path": file_path,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "source": "docling" if self.document_converter else "pypdf",
                "file_hash": file_hash,
            }
            self.database.insert_chunk(chunk_text, embedding, metadata)

        self.database.save_document_record(file_path, len(chunks), file_hash)

        return {
            "file_path": file_path,
            "num_chunks": len(chunks),
            "status": "processed",
        }

    def _extract_text(self, file_path: str) -> str:
        if self.document_converter:
            try:
                result = self.document_converter.convert(file_path)
                return result.document.export_to_text()
            except Exception as e:
                print(f"Docling extraction failed: {e}, falling back to pypdf")

        return self._extract_text_pypdf(file_path)

    def _extract_text_pypdf(self, file_path: str) -> str:
        try:
            from pypdf import PdfReader

            reader = PdfReader(file_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            return text
        except Exception as e:
            raise RuntimeError(f"Failed to extract text: {e}")

    def _split_into_chunks(self, text: str) -> List[str]:
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        words = text.split()
        chunks = []

        for i in range(0, len(words), self.chunk_size - self.overlap):
            chunk = " ".join(words[i : i + self.chunk_size])
            if chunk.strip():
                chunks.append(chunk)

        return chunks

    def _load_from_database(self, file_path: str) -> Dict[str, Any]:
        chunks_data = self.database.get_chunks_by_file(file_path)

        if not chunks_data:
            return {"status": "no_chunks_found"}

        self.vector_store = NumpyVectorStore(embedding_dim=len(chunks_data[0][1]))

        for text, embedding, metadata in chunks_data:
            self.vector_store.add_chunk(text, embedding, metadata)

        return {
            "file_path": file_path,
            "num_chunks": len(chunks_data),
            "status": "loaded",
        }

    def build_index(self):
        all_chunks = self.database.get_all_chunks()

        if not all_chunks:
            print("No chunks found in database")
            return

        texts = [chunk[0] for chunk in all_chunks]

        embeddings = self.embedder.fit_transform(texts)

        self.vector_store = NumpyVectorStore(embedding_dim=embeddings.shape[1])

        for i, (text, _, metadata) in enumerate(all_chunks):
            self.vector_store.add_chunk(text, embeddings[i], metadata)

        print(
            f"Built index with {len(self.vector_store.chunks)} chunks, dim={embeddings.shape[1]}"
        )

    def search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        if top_k is None:
            top_k = self.top_k

        if self.vector_store is None:
            self.build_index()

        if not self.vector_store or not self.vector_store.chunks:
            return []

        query_embedding = self.embedder.transform([query])

        results = self.vector_store.search(query_embedding[0], top_k)

        formatted_results = []
        for chunk, score in results:
            formatted_results.append(
                {"text": chunk.text, "score": score, "metadata": chunk.metadata}
            )

        return formatted_results

    def hybrid_search(
        self,
        query: str,
        top_k: Optional[int] = None,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> List[Dict[str, Any]]:
        if top_k is None:
            top_k = self.top_k

        if self.vector_store is None:
            self.build_index()

        query_lower = query.lower()
        query_terms = set(query_lower.split())

        query_embedding = self.embedder.transform([query])
        semantic_results = self.vector_store.search(query_embedding[0], top_k * 3)

        keyword_scores = {}
        for chunk in self.vector_store.chunks:
            text_lower = chunk.text.lower()
            text_words = set(text_lower.split())

            overlap = len(query_terms & text_words)
            if overlap > 0:
                keyword_scores[chunk.chunk_id] = overlap / len(query_terms)
            else:
                keyword_scores[chunk.chunk_id] = 0.0

        combined_scores = {}
        for chunk, semantic_score in semantic_results:
            sem_weighted = semantic_score * semantic_weight
            kw_weighted = keyword_scores.get(chunk.chunk_id, 0) * keyword_weight
            combined_scores[chunk.chunk_id] = sem_weighted + kw_weighted

        sorted_chunks = sorted(
            combined_scores.items(), key=lambda x: x[1], reverse=True
        )[:top_k]

        chunk_map = {c.chunk_id: c for c in self.vector_store.chunks}

        results = []
        for chunk_id, score in sorted_chunks:
            chunk = chunk_map[chunk_id]
            results.append(
                {"text": chunk.text, "score": score, "metadata": chunk.metadata}
            )

        return results

    def process_folder(
        self, folder_path: str, force_reprocess: bool = False
    ) -> Dict[str, Any]:
        if not os.path.exists(folder_path):
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        processed_files = self.database.get_processed_files()

        current_pdf_files = set()
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(".pdf"):
                    file_path = os.path.join(root, file)
                    current_pdf_files.add(file_path)

        processed_set = set(processed_files.keys())

        deleted_files = processed_set - current_pdf_files
        for deleted_file in deleted_files:
            print(f"Removing deleted file: {deleted_file}")
            self.database.clear_file_chunks(deleted_file)
            self.database.remove_document_record(deleted_file)

        new_or_changed = []
        for file_path in current_pdf_files:
            if force_reprocess:
                new_or_changed.append(file_path)
            elif file_path not in processed_files:
                new_or_changed.append(file_path)
            else:
                file_hash = self._get_file_hash(file_path)
                if processed_files[file_path] != file_hash:
                    new_or_changed.append(file_path)

        processed = []
        failed = []

        for file_path in new_or_changed:
            try:
                result = self.process_document(
                    file_path, force_reprocess=force_reprocess
                )
                processed.append(result)
            except Exception as e:
                failed.append({"file": file_path, "error": str(e)})

        if processed or deleted_files:
            self.build_index()

        return {
            "processed": processed,
            "failed": failed,
            "total_processed": len(processed),
            "total_failed": len(failed),
            "new_files": len(new_or_changed),
            "deleted_files": len(deleted_files),
            "skipped": len(current_pdf_files) - len(new_or_changed),
        }


def check_ollama_connection() -> Tuple[bool, str]:
    try:
        response = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
        if response.status_code == 200:
            return True, "Connected"
        return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, str(e)


def generate_response(
    query: str,
    rag_system: DoclingRAG,
    llm_model: str = "qwen3:14b",
    use_hybrid: bool = True,
) -> Dict[str, Any]:
    ollama_available, ollama_msg = check_ollama_connection()

    if not ollama_available:
        return {
            "response": f"Ollama not available: {ollama_msg}\n\nMake sure Ollama is running locally.",
            "sources": [],
            "query": query,
            "error": True,
        }

    try:
        if use_hybrid:
            results = rag_system.hybrid_search(query, top_k=5)
        else:
            results = rag_system.search(query, top_k=5)

        if not results:
            return {
                "response": "No relevant documents found.",
                "sources": [],
                "query": query,
            }

        context = "\n\n".join([r["text"] for r in results])

        prompt = f"""Based on the following context from technical and research documents, please answer the question accurately and thoroughly.

Context:
{context}

Question: {query}

Please provide a detailed, accurate answer based solely on the context above. If the context doesn't contain enough information to fully answer the question, please state what information is available and what is missing."""

        try:
            payload = {
                "model": llm_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_ctx": 8192, "top_p": 0.9},
            }

            response = httpx.post(
                f"{OLLAMA_HOST}/api/generate", json=payload, timeout=120.0
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "response": data.get("response", "No response generated"),
                    "sources": results,
                    "query": query,
                    "num_sources": len(results),
                }
            else:
                return {
                    "response": f"LLM Error: HTTP {response.status_code} - {response.text}",
                    "sources": results,
                    "query": query,
                    "num_sources": len(results),
                    "error": True,
                }
        except Exception as e:
            return {
                "response": f"LLM Error: {str(e)}",
                "sources": results,
                "query": query,
                "num_sources": len(results),
                "error": True,
            }

    except Exception as e:
        return {
            "response": f"Error: {str(e)}",
            "sources": [],
            "query": query,
            "error": True,
        }

    try:
        import ollama

        if use_hybrid:
            results = rag_system.hybrid_search(query, top_k=5)
        else:
            results = rag_system.search(query, top_k=5)

        if not results:
            return {
                "response": "No relevant documents found.",
                "sources": [],
                "query": query,
            }

        context = "\n\n".join([r["text"] for r in results])

        prompt = f"""Based on the following context from technical and research documents, please answer the question accurately and thoroughly.

Context:
{context}

Question: {query}

Please provide a detailed, accurate answer based solely on the context above. If the context doesn't contain enough information to fully answer the question, please state what information is available and what is missing."""

        try:
            response = ollama.generate(
                model=llm_model,
                prompt=prompt,
                options={"temperature": 0.3, "num_ctx": 8192, "top_p": 0.9},
            )

            return {
                "response": response.get("response", "No response generated"),
                "sources": results,
                "query": query,
                "num_sources": len(results),
            }
        except Exception as e:
            return {
                "response": f"LLM Error: {str(e)}",
                "sources": results,
                "query": query,
                "num_sources": len(results),
                "error": True,
            }

    except ImportError:
        return {
            "response": "Ollama not installed. Please install ollama to generate responses.",
            "sources": [],
            "query": query,
            "error": True,
        }


if __name__ == "__main__":
    rag = DoclingRAG(
        db_path="docling_rag.db",
        chunk_size=500,
        overlap=100,
        embedding_dim=10000,
        top_k=5,
    )

    print("Processing PDFs in 'pdf' folder...")
    result = rag.process_folder("pdf")
    print(f"Processed {result['total_processed']} files")
    if result["failed"]:
        print(f"Failed: {result['failed']}")

    print("\n--- Search Test ---")
    query = "SOMEIP protocol"
    results = rag.hybrid_search(query)
    print(f"Query: {query}")
    print(f"Found {len(results)} results")
    for i, r in enumerate(results):
        print(f"\n--- Result {i + 1} (score: {r['score']:.4f}) ---")
        print(r["text"][:300] + "...")
