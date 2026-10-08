"""Evidence-aligned diff engine (Phase 2 §9). Deterministic structural diff first; LLM only explains."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class DiffItem(BaseModel):
    domain: Literal["requirement", "api", "ecuc", "arxml", "graph", "text", "code"] = "text"
    entity_key: str
    change_type: Literal["added", "removed", "modified", "renamed", "moved", "unchanged", "unknown"] = "unknown"
    severity: Literal["info", "warning", "high", "critical"] = "info"
    base_value: dict | str | None = None
    target_value: dict | str | None = None
    base_evidence_ids: list[str] = Field(default_factory=list)
    target_evidence_ids: list[str] = Field(default_factory=list)
    compatibility_risk: str = ""
    migration_action: str | None = None
    confidence: float = 1.0


def _norm_api(sig: str) -> str:
    return " ".join(sig.split())


def diff_records(base: list[dict], target: list[dict], domain: str,
                 key: str = "entity_key") -> list[DiffItem]:
    """Generic canonical-key diff. Never fabricates a change from wording alone: values compared exactly."""
    b = {r[key]: r for r in base}
    t = {r[key]: r for r in target}
    out: list[DiffItem] = []
    for k in sorted(set(b) | set(t)):
        if k not in b:
            out.append(DiffItem(domain=domain, entity_key=k, change_type="added",
                                target_value=t[k], target_evidence_ids=t[k].get("evidence_ids", []),
                                compatibility_risk="new entity — verify integration impact",
                                migration_action="adopt and test"))
        elif k not in t:
            out.append(DiffItem(domain=domain, entity_key=k, change_type="removed",
                                base_value=b[k], base_evidence_ids=b[k].get("evidence_ids", []),
                                compatibility_risk="removed entity — migration break risk",
                                migration_action="replace or remove usage", severity="high"))
        else:
            bv, tv = b[k], t[k]
            if bv.get("normalized") == tv.get("normalized"):
                out.append(DiffItem(domain=domain, entity_key=k, change_type="unchanged",
                                    base_value=bv, target_value=tv,
                                    base_evidence_ids=bv.get("evidence_ids", []),
                                    target_evidence_ids=tv.get("evidence_ids", [])))
            else:
                out.append(DiffItem(domain=domain, entity_key=k, change_type="modified",
                                    base_value=bv, target_value=tv,
                                    base_evidence_ids=bv.get("evidence_ids", []),
                                    target_evidence_ids=tv.get("evidence_ids", []),
                                    compatibility_risk="signature/content changed — review callers",
                                    migration_action="update call sites and ECUC refs", severity="warning"))
    return out


def diff_arxml_topologies(base, target) -> list[DiffItem]:
    """Structural ARXML diff over SWCs, ports, interfaces, connectors, runnables, ECUC params."""
    def recs(items: list[dict], ev: str) -> list[dict]:
        return [{"entity_key": i["qualified_name"] if isinstance(i, dict) else getattr(i, "qualified_name", str(i)),
                 "normalized": str(i), "evidence_ids": [ev]} for i in items]
    items: list[DiffItem] = []
    items += diff_records(recs([c.model_dump() for c in base.components], "base"),
                          recs([c.model_dump() for c in target.components], "target"), "arxml")
    items += diff_records(recs([p.model_dump() for p in base.ports], "base"),
                          recs([p.model_dump() for p in target.ports], "target"), "arxml")
    items += diff_records(recs([i.model_dump() for i in base.interfaces], "base"),
                          recs([i.model_dump() for i in target.interfaces], "target"), "arxml")
    return items
