"""In-memory registry of parsed ARXML artifacts.

Shared by the REST API and the agent tools so an artifact uploaded through the UI is
immediately queryable by the agent workflows (topology, neighbours, ECUC lookup).
Tenant scoping is enforced on every access.
"""
from __future__ import annotations

import threading

from .models import ArxmlTopology

_lock = threading.Lock()
_ARTIFACTS: dict[str, dict] = {}


def put_artifact(topo: ArxmlTopology, graph: dict) -> str:
    artifact_id = topo.artifact.artifact_id
    with _lock:
        _ARTIFACTS[artifact_id] = {"topology": topo, "graph": graph}
    return artifact_id


def get_artifact(artifact_id: str, tenant_id: str = "default") -> dict | None:
    entry = _ARTIFACTS.get(artifact_id)
    if not entry:
        return None
    if tenant_id and entry["topology"].artifact.tenant_id != tenant_id:
        return None
    return entry


def list_artifacts(tenant_id: str = "default") -> list[dict]:
    out = []
    for aid, entry in _ARTIFACTS.items():
        topo = entry["topology"]
        if tenant_id and topo.artifact.tenant_id != tenant_id:
            continue
        out.append({"artifact_id": aid, "source": topo.artifact.source_path,
                    "tenant_id": topo.artifact.tenant_id,
                    "project_scope": topo.artifact.project_scope,
                    "release": topo.artifact.autosar_release,
                    "components": len(topo.components), "ports": len(topo.ports),
                    "interfaces": len(topo.interfaces), "connectors": len(topo.connectors),
                    "runnables": len(topo.runnables),
                    "ecuc_parameters": len(topo.ecuc_parameters)})
    return out


def clear() -> None:
    with _lock:
        _ARTIFACTS.clear()
