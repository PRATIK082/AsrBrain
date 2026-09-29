# src/pdf_rag_system.py
import os
import numpy as np
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import faiss
from typing import List, Tuple, Iterator, Optional, Any, Dict, DefaultDict, List

# from nltk.tokenize import sent_tokenize
# import nltk
from rank_bm25 import BM25Okapi

# from nli_utils import NLIClassifier
from database import VectorDatabase
import numpy

# import torch
# print(torch.__version__)
# print(torch.cuda.is_available())
import ollama

# Initialize the model
llm = ollama

db = VectorDatabase()
# Download required NLTK data
# nltk.download('punkt')
# model = SentenceTransformer('sentence-transformers/paraphrase-MiniLM-L12-v2')
# model = SentenceTransformer('all-mpnet-base-v2')
model = SentenceTransformer("all-mpnet-base-v2", device="cpu")  # Use CPU
# In-memory metadata store
vector_metadata: Dict[int, Dict[str, Any]] = DefaultDict(dict)


# Step 1: Preprocess the PDF
def process_pdf(file_path: str) -> str:
    """Extract text from a PDF file."""
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""  # Handle potential None values
    return text


def split_text_into_chunks(
    text: str, chunk_size: int = 500, overlap: int = 50
) -> List[str]:
    """Split text into chunks with specified size and overlap."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i : i + chunk_size])
        chunks.append(chunk)
    return chunks


# Step 2: Create embeddings and index
def create_embeddings_and_index(
    text_chunks: List[str],
) -> Tuple[faiss.Index, np.ndarray]:
    """Create embeddings using a sentence transformer and build a FAISS index using IVFPQ."""
    embeddings = model.encode(text_chunks, convert_to_tensor=True).cpu().numpy()
    # Normalize embeddings using NumPy
    embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    # Ensure we have enough training vectors
    num_training_vectors = min(
        500, len(embeddings)
    )  # Use up to 500 vectors for training
    if num_training_vectors < 1:  # FAISS recommends at least 100 training vectors
        raise ValueError(
            f"Need at least 1 training vectors, but only {num_training_vectors} are available."
        )

    # Set the number of clusters to be less than or equal to the number of training vectors
    num_clusters = min(128, num_training_vectors)  # Use 128 clusters or fewer

    # Use IVFPQ index
    d = embeddings.shape[1]  # Dimension of the embeddings
    index = faiss.IndexIVFFlat(
        faiss.IndexFlatL2(d),  # Use L2 distance
        d,  # Dimension
        num_clusters,  # Number of clusters
    )

    # Train the index on a subset of the data
    index.train(
        embeddings[:num_training_vectors]
    )  # Use first num_training_vectors vectors to train

    # Add all embeddings to the index
    index.add(embeddings)

    return index, embeddings


# Step 3: Retrieve relevant chunks
def retrieve_relevant_chunks_old(
    query: str, index: faiss.Index, chunks: List[str], top_k: int = 5
) -> List[str]:
    """Retrieve the most relevant chunks based on a query."""
    # Encode query and convert to NumPy
    query_embedding = model.encode([query], convert_to_tensor=True).cpu().numpy()

    # Get top-k FAISS matches
    faiss_indices = index.search(query_embedding, top_k)[1][0]

    # Preprocess chunks for BM25
    tokenized_corpus = [chunk.split() for chunk in chunks]
    bm25 = BM25Okapi(tokenized_corpus)

    # Use BM25 to get top-k matches
    bm25_scores = bm25.get_scores(query.split())
    bm25_indices = np.argsort(-bm25_scores)[:top_k]

    # Combine the indices (remove duplicates)
    combined_indices = np.unique(np.concatenate([faiss_indices, bm25_indices]))

    # Get the final relevant chunks
    relevant_chunks = [chunks[i] for i in faiss_indices]
    return relevant_chunks


def retrieve_relevant_chunks(
    query: str, index: faiss.Index, chunks: List[str], top_k: int = 5
) -> List[str]:
    """
    Retrieve the most relevant chunks based on a query using FAISS and BM25.
    Combines results from both methods and returns the top-k chunks.
    """
    # Step 1: FAISS search
    query_embedding = model.encode([query], convert_to_tensor=True).cpu().numpy()
    # Normalize embeddings using NumPy
    query_embedding = query_embedding / np.linalg.norm(
        query_embedding, axis=1, keepdims=True
    )
    faiss_distances, faiss_indices = index.search(query_embedding, top_k)

    # Flatten the lists
    faiss_indices = faiss_indices.tolist()[0]  # Flatten to a list of integers
    faiss_distances = faiss_distances.tolist()[0]  # Flatten to a list of distances

    # Step 2: BM25 search
    tokenized_corpus = [chunk.split() for chunk in chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    bm25_scores = bm25.get_scores(query.split())
    bm25_indices = np.argsort(-bm25_scores)[:top_k]
    bm25_indices = bm25_indices.tolist()  # Convert to list

    # Step 3: Combine and sort results
    # Map FAISS indices to chunk scores
    faiss_chunk_scores = {
        i: 1 - distance for i, distance in zip(faiss_indices, faiss_distances)
    }
    # Map BM25 indices to chunk scores
    bm25_chunk_scores = {
        i: score for i, score in zip(bm25_indices, bm25_scores[bm25_indices])
    }

    # Combine scores
    combined_scores = {}
    for i in faiss_indices:
        combined_scores[i] = faiss_chunk_scores[i]
    for i in bm25_indices:
        if i in combined_scores:
            combined_scores[i] += bm25_chunk_scores[i]
        else:
            combined_scores[i] = bm25_chunk_scores[i]

    # Sort by combined score
    sorted_indices = sorted(combined_scores, key=combined_scores.get, reverse=True)

    # Step 4: Return top-k chunks
    relevant_chunks = [chunks[i] for i in sorted_indices[:top_k]]
    return relevant_chunks


# Vector deletion, update, and search functionality
def delete_vector(index: faiss.Index, embeddings: np.ndarray, vector_index: int):
    """Delete a vector from the FAISS index."""
    # Remove the vector from the embeddings
    embeddings = np.delete(embeddings, vector_index, axis=0)
    # Rebuild the index
    index.reset()
    index.train(embeddings[: min(500, len(embeddings))])
    index.add(embeddings)
    return index, embeddings


def update_vector(
    index: faiss.Index,
    embeddings: np.ndarray,
    vector_index: int,
    new_embedding: np.ndarray,
):
    """Update a vector in the FAISS index."""
    # Replace the vector in the embeddings
    embeddings[vector_index] = new_embedding
    # Rebuild the index
    index.reset()
    index.train(embeddings[: min(500, len(embeddings))])
    index.add(embeddings)
    return index, embeddings


def search_vector(index: faiss.Index, query_embedding: np.ndarray, top_k: int = 5):
    """Search for the most similar vectors in the FAISS index."""
    distances, indices = index.search(query_embedding, top_k)
    return distances, indices


# Function to check if a file has already been processed
def has_file_been_processed(file_path: str, database: VectorDatabase) -> bool:
    """Check if the file has already been processed based on the database."""
    existing_metadata = database.get_all_metadata()

    for metadata in existing_metadata:
        if metadata.get("file_path") == file_path:
            return True

    return False


# Function to retrieve existing vectors and chunks
def get_existing_vectors_and_chunks(
    database: VectorDatabase, file_path: str
) -> Tuple[List[str], np.ndarray]:
    """Retrieve existing vectors and chunks from the database for a given file."""
    existing_vectors = database.get_all_vectors()
    chunks = []
    embeddings = []

    for row in existing_vectors:
        if isinstance(row, tuple):
            _, embedding, metadata_str = row
        else:
            # Fallback for unexpected row format
            continue

        # Convert metadata string to dictionary
        try:
            metadata = eval(metadata_str)
        except Exception as e:
            print(f"Error converting metadata: {metadata_str} - {e}")
            continue

        # Check if this vector belongs to the current file
        if metadata.get("file_path") == file_path:
            chunks.append(metadata.get("chunk", ""))
            embeddings.append(np.frombuffer(embedding, dtype=np.float32))

    # Convert list of embeddings to NumPy array
    embeddings = np.array(embeddings)

    return chunks, embeddings


# Main function
def _testmain():
    # Initialize model and database
    db._initialize_database()

    # Process all PDF files in the folder and subfolders
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

                # Check if the file has already been processed (fast lookup)
                if file_path in processed_files:
                    print(f"File {file_path} has already been processed. Skipping.")
                    continue
                # Check if the file has already been processed
                if has_file_been_processed(file_path, db):
                    print(f"File {file_path} has already been processed. Skipping.")
                    continue

                # Add file to processed set
                processed_files.add(file_path)

                # Process the PDF and split into chunks
                text = process_pdf(file_path)
                chunks = split_text_into_chunks(text)

                # Check if there are existing vectors for this file
                chunks, embeddings = get_existing_vectors_and_chunks(db, file_path)

                # If no existing vectors, process the file again
                if not chunks:
                    print(
                        f"No valid vectors found in the database. Processing file {file_path} again."
                    )
                    # Check if the file exists
                    if not os.path.exists(file_path):
                        print(f"Error: The file {file_path} does not exist.")
                        continue

                    # Process the PDF and split into chunks
                    text = process_pdf(file_path)
                    chunks = split_text_into_chunks(text)

                    # Create embeddings and index
                    index, embeddings = create_embeddings_and_index(chunks)

                    # Insert vectors into the database
                    for i, embedding in enumerate(embeddings):
                        metadata = {
                            "chunk": chunks[i],
                            "index": i,
                            "file_path": file_path,
                        }
                        db.insert_vector(embedding, metadata)
                        print(f"Inserted vector {i} into the database.")

                else:
                    # Use existing vectors for retrieval and search
                    print(
                        f"File {file_path} has already been processed. Using existing data from the database."
                    )

                    # Create FAISS index from existing embeddings
                    index = faiss.IndexIVFFlat(
                        faiss.IndexFlatL2(embeddings.shape[1]),  # Use L2 distance
                        embeddings.shape[1],  # Dimension
                        min(128, len(embeddings)),  # Number of clusters
                    )
                    index.train(embeddings[: min(500, len(embeddings))])
                    index.add(embeddings)

    # Rebuild the FAISS index with all embeddings from the database
    # Get all vectors from the database
    all_vectors = db.get_all_vectors()
    all_embeddings = []
    all_chunks = []

    for row in all_vectors:
        if isinstance(row, tuple):
            _, embedding, metadata_str = row
        else:
            continue

        # Convert metadata string to dictionary
        try:
            metadata = eval(metadata_str)
        except Exception as e:
            print(f"Error converting metadata: {metadata_str} - {e}")
            continue

        # Extract chunk and embedding
        chunk = metadata.get("chunk", "")
        all_chunks.append(chunk)
        all_embeddings.append(np.frombuffer(embedding, dtype=np.float32))

    # Convert list of embeddings to NumPy array
    all_embeddings = np.array(all_embeddings)

    # Create FAISS index with all embeddings
    index = faiss.IndexIVFFlat(
        faiss.IndexFlatL2(all_embeddings.shape[1]),  # Use L2 distance
        all_embeddings.shape[1],  # Dimension
        min(128, len(all_embeddings)),  # Number of clusters
    )
    index.train(all_embeddings[: min(500, len(all_embeddings))])
    index.add(all_embeddings)

    # Example query
    query = ""
    print(f"\nQuery: {query}")

    # Retrieve relevant chunks
    relevant_chunks = retrieve_relevant_chunks(query, index, all_chunks)
    print("\nRelevant chunks from the PDF:")
    for chunk in relevant_chunks:
        print(chunk)
        print("-" * 80)

    # Search for vectors in the database
    query_embedding = model.encode([query], convert_to_tensor=True).cpu().numpy()
    distances, indices = search_vector(index, query_embedding)
    print(f"\nSearch results for query '{query}':")
    print(f"Distances: {distances}")
    print(f"Indices: {indices}")


# Function to generate a response using the RAG system and an LLM
def generate_response(
    query: str, db: VectorDatabase, model: SentenceTransformer, llm: Any
) -> str:
    """
    Generate a response using the RAG system and an LLM.

    Args:
        query: The user query.
        db: The vector database.
        model: The embedding model.
        llm: The LLM used to generate the response.

    Returns:
        The generated response.
    """
    # Load all vectors and chunks from the database
    chunks, embeddings = load_vectors_from_database(db)

    # Create FAISS index from the database
    index, _ = create_faiss_index_from_database(db)

    # Retrieve relevant chunks
    relevant_chunks = retrieve_relevant_chunks(query, index, chunks, top_k=5)

    # Combine the relevant chunks into a single context
    context = " ".join(relevant_chunks)

    # Generate a response using the LLM
    response = ollama.generate(
        model="qwen3:14b",
        prompt=f"Use the following context to answer the query: {context}\nQuery: {query}",
    )
    return response


# Function to create FAISS index from all vectors in the database
def create_faiss_index_from_database(
    db: VectorDatabase,
) -> Tuple[faiss.Index, np.ndarray]:
    """Create a FAISS index from all vectors in the database."""
    chunks, embeddings = load_vectors_from_database(db)

    if len(embeddings) == 0:
        raise ValueError("No vectors found in the database.")

    d = embeddings.shape[1]
    num_clusters = min(128, len(embeddings))
    index = faiss.IndexIVFFlat(faiss.IndexFlatL2(d), d, num_clusters)
    index.train(embeddings[: min(500, len(embeddings))])
    index.add(embeddings)
    return index, embeddings


# Function to load all vectors and chunks from the database
def load_vectors_from_database(db: VectorDatabase) -> Tuple[List[str], np.ndarray]:
    """Load all vectors and chunks from the database."""
    all_vectors = db.get_all_vectors()
    chunks = []
    embeddings = []

    for row in all_vectors:
        if isinstance(row, tuple):
            _, embedding, metadata_str = row
        else:
            continue

        try:
            metadata = eval(metadata_str)
        except Exception as e:
            print(f"Error converting metadata: {metadata_str} - {e}")
            continue

        chunk = metadata.get("chunk", "")
        chunks.append(chunk)
        embeddings.append(np.frombuffer(embedding, dtype=np.float32))

    embeddings = np.array(embeddings)
    return chunks, embeddings


# Function to create FAISS index from all vectors in the database
def create_faiss_index_from_database(
    db: VectorDatabase,
) -> Tuple[faiss.Index, np.ndarray]:
    """Create a FAISS index from all vectors in the database."""
    chunks, embeddings = load_vectors_from_database(db)

    if len(embeddings) == 0:
        raise ValueError("No vectors found in the database.")

    d = embeddings.shape[1]
    num_clusters = min(128, len(embeddings))
    index = faiss.IndexIVFFlat(faiss.IndexFlatL2(d), d, num_clusters)
    index.train(embeddings[: min(500, len(embeddings))])
    index.add(embeddings)
    return index, embeddings


# Function to load all vectors and chunks from the database
def load_vectors_from_database(db: VectorDatabase) -> Tuple[List[str], np.ndarray]:
    """Load all vectors and chunks from the database."""
    all_vectors = db.get_all_vectors()
    chunks = []
    embeddings = []

    for row in all_vectors:
        if isinstance(row, tuple):
            _, embedding, metadata_str = row
        else:
            continue

        try:
            metadata = eval(metadata_str)
        except Exception as e:
            print(f"Error converting metadata: {metadata_str} - {e}")
            continue

        chunk = metadata.get("chunk", "")
        chunks.append(chunk)
        embeddings.append(np.frombuffer(embedding, dtype=np.float32))

    embeddings = np.array(embeddings)
    return chunks, embeddings


# if __name__ == "__main__":
#     main()
