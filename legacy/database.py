# database.py
import ast
import json
import sqlite3
import numpy as np


def _parse_metadata(s: str) -> dict:
    """JSON-first metadata parsing (legacy str(dict) rows still readable)."""
    try:
        return json.loads(s)
    except Exception:
        try:
            return ast.literal_eval(s)
        except Exception:
            return {}

class VectorDatabase:
    def __init__(self, db_path='vector_database.db'):
        self.db_path = db_path
        self._initialize_database()

    def _initialize_database(self):
        """Initialize the SQLite database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS vectors
                     (id INTEGER PRIMARY KEY, embedding BLOB, metadata TEXT)''')
        conn.commit()
        conn.close()

    def insert_vector(self, embedding: np.ndarray, metadata: dict):
        """Insert a vector into the database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT INTO vectors (embedding, metadata) VALUES (?, ?)",
                  (embedding.tobytes(), json.dumps(metadata)))
        conn.commit()
        conn.close()

    def get_all_vectors(self):
        """Retrieve all vectors from the database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM vectors")
        rows = c.fetchall()
        conn.close()
        return rows

    def get_vector_by_id(self, vector_id: int):
        """Retrieve a vector by ID from the database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM vectors WHERE id=?", (vector_id,))
        row = c.fetchone()
        conn.close()
        return row

    def update_vector_by_id(self, vector_id: int, embedding: np.ndarray, metadata: dict):
        """Update a vector by ID in the database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE vectors SET embedding=?, metadata=? WHERE id=?",
                  (embedding.tobytes(), json.dumps(metadata), vector_id))
        conn.commit()
        conn.close()

    def delete_vector_by_id(self, vector_id: int):
        """Delete a vector by ID from the database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM vectors WHERE id=?", (vector_id,))
        conn.commit()
        conn.close()

    def get_all_metadata(self):
        """Retrieve all metadata from the database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT metadata FROM vectors")
        metadata_rows = c.fetchall()
        conn.close()

        # Extract metadata strings and convert to dictionaries
        metadata_list = []
        for row in metadata_rows:
            if row[0]:
                metadata_list.append(_parse_metadata(row[0]))
        return metadata_list