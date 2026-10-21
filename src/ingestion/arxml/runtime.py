"""Persistent ARXML runtime (Phase 4).

The v1 API keeps parsed ARXML in an in-memory dict, so an upload is lost when
the server restarts. The runtime stores each topology on disk, addressed by the
artifact id derived from the file's content hash, and can re-hydrate it.

Nothing is re-parsed to serve a request: the parsed structure is the artifact.
The raw bytes live in the object store (ADR-0012) and the provenance lives in
the registry (ADR-0002) — this store holds the *structure*.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import ArxmlTopology

__all__ = ["ArxmlRuntime"]


class ArxmlRuntime:
    """A file-backed store of parsed ARXML topologies."""

    def __init__(self, root: str = "data/canonical/arxml"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, artifact_id: str) -> Path:
        safe = "".join(ch for ch in artifact_id if ch.isalnum() or ch in "-_")
        if not safe:
            raise ValueError(f"invalid artifact id: {artifact_id!r}")
        return self.root / f"{safe}.json"

    def put(self, topology: ArxmlTopology) -> str:
        """Store a topology and return its artifact id."""
        artifact_id = topology.artifact.artifact_id
        payload = {"topology": topology.model_dump()}
        path = self._path(artifact_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return artifact_id

    def get(self, artifact_id: str) -> ArxmlTopology | None:
        """Re-hydrate a stored topology, or None when it is not there."""
        try:
            path = self._path(artifact_id)
        except ValueError:
            return None
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return ArxmlTopology.model_validate(payload["topology"])
        except (OSError, ValueError, KeyError):
            return None

    def list(self) -> list[dict]:
        """A summary of every stored artifact."""
        out: list[dict] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                topology = ArxmlTopology.model_validate(payload["topology"])
            except (OSError, ValueError, KeyError):
                continue
            artifact = topology.artifact
            out.append({
                "artifact_id": artifact.artifact_id,
                "source_path": artifact.source_path,
                "source_sha256": artifact.source_sha256,
                "autosar_release": artifact.autosar_release,
                "schema_version": artifact.autosar_schema_version,
                "parse_status": artifact.parse_status,
                "tenant_id": artifact.tenant_id,
                "project_scope": artifact.project_scope,
                "counts": {
                    "components": len(topology.components),
                    "ports": len(topology.ports),
                    "interfaces": len(topology.interfaces),
                    "connectors": len(topology.connectors),
                    "runnables": len(topology.runnables),
                    "ecuc_parameters": len(topology.ecuc_parameters),
                },
            })
        return out

    def delete(self, artifact_id: str) -> bool:
        try:
            path = self._path(artifact_id)
        except ValueError:
            return False
        if not path.exists():
            return False
        path.unlink()
        return True
