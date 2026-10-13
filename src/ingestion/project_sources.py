"""Project source onboarding: link local PC folders, server Git URLs, or uploaded
ARXML / config / code files with explicit scoping.

Scope types (user-visible): project | oem | open_program | customer |
customer_project | generic.  Every source records tenant/project/workspace +
scope so retrieval can show *why* a chunk was used and tenants stay isolated.

Design notes
- ARXML is parsed deterministically first (see src/ingestion/arxml/parser);
  raw text is chunked only as retrievable evidence, never as prose truth.
- Code/config chunks use module="" so the metadata hard-filter never drops
  them when the query plan names a spec module (CanIf, PduR, ...).  Scope is
  carried in section_title ("[customer:XYZ] path/to/file.c") and document_type
  ("code" | "arxml" | "config" | "diagram"), which the retrieval filter
  explicitly lets through regardless of release/platform.
- Registry lives at data/canonical/sources.json (additive, human-readable).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from dataclasses import asdict, dataclass, field

SCOPE_TYPES = ("project", "oem", "open_program", "customer", "customer_project", "generic")
SOURCE_KINDS = ("arxml", "config", "code", "pdf", "mixed")

CODE_EXTS = {".c", ".h", ".cpp", ".hpp", ".cc", ".py", ".cs", ".java", ".rs",
             ".dbc", ".yaml", ".yml", ".json", ".xml", ".arxml", ".txt", ".md",
             ".cfg", ".ini", ".toml", ".cmake", ".mk", ".ld", ".a2l", ".xdm"}
ARXML_EXTS = {".arxml", ".xml"}
CONFIG_EXTS = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".dbc", ".xdm", ".xml"}
PDF_EXTS = {".pdf"}

REGISTRY_PATH = os.path.join("data", "canonical", "sources.json")
CHECKOUT_ROOT = os.path.join("data", "sources")
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150


@dataclass
class ProjectSource:
    source_id: str
    name: str
    kind: str = "mixed"
    location: str = ""          # local path or git URL (as given)
    local_path: str = ""        # resolved checkout/copy on this machine
    scope_type: str = "project"  # one of SCOPE_TYPES
    scope_name: str = "default"
    tenant_id: str = "default"
    project_id: str = "default"
    workspace_id: str = "default"
    created_at: float = field(default_factory=time.time)
    files_indexed: int = 0
    chunks_indexed: int = 0
    note: str = ""


def _registry_path(path: str = REGISTRY_PATH) -> str:
    return path


def load_registry(path: str = REGISTRY_PATH) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_registry(sources: list[dict], path: str = REGISTRY_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sources, f, indent=2)


def _is_git_url(loc: str) -> bool:
    l = loc.strip().lower()
    return (l.startswith("http") and (l.endswith(".git") or "git" in l or "@" in loc)) \
        or l.startswith("git@") or l.startswith("ssh://")


def _resolve_location(source_id: str, location: str) -> str:
    """Clone git URLs into data/sources/<id>; accept local files/dirs as-is."""
    location = location.strip()
    if _is_git_url(location):
        dest = os.path.join(CHECKOUT_ROOT, source_id)
        if os.path.isdir(os.path.join(dest, ".git")):
            subprocess.run(["git", "-C", dest, "pull", "--ff-only"],
                           capture_output=True, timeout=300)
        else:
            os.makedirs(CHECKOUT_ROOT, exist_ok=True)
            if os.path.isdir(dest):
                shutil.rmtree(dest)
            subprocess.run(["git", "clone", "--depth", "1", location, dest],
                           check=True, capture_output=True, timeout=600)
        return dest
    p = os.path.abspath(os.path.expanduser(location))
    if not os.path.exists(p):
        raise FileNotFoundError(f"Local path not found: {location}")
    return p


def register_source(name: str, location: str, kind: str = "mixed",
                    scope_type: str = "project", scope_name: str = "default",
                    tenant_id: str = "default", project_id: str = "default",
                    workspace_id: str = "default",
                    registry: str = REGISTRY_PATH) -> dict:
    if scope_type not in SCOPE_TYPES:
        raise ValueError(f"scope_type must be one of {SCOPE_TYPES}")
    if kind not in SOURCE_KINDS:
        raise ValueError(f"kind must be one of {SOURCE_KINDS}")
    sid = "src-" + hashlib.sha256(f"{name}|{location}|{time.time()}".encode()).hexdigest()[:10]
    local_path = _resolve_location(sid, location)
    src = ProjectSource(source_id=sid, name=name, kind=kind, location=location,
                        local_path=local_path, scope_type=scope_type,
                        scope_name=scope_name, tenant_id=tenant_id,
                        project_id=project_id, workspace_id=workspace_id)
    rows = load_registry(registry)
    rows.append(asdict(src))
    save_registry(rows, registry)
    return asdict(src)


def _kind_for_file(path: str, default_kind: str) -> str | None:
    ext = os.path.splitext(path)[1].lower()
    if default_kind == "arxml":
        return "arxml" if ext in ARXML_EXTS else None
    if default_kind == "config":
        return "config" if ext in CONFIG_EXTS else None
    if default_kind == "code":
        return "code" if ext in CODE_EXTS else None
    if default_kind == "pdf":
        return "pdf" if ext in PDF_EXTS else None
    if ext in PDF_EXTS:
        return None  # PDFs stay in the PDF pipeline
    return "code" if ext in CODE_EXTS else ("config" if ext in CONFIG_EXTS
                                            else ("arxml" if ext in ARXML_EXTS else None))


def _iter_files(local_path: str, kind: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if os.path.isfile(local_path):
        k = _kind_for_file(local_path, kind)
        if k:
            out.append((local_path, k))
        return out
    for root, _dirs, files in os.walk(local_path):
        if ".git" in root.split(os.sep):
            continue
        for fn in sorted(files):
            fp = os.path.join(root, fn)
            k = _kind_for_file(fp, kind)
            if k:
                out.append((fp, k))
    return out[:5000]


def _read_text(fp: str, limit: int = 200_000) -> str:
    try:
        with open(fp, encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


def _arxml_summary(text: str) -> str:
    """Deterministic topology sketch so the chunk is findable by SWC/port name."""
    try:
        from .arxml.parser import parse_arxml
        topo = parse_arxml(text, artifact_id="summary").get("topology", {})
        parts = []
        for swc in topo.get("software_components", [])[:40]:
            ports = ", ".join(p.get("name", "") for p in swc.get("ports", [])[:12])
            parts.append(f"SWC {swc.get('name')} [{swc.get('kind')}]: {ports}")
        for c in topo.get("connectors", [])[:40]:
            parts.append(f"CONN {c.get('name')}: {c.get('source')} -> {c.get('target')}")
        return "\n".join(parts)[:4000]
    except Exception:
        return ""


def chunk_file(fp: str, kind: str, src: dict, rel: str) -> list[dict]:
    text = _read_text(fp)
    if not text.strip():
        return []
    scope_tag = f"[{src['scope_type']}:{src['scope_name']}]"
    tenant_tag = f"[tenant:{src['tenant_id']} project:{src['project_id']}]"
    blocks: list[str] = []
    if kind == "arxml":
        summary = _arxml_summary(text)
        if summary:
            blocks.append(f"ARXML topology summary for {rel}:\n{summary}")
    step = CHUNK_CHARS - CHUNK_OVERLAP
    for i in range(0, len(text), step):
        blocks.append(text[i:i + CHUNK_CHARS])
        if len(blocks) > 60:
            break
    chunks = []
    sha = hashlib.sha256(fp.encode()).hexdigest()[:12]
    for n, b in enumerate(blocks):
        cid = f"ps-{src['source_id'][:8]}-{sha}-{n}"
        label = f"{scope_tag} {rel} part{n}" if n else f"{scope_tag} {rel}"
        chunks.append({
            "chunk_id": cid,
            "document_id": src["source_id"],
            "source_pdf": f"{tenant_tag} {rel}",
            "sha256": sha,
            "page_start": n, "page_end": n, "pdf_page_index": n,
            "autosar_release": "", "platform": "", "module": "",
            "document_type": kind,
            "section_number": "", "section_title": label,
            "requirement_ids": [], "api_names": [],
            "ecu_parameters": [], "parent_chunk_id": None,
            "chunk_kind": kind,
            "text": b, "normalized_text": b,
        })
    return chunks


def ingest_source(source_id: str, canonical_db: str = "data/canonical/canonical.db",
                  registry: str = REGISTRY_PATH) -> dict:
    rows = load_registry(registry)
    src = next((r for r in rows if r["source_id"] == source_id), None)
    if src is None:
        raise KeyError(f"Unknown source: {source_id}")
    if not os.path.exists(src["local_path"]):
        src["local_path"] = _resolve_location(source_id, src["location"])
    files = _iter_files(src["local_path"], src.get("kind", "mixed"))
    all_chunks: list[dict] = []
    for fp, kind in files:
        rel = os.path.relpath(fp, src["local_path"]) if os.path.isdir(src["local_path"]) \
            else os.path.basename(fp)
        all_chunks.extend(chunk_file(fp, kind, src, rel))
    conn = sqlite3.connect(canonical_db)
    conn.execute("""CREATE TABLE IF NOT EXISTS documents(document_id TEXT PRIMARY KEY,
        source_pdf TEXT, sha256 TEXT, title TEXT, autosar_release TEXT, platform TEXT,
        module TEXT, document_type TEXT, page_count INT, quality REAL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS chunks(chunk_id TEXT PRIMARY KEY,
        document_id TEXT, source_pdf TEXT, sha256 TEXT, page_start INT, page_end INT,
        pdf_page_index INT, autosar_release TEXT, platform TEXT, module TEXT,
        document_type TEXT, section_number TEXT, section_title TEXT,
        requirement_ids TEXT, api_names TEXT, ecu_parameters TEXT,
        parent_chunk_id TEXT, chunk_kind TEXT, text TEXT, normalized_text TEXT)""")
    conn.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (src["source_id"], src["local_path"], src["source_id"],
                  f"{src['name']} [{src['scope_type']}:{src['scope_name']}]",
                  "", "", "", src.get("kind", "mixed"), len(files), 1.0))
    for c in all_chunks:
        conn.execute("INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (c["chunk_id"], c["document_id"], c["source_pdf"], c["sha256"],
                      c["page_start"], c["page_end"], c["pdf_page_index"],
                      c["autosar_release"], c["platform"], c["module"],
                      c["document_type"], c["section_number"], c["section_title"],
                      json.dumps(c["requirement_ids"]), json.dumps(c["api_names"]),
                      json.dumps(c["ecu_parameters"]), c["parent_chunk_id"],
                      c["chunk_kind"], c["text"], c["normalized_text"]))
    conn.commit()
    conn.close()
    src["files_indexed"] = len(files)
    src["chunks_indexed"] = len(all_chunks)
    save_registry(rows, registry)
    return {"source_id": source_id, "files": len(files), "chunks": len(all_chunks)}
