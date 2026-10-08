"""Typed ARXML graph projection. Deterministic edges only; inferred edges flagged, never normative."""
from __future__ import annotations

from src.ingestion.arxml.models import ArxmlTopology


def _edge(src: str, rel: str, dst: str, topo: ArxmlTopology, inferred: bool = False,
          confidence: float = 1.0, method: str = "") -> dict:
    return {"src": src, "rel": rel, "dst": dst, "tenant_id": topo.artifact.tenant_id,
            "project_id": topo.artifact.project_scope, "artifact_id": topo.artifact.artifact_id,
            "source_file": topo.artifact.source_path, "source_sha256": topo.artifact.source_sha256,
            "release": topo.artifact.autosar_release, "confidence": confidence,
            "is_inferred": inferred, "inference_method": method}


def export_graph(topo: ArxmlTopology) -> dict:
    nodes = [{"id": topo.artifact.artifact_id, "type": "ArxmlArtifact", "label": topo.artifact.source_path}]
    edges: list[dict] = []
    for c in topo.components:
        nodes.append({"id": c.qualified_name, "type": "Composition" if "COMPOSITION" in c.component_type else "SoftwareComponent",
                      "label": c.short_name, "xpath": c.source_xpath})
        edges.append(_edge(topo.artifact.artifact_id, "CONTAINS", c.qualified_name, topo))
        for p in c.ports:
            edges.append(_edge(c.qualified_name, "HAS_PORT", p, topo))
    for p in topo.ports:
        nodes.append({"id": p.qualified_name, "type": "Port",
                      "label": f"{p.short_name} ({p.direction})", "xpath": p.source_xpath})
        if p.interface_ref:
            edges.append(_edge(p.qualified_name, "REFERENCES_INTERFACE", p.interface_ref, topo))
    for i in topo.interfaces:
        nodes.append({"id": i.qualified_name, "type": "PortInterface",
                      "label": f"{i.short_name} [{i.interface_type}]", "xpath": i.source_xpath})
    for r in topo.runnables:
        nodes.append({"id": r.qualified_name, "type": "Runnable", "label": r.short_name, "xpath": r.source_xpath})
    for c in topo.connectors:
        if c.provider_port_ref and c.requester_port_ref:
            edges.append(_edge(c.requester_port_ref,
                               "ASSEMBLY_CONNECTS" if c.connector_type == "assembly" else "DELEGATES_TO",
                               c.provider_port_ref, topo))
    for e in topo.ecuc_parameters:
        nodes.append({"id": e.qualified_path or e.short_name, "type": "EcucParameter", "label": e.short_name})
    return {"nodes": nodes, "edges": edges, "unresolved": topo.unresolved_refs}


def neighbors(graph: dict, node_id: str, depth: int = 1) -> dict:
    seen = {node_id}
    frontier = {node_id}
    out_edges = []
    for _ in range(max(1, depth)):
        nxt = set()
        for e in graph.get("edges", []):
            if e["src"] in frontier and e["dst"] not in seen:
                out_edges.append(e)
                seen.add(e["dst"])
                nxt.add(e["dst"])
            elif e["dst"] in frontier and e["src"] not in seen:
                out_edges.append(e)
                seen.add(e["src"])
                nxt.add(e["src"])
        frontier = nxt
        if not frontier:
            break
    return {"node_id": node_id,
            "nodes": [n for n in graph.get("nodes", []) if n["id"] in seen],
            "edges": out_edges}
