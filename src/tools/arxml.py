"""ARXML tools: deterministic topology exploration for the agent workflows.

The ARXML model is parsed deterministically first; these tools expose that structure
(components, ports, interfaces, runnables, connectors, ECUC values) with XPath
provenance.  They never guess: unresolved references are reported as such.
"""
from __future__ import annotations

from ..ingestion.arxml import runtime as ar_runtime


def arxml_artifacts(tenant: str = "default") -> dict:
    """All ARXML artifacts visible for the tenant."""
    return {"artifacts": ar_runtime.list_artifacts(tenant)}


def arxml_topology(artifact_id: str, tenant: str = "default") -> dict:
    """Full topology of one artifact (typed model dump)."""
    entry = ar_runtime.get_artifact(artifact_id, tenant)
    if not entry:
        return {"found": False, "artifact_id": artifact_id,
                "error": "artifact not found or access denied"}
    topo = entry["topology"]
    return {"found": True, "artifact_id": artifact_id,
            "artifact": topo.artifact.model_dump(),
            "components": [c.model_dump() for c in topo.components],
            "ports": [p.model_dump() for p in topo.ports],
            "interfaces": [i.model_dump() for i in topo.interfaces],
            "connectors": [c.model_dump() for c in topo.connectors],
            "runnables": [r.model_dump() for r in topo.runnables],
            "ecuc_parameters": [e.model_dump() for e in topo.ecuc_parameters],
            "unresolved_refs": topo.unresolved_refs,
            "warnings": topo.artifact.validation_warnings}


def arxml_neighbors(node_id: str, artifact_id: str, tenant: str = "default",
                    depth: int = 1) -> dict:
    """Graph neighbourhood of a node inside the ARXML projection."""
    from ..ingestion.arxml.graph_export import neighbors
    entry = ar_runtime.get_artifact(artifact_id, tenant)
    if not entry:
        return {"found": False, "error": "artifact not found or access denied"}
    res = neighbors(entry["graph"], node_id, depth=min(max(1, depth), 3))
    res["found"] = True
    res["artifact_id"] = artifact_id
    return res


def arxml_search(query: str, artifact_id: str = "", tenant: str = "default",
                 limit: int = 40) -> dict:
    """Search ARXML nodes (component / port / interface / runnable / ECUC) by name."""
    q = (query or "").lower()
    hits: list[dict] = []
    artifacts = ([artifact_id] if artifact_id
                 else [a["artifact_id"] for a in ar_runtime.list_artifacts(tenant)])
    for aid in artifacts:
        entry = ar_runtime.get_artifact(aid, tenant)
        if not entry:
            continue
        topo = entry["topology"]
        for c in topo.components:
            if q in c.qualified_name.lower() or q in c.short_name.lower():
                hits.append({"artifact_id": aid, "kind": "component", "id": c.qualified_name,
                             "label": c.short_name, "type": c.component_type,
                             "xpath": c.source_xpath})
        for p in topo.ports:
            if q in p.qualified_name.lower() or q in p.short_name.lower():
                hits.append({"artifact_id": aid, "kind": "port", "id": p.qualified_name,
                             "label": p.short_name, "type": p.direction,
                             "interface": p.interface_ref, "xpath": p.source_xpath})
        for i in topo.interfaces:
            if q in i.qualified_name.lower() or q in i.short_name.lower():
                hits.append({"artifact_id": aid, "kind": "interface", "id": i.qualified_name,
                             "label": i.short_name, "type": i.interface_type,
                             "xpath": i.source_xpath})
        for r in topo.runnables:
            if q in r.qualified_name.lower() or q in r.short_name.lower():
                hits.append({"artifact_id": aid, "kind": "runnable", "id": r.qualified_name,
                             "label": r.short_name, "type": "runnable",
                             "symbol": r.symbol, "xpath": r.source_xpath})
        for e in topo.ecuc_parameters:
            if q in e.qualified_path.lower() or q in e.short_name.lower():
                hits.append({"artifact_id": aid, "kind": "ecuc_parameter",
                             "id": e.qualified_path or e.short_name, "label": e.short_name,
                             "type": e.value_type, "value": e.value,
                             "definition_ref": e.definition_ref, "xpath": e.source_xpath})
        if len(hits) >= limit:
            break
    return {"query": query, "hits": hits[:limit], "hit_count": len(hits)}


def arxml_config(parameter: str, artifact_id: str = "", tenant: str = "default",
                 limit: int = 40) -> dict:
    """Look up ECUC configuration parameters (value + definition + container)."""
    q = (parameter or "").lower()
    hits: list[dict] = []
    artifacts = ([artifact_id] if artifact_id
                 else [a["artifact_id"] for a in ar_runtime.list_artifacts(tenant)])
    for aid in artifacts:
        entry = ar_runtime.get_artifact(aid, tenant)
        if not entry:
            continue
        for e in entry["topology"].ecuc_parameters:
            path = (e.qualified_path or e.short_name).lower()
            if q in path or q in e.short_name.lower():
                hits.append({"artifact_id": aid, "parameter": e.qualified_path or e.short_name,
                             "short_name": e.short_name, "value": e.value,
                             "value_type": e.value_type,
                             "definition_ref": e.definition_ref,
                             "container": e.container_path, "xpath": e.source_xpath})
        if len(hits) >= limit:
            break
    return {"parameter": parameter, "hits": hits[:limit], "hit_count": len(hits)}
