"""Deterministic entity + relation extraction for the GraphRAG knowledge graph.

No model calls here: extraction is rule based so the graph is reproducible, diffable
and reviewable by an engineer.  Every extracted relation carries the evidence that
produced it (chunk id / file / line) and an `is_inferred` flag.

Supported artifact families:

* AUTOSAR specification chunks (requirement IDs, API names, ECUC parameters, modules,
  error codes, cross references)
* C / C++ implementation sources (functions, `Rte_*` calls, includes, module prefixes)
* Test sources (test-case identifiers, `covers` / `requires` annotations)
* ARXML topologies (delegated to `src.ingestion.arxml.graph_export`)
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------- patterns
REQ_ID_RE = re.compile(r"\b(?:SWS|SRS|RS|REQ|TSW|TPS|ASR|SWS_[A-Z0-9]+)_[A-Za-z0-9]+_\d{3,6}\b")
REQ_ID_SIMPLE_RE = re.compile(r"\bSWS_[A-Za-z0-9]+_\d{3,6}\b")
ERROR_CODE_RE = re.compile(r"\b(?:[A-Z]{2,6}_)?E(?:rr|rror)?_?[0-9]{2,6}\b|\bE_[A-Z]{2,6}_[0-9]{2,6}\b")
TESTCASE_RE = re.compile(r"\b(?:TEST|TC|TESTCASE|TEST_CASE|UT|IT|AT)_[A-Za-z0-9_]{3,}\b")
FUNC_DEF_RE = re.compile(
    r"^[ \t]*(?:(?:static|inline|extern|const|volatile|unsigned|signed|void|char|int|long|"
    r"short|float|double|bool|size_t|uint\d+_t|int\d+_t)\s+)*"
    r"(?P<name>[A-Za-z_]\w*)\s*\([^;{]*\)\s*\{", re.M)
RTE_CALL_RE = re.compile(r"\bRte_(?:Read|Write|Call|Mode|Invalidate|Receive|Send|Start|Stop|"
                         r"Trigger|Event|Impl|Dummy|Init|Periodic)\w*")
INCLUDE_RE = re.compile(r'^[ \t]*#\s*include\s*[<"]([^>"]+)[>"]', re.M)
ANNOTATION_RE = re.compile(r"@(?:covers?|requires?|verifies?|tests?|validates?|requirement|ref)\s*"
                           r"[:=]?\s*([A-Za-z0-9_.\-]+)", re.I)

AUTOSAR_MODULES = (
    "CanIf", "CanDrv", "CanSM", "CanTp", "PduR", "Pdu", "Com", "ComM", "Nm", "EcuC",
    "Dcm", "Dem", "NvM", "Eep", "Fls", "Fee", "Spi", "Adc", "I2c", "Wdg", "WdgM",
    "Gpt", "Mcu", "Port", "Dio", "Pwm", "Act", "Icu", "Lin", "Eth", "Uds", "DoIP",
    "SOME-IP", "SomeIp", "SomeIpTp", "Tp", "IpduM", "SecOC", "Crypto", "Rte",
    "Dsa", "Dsw", "EcuAb", "BswM", "Esm", "Crc", "Sec", "Rsa", "Ea", "NvM",
)

# tokens that are never interesting graph nodes
_STOP_LABELS = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "is", "are",
                "this", "that", "with", "by", "from", "on", "as", "be", "it"}


@dataclass
class Entity:
    type: str
    label: str
    properties: dict = field(default_factory=dict)


@dataclass
class Relation:
    src_type: str
    src: str
    dst_type: str
    dst: str
    rel: str
    confidence: float = 0.8
    is_inferred: bool = True
    provenance: dict = field(default_factory=dict)


# ------------------------------------------------------------------ spec chunks
def extract_chunk_entities(chunk: dict) -> tuple[list[Entity], list[Relation]]:
    """Entities + relations implied by one canonical chunk."""
    ents: list[Entity] = []
    rels: list[Relation] = []
    text = chunk.get("normalized_text") or chunk.get("text") or ""
    chunk_id = chunk.get("chunk_id", "")
    prov = {"chunk_id": chunk_id, "source_pdf": chunk.get("source_pdf", ""),
            "page": int(chunk.get("page_start") or 0),
            "release": chunk.get("autosar_release", ""),
            "platform": chunk.get("platform", "")}

    module = (chunk.get("module") or "").strip()
    if module:
        ents.append(Entity("module", module, {"release": chunk.get("autosar_release", "")}))

    for req in _dedupe(chunk.get("requirement_ids") or []) + REQ_ID_RE.findall(text) + REQ_ID_SIMPLE_RE.findall(text):
        if not _is_concrete_requirement(req):
            continue
        ents.append(Entity("requirement", req, {"release": chunk.get("autosar_release", "")}))

    for api in _dedupe(chunk.get("api_names") or []):
        ents.append(Entity("api", api, {}))

    for ecuc in _dedupe(chunk.get("ecu_parameters") or []):
        ents.append(Entity("ecuc_parameter", ecuc, {}))

    for code in _dedupe(ERROR_CODE_RE.findall(text)):
        ents.append(Entity("error_code", code, {}))

    doc_id = chunk.get("document_id", "")
    if doc_id:
        ents.append(Entity("document", doc_id, {"source_pdf": chunk.get("source_pdf", ""),
                                                "release": chunk.get("autosar_release", "")}))

    known_apis = [a for a in (chunk.get("api_names") or [])]
    known_reqs = [r for r in _dedupe(chunk.get("requirement_ids") or [])
                  if _is_concrete_requirement(r)]
    for m in AUTOSAR_MODULES:
        if re.search(rf"\b{re.escape(m)}\b", text):
            ents.append(Entity("module", m, {}))

    # edges: document -contains-> entities, module -implements-> api, api -satisfies-> requirement
    if doc_id:
        for e in ents:
            if e.type in ("requirement", "api", "ecuc_parameter", "error_code", "module"):
                rels.append(Relation("document", doc_id, e.type, e.label, "contains",
                                     confidence=0.95, is_inferred=False, provenance=prov))
    for api in known_apis:
        for m in _modules_for(api, chunk):
            rels.append(Relation("module", m, "api", api, "implements",
                                 confidence=0.75, is_inferred=True, provenance=prov))
    for req in known_reqs:
        for api in known_apis:
            rels.append(Relation("api", api, "requirement", req, "satisfies",
                                 confidence=0.6, is_inferred=True, provenance=prov))
    if module and known_apis:
        for api in known_apis:
            rels.append(Relation("module", module, "api", api, "implements",
                                 confidence=0.8, is_inferred=True, provenance=prov))
    # cross references inside the prose
    for api in known_apis:
        for other in _dedupe(chunk.get("api_names") or []):
            if other != api and other in text:
                rels.append(Relation("api", api, "api", other, "references",
                                     confidence=0.55, is_inferred=True, provenance=prov))
    return ents, rels


def _is_concrete_requirement(label: str) -> bool:
    """Requirement ids must carry a numeric suffix (e.g. ``SWS_Com_00123``).

    The canonical store also keeps family prefixes such as ``PRS_E2E_``; those are
    not requirements and would pollute the graph with empty nodes.
    """
    text = (label or "").strip()
    if len(text) < 5 or " " in text:
        return False
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*_\d{3,6}$", text))


def _modules_for(api: str, chunk: dict) -> list[str]:
    out: list[str] = []
    m = (chunk.get("module") or "").strip()
    if m:
        out.append(m)
    for mod in AUTOSAR_MODULES:
        if api.startswith(mod + "_"):
            out.append(mod)
    return _dedupe(out)


# ----------------------------------------------------------------------- code
def extract_code_entities(path: str, text: str) -> tuple[list[Entity], list[Relation]]:
    ents: list[Entity] = []
    rels: list[Relation] = []
    base = os.path.basename(path)
    prov = {"file": path, "source": base}

    functions: list[str] = []
    for m in FUNC_DEF_RE.finditer(text):
        name = m.group("name")
        if name in _STOP_LABELS or name.startswith(("if", "for", "while", "switch", "return")):
            continue
        line = text[: m.start()].count("\n") + 1
        functions.append(name)
        ents.append(Entity("function", name, {"file": path, "line": line,
                                               "source": base}))
        rels.append(Relation("document", base, "function", name, "defined_in",
                             confidence=0.9, is_inferred=False,
                             provenance={**prov, "line": line}))

    for inc in _dedupe(INCLUDE_RE.findall(text)):
        ents.append(Entity("concept", inc, {"file": path}))

    rte_calls = _dedupe(RTE_CALL_RE.findall(text))
    for call in rte_calls:
        ents.append(Entity("api", call, {"file": path}))
        rels.append(Relation("function", _enclosing_function(text, call) or base,
                             "api", call, "calls", confidence=0.85, is_inferred=False,
                             provenance=prov))
    for fn in functions:
        for mod in AUTOSAR_MODULES:
            if fn.startswith(mod + "_"):
                rels.append(Relation("module", mod, "function", fn, "implements",
                                     confidence=0.7, is_inferred=True, provenance=prov))
    # module -> rte api
    for mod in AUTOSAR_MODULES:
        for call in rte_calls:
            if mod.lower() in call.lower():
                rels.append(Relation("module", mod, "api", call, "implements",
                                     confidence=0.65, is_inferred=True, provenance=prov))
    return ents, rels


def extract_test_entities(path: str, text: str) -> tuple[list[Entity], list[Relation]]:
    ents: list[Entity] = []
    rels: list[Relation] = []
    base = os.path.basename(path)
    prov = {"file": path, "source": base}
    cases = _dedupe(TESTCASE_RE.findall(text))
    for m in FUNC_DEF_RE.finditer(text):
        name = m.group("name")
        if name.lower().startswith(("test", "tc_", "ut_", "it_")):
            cases.append(name)
    for case in _dedupe(cases):
        ents.append(Entity("test_case", case, {"file": path, "source": base}))
        rels.append(Relation("document", base, "test_case", case, "defined_in",
                             confidence=0.9, is_inferred=False, provenance=prov))
    # annotations: @covers SWS_CanIf_00012 / @requires ...
    for m in ANNOTATION_RE.finditer(text):
        target = m.group(1).strip()
        if not target:
            continue
        kind = "requirement" if REQ_ID_RE.match(target) or REQ_ID_SIMPLE_RE.match(target) else "api"
        ents.append(Entity(kind, target, {}))
        for case in _dedupe(cases):
            rels.append(Relation("test_case", case, kind, target,
                                 "covered_by" if kind == "requirement" else "verifies",
                                 confidence=0.9, is_inferred=False, provenance=prov))
    # requirement mentions inside a test file
    for req in _dedupe(REQ_ID_RE.findall(text) + REQ_ID_SIMPLE_RE.findall(text)):
        ents.append(Entity("requirement", req, {}))
        for case in _dedupe(cases):
            rels.append(Relation("test_case", case, "requirement", req, "covers",
                                 confidence=0.65, is_inferred=True, provenance=prov))
    return ents, rels


# ---------------------------------------------------------------------- helpers
def _dedupe(items) -> list[str]:
    out: list[str] = []
    for it in items or []:
        s = str(it).strip()
        if s and s not in out:
            out.append(s)
    return out


def _enclosing_function(text: str, needle: str) -> str | None:
    """Best-effort: nearest preceding function definition name."""
    idx = text.find(needle)
    if idx < 0:
        return None
    best: tuple[int, str] | None = None
    for m in FUNC_DEF_RE.finditer(text):
        if m.start() > idx:
            break
        best = (m.start(), m.group("name"))
    return best[1] if best else None


def module_of_symbol(symbol: str) -> str:
    """AUTOSAR module prefix for a symbol: ``CanIf_Init`` -> ``CanIf``."""
    for mod in AUTOSAR_MODULES:
        if symbol == mod or symbol.startswith(mod + "_"):
            return mod
    return ""


def seed_labels(query: str, limit: int = 12) -> list[str]:
    """Candidate graph seeds for a natural-language query (deterministic)."""
    seeds: list[str] = []
    q = query or ""
    identifiers: list[str] = []
    for req in REQ_ID_RE.findall(q) + REQ_ID_SIMPLE_RE.findall(q):
        identifiers.append(req)
        seeds.append(req)
    for tc in TESTCASE_RE.findall(q):
        identifiers.append(tc)
        seeds.append(tc)
    for m in FUNC_DEF_RE.finditer(q):
        identifiers.append(m.group("name"))
        seeds.append(m.group("name"))
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+)\b", q):
        identifiers.append(m.group(1))
        seeds.append(m.group(1))
    for m in re.finditer(r"\b([A-Za-z][A-Za-z0-9]{2,})\b", q):
        w = m.group(1)
        if w.lower() not in _STOP_LABELS and module_of_symbol(w):
            seeds.append(w)
    for mod in AUTOSAR_MODULES:
        if re.search(rf"\b{re.escape(mod)}\b", q):
            seeds.append(mod)
    # a module is often only visible through its symbols (`CanIf_Main` -> `CanIf`)
    for ident in identifiers:
        mod = module_of_symbol(ident)
        if mod:
            seeds.append(mod)
    return _dedupe(seeds)[:limit]
