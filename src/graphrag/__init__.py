"""GraphRAG layer: local-first knowledge graph over specs, ARXML, code and tests."""
from .store import GraphStore, TraceLink, node_id
from .builder import build_graph, build_from_canonical
from .community import detect_communities, summarize_community
from .retrieval import local_search, global_search, hybrid_search, rrf_fuse

__all__ = [
    "GraphStore", "TraceLink", "node_id",
    "build_graph", "build_from_canonical",
    "detect_communities", "summarize_community",
    "local_search", "global_search", "hybrid_search", "rrf_fuse",
]
