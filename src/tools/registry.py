"""Global tool registry: the single source of truth for what the agent and the API
can call.  Schemas are plain JSON Schema so they can be handed to an OpenAI-compatible
provider or an Ollama model with native tool calling.
"""
from __future__ import annotations

from .base import REGISTRY, ToolRegistry
from . import arxml as _arxml
from . import code as _code
from . import graphrag as _graphrag
from . import mindmap as _mindmap
from . import traceability as _trace

_STR = {"type": "string"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}


def _schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props,
            "required": required or []}


def build_registry() -> ToolRegistry:
    """Create a fresh registry populated with every tool (idempotent per registry)."""
    reg = ToolRegistry()

    # ------------------------------------------------------------------ graph
    reg.register(_spec(
        "graph.search",
        "Search the automotive knowledge graph (specs, ARXML, C code, tests). "
        "mode=local (entity neighbourhood), global (community summaries) or hybrid.",
        _schema({"query": _STR, "mode": {"type": "string",
                                         "enum": ["local", "global", "hybrid"]},
                 "depth": _INT, "limit": _INT}, ["query"]),
        _graphrag.graph_search, tags=["graph", "retrieval"]))

    reg.register(_spec(
        "graph.neighbors",
        "Neighbourhood subgraph of one knowledge-graph node (label or type:label id).",
        _schema({"node": _STR, "depth": _INT, "limit": _INT}, ["node"]),
        _graphrag.graph_neighbors, tags=["graph"]))

    reg.register(_spec(
        "graph.path",
        "Shortest relationship path between two knowledge-graph nodes.",
        _schema({"source": _STR, "target": _STR, "max_depth": _INT}, ["source", "target"]),
        _graphrag.graph_path, tags=["graph"]))

    reg.register(_spec(
        "graph.communities",
        "List knowledge-graph communities, optionally ranked against a query.",
        _schema({"query": _STR, "limit": _INT}, []),
        _graphrag.graph_communities, tags=["graph"]))

    reg.register(_spec(
        "graph.community",
        "Details and members of one knowledge-graph community.",
        _schema({"community_id": _STR}, ["community_id"]),
        _graphrag.graph_community, tags=["graph"]))

    reg.register(_spec(
        "graph.stats",
        "Node, edge, community and traceability counts of the knowledge graph.",
        _schema({}, []),
        _graphrag.graph_stats, tags=["graph", "admin"]))

    reg.register(_spec(
        "graph.build",
        "Rebuild the knowledge graph from the canonical store and optional code folders.",
        _schema({"canonical_db": _STR, "code_dirs": _STR_LIST, "clear": _BOOL}, []),
        _graphrag.graph_build, tags=["graph", "admin"], mutating=True))

    # --------------------------------------------------------------- mindmap
    reg.register(_spec(
        "mindmap.build",
        "Build a Mermaid mindmap for a topic from the knowledge graph, from retrieval "
        "evidence or from an explicit outline.",
        _schema({"topic": _STR,
                 "source": {"type": "string", "enum": ["auto", "graph", "evidence", "outline"]},
                 "depth": _INT,
                 "outline": {"type": "array", "items": {"type": "object"}}}, ["topic"]),
        _mindmap_tool, tags=["mindmap", "visualisation"]))

    # ----------------------------------------------------------------- arxml
    reg.register(_spec(
        "arxml.artifacts", "List the parsed ARXML artifacts of the tenant.",
        _schema({"tenant": _STR}, []),
        _arxml.arxml_artifacts, tags=["arxml"]))

    reg.register(_spec(
        "arxml.topology",
        "Deterministic ARXML topology: components, ports, interfaces, runnables, "
        "connectors and ECUC values with XPath provenance.",
        _schema({"artifact_id": _STR, "tenant": _STR}, ["artifact_id"]),
        _arxml.arxml_topology, tags=["arxml"]))

    reg.register(_spec(
        "arxml.neighbors",
        "Neighbourhood of a node inside the ARXML graph (max depth 3).",
        _schema({"node_id": _STR, "artifact_id": _STR, "tenant": _STR, "depth": _INT},
                ["node_id", "artifact_id"]),
        _arxml.arxml_neighbors, tags=["arxml"]))

    reg.register(_spec(
        "arxml.search",
        "Search ARXML components, ports, interfaces, runnables and ECUC parameters.",
        _schema({"query": _STR, "artifact_id": _STR, "tenant": _STR, "limit": _INT},
                ["query"]),
        _arxml.arxml_search, tags=["arxml"]))

    reg.register(_spec(
        "arxml.config",
        "Look up ECUC configuration parameters and their values.",
        _schema({"parameter": _STR, "artifact_id": _STR, "tenant": _STR, "limit": _INT},
                ["parameter"]),
        _arxml.arxml_config, tags=["arxml", "configuration"]))

    # ------------------------------------------------------------------ code
    reg.register(_spec(
        "code.symbols",
        "List functions, includes and RTE call sites of a C file or of the indexed code.",
        _schema({"path": _STR, "source": _STR, "module": _STR}, []),
        _code.code_symbols, tags=["code"]))

    reg.register(_spec(
        "code.callgraph",
        "Call graph around a C function (callers and callees with file/line).",
        _schema({"function": _STR, "path": _STR, "source": _STR, "depth": _INT},
                ["function"]),
        _code.code_callgraph, tags=["code"]))

    reg.register(_spec(
        "code.rte_map",
        "Map RTE_* call sites to ARXML ports (name-overlap evidence).",
        _schema({"source": _STR, "path": _STR, "port_names": _STR_LIST}, []),
        _code.code_rte_map, tags=["code", "traceability"]))

    reg.register(_spec(
        "code.analyze",
        "Advisory static checks on a C snippet (never a compliance verdict).",
        _schema({"source": _STR, "path": _STR}, ["source"]),
        _code.code_analyze, tags=["code", "quality"]))

    # ----------------------------------------------------------- traceability
    reg.register(_spec(
        "trace.links", "Raw traceability links between requirements, code and tests.",
        _schema({"source_type": _STR, "source_id": _STR, "target_type": _STR,
                 "target_id": _STR, "limit": _INT}, []),
        _trace.trace_links, tags=["traceability"]))

    reg.register(_spec(
        "trace.requirements",
        "Requirements reachable from a symbol, port, module or API name.",
        _schema({"query": _STR, "limit": _INT}, ["query"]),
        _trace.trace_requirements, tags=["traceability"]))

    reg.register(_spec(
        "trace.tests", "Test cases covering a requirement or an API.",
        _schema({"query": _STR, "limit": _INT}, ["query"]),
        _trace.trace_tests, tags=["traceability"]))

    reg.register(_spec(
        "trace.matrix",
        "Requirement / API / code / test matrix for a module.",
        _schema({"module": _STR, "limit": _INT}, []),
        _trace.trace_matrix, tags=["traceability"]))

    reg.register(_spec(
        "trace.gaps",
        "Requirements without an implementation or without a test case.",
        _schema({"module": _STR}, []),
        _trace.trace_gaps, tags=["traceability", "quality"]))

    return reg


def _spec(name: str, description: str, parameters: dict, fn, tags: list[str],
          mutating: bool = False):
    from .base import ToolSpec
    return ToolSpec(name=name, description=description, parameters=parameters,
                    fn=fn, tags=tags, mutating=mutating)


def _mindmap_tool(topic: str, source: str = "auto", depth: int = 2,
                  outline: list[dict] | None = None) -> dict:
    """Adapter that lets the mindmap module be registered as a tool."""
    from ..graphrag.runtime import get_store
    return _mindmap.build_mindmap(topic=topic, source=source, store=get_store(),
                                   outline=outline, depth=depth)


def install() -> ToolRegistry:
    """Install every tool into the process-wide registry."""
    reg = build_registry()
    for spec in reg.specs():
        if REGISTRY.get(spec.name) is None:
            REGISTRY.register(spec)
    return REGISTRY
