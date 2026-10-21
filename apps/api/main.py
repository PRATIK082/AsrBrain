"""FastAPI service: legacy /query,/ingest,/evaluate + Part-D chat contract under /api/."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
import os
import sqlite3
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from src.config.settings import settings
from src.indexing.hybrid import HybridIndex, load_chunks
from src.retrieval.pipeline import RetrievalPipeline
from src.workflows.router import answer_query
from src.workflows.stages import run_staged
from src.generation.providers import ProviderSpec, list_ollama_models
from src.chat.store import ChatStore
from src.ingestion.pipeline import run as run_ingest
from src.evaluation.datasets import write_seed

app = FastAPI(title="AsrBrain API")

_pipe: RetrievalPipeline | None = None
_store = ChatStore()
_cancel: dict[str, bool] = {}
PIPELINE_VERSION = os.environ.get("RAG_PIPELINE_VERSION", "v2")


class QueryRequest(BaseModel):
    query: str
    top_k: int = 12
    release: str = ""
    platform: str = ""
    module: str = ""


def get_pipe() -> RetrievalPipeline:
    global _pipe
    if _pipe is None:
        chunks = load_chunks(settings.canonical_db)
        if not chunks:
            raise HTTPException(503, f"Canonical store empty at {settings.canonical_db}. POST /ingest first.")
        try:
            idx = HybridIndex.load("data/indexes/hybrid")
            if len(idx.chunk_ids) != len(chunks):
                raise ValueError("stale index")
        except Exception:
            idx = HybridIndex()
            idx.build(chunks)
            idx.save("data/indexes/hybrid")
        _pipe = RetrievalPipeline(idx, chunks)
    return _pipe


@app.get("/health")
def health():
    return {"status": "ok", "llm": settings.llm_model, "backend": settings.embedding_backend,
            "pipeline": PIPELINE_VERSION}


@app.post("/query")
def query(req: QueryRequest):
    q = req.query
    if req.release:
        q += f" {req.release}"
    if req.platform:
        q += f" {req.platform}"
    if req.module:
        q += f" {req.module}"
    return answer_query(get_pipe(), q)


@app.post("/ingest")
def ingest(pdf_dir: str = "pdf", module: str = ""):
    global _pipe
    result = run_ingest(pdf_dir, "data/canonical", module)
    chunks = load_chunks(settings.canonical_db)
    idx = HybridIndex()
    idx.build(chunks)
    idx.save("data/indexes/hybrid")
    _pipe = None
    return result


@app.post("/evaluate")
def evaluate():
    write_seed("data/benchmarks/autosar_benchmark_v1.jsonl")
    from src.evaluation.run import run_benchmark
    return run_benchmark("data/benchmarks/autosar_benchmark_v1.jsonl",
                         settings.canonical_db, "data/indexes/hybrid",
                         "reports/evaluation/validated.json")["summary"]


# ---------------- Part D: chat contract ----------------

class ConversationCreate(BaseModel):
    title: str = "New conversation"


class ConversationPatch(BaseModel):
    title: str | None = None
    archived: bool | None = None


class ChatRequest(BaseModel):
    conversation_id: str = ""
    message: str
    release_filter: list[str] = []
    platform_filter: list[str] = []
    module_filter: list[str] = []
    mode: str = "auto"              # auto | exact_lookup | comparison | troubleshooting | deep_explanation
    include_graph: bool = True
    include_tables: bool = True
    include_figures: bool = True
    stream: bool = False
    provider: str = "ollama"        # ollama | openai_compat
    model: str = ""
    base_url: str = ""
    api_key: str = ""               # per-request only, never stored
    skip_clarify: bool = False      # escape hatch: answer generally


def _provider_spec(req: ChatRequest) -> ProviderSpec:
    if req.provider == "openai_compat":
        return ProviderSpec(kind="openai_compat", model=req.model or "gpt-4o-mini",
                            base_url=req.base_url or "https://api.openai.com/v1",
                            api_key=req.api_key, timeout_s=settings.ollama_timeout_s)
    from src.generation.answer import pick_model
    return ProviderSpec(kind="ollama", model=req.model or pick_model(),
                        base_url=settings.ollama_base_url, timeout_s=settings.ollama_timeout_s)


def _slots_from_req(req: ChatRequest) -> dict:
    slots: dict = {}
    if req.release_filter:
        slots["releases"] = req.release_filter
    if req.platform_filter:
        slots["platforms"] = req.platform_filter
    if req.module_filter:
        slots["modules"] = req.module_filter
    if req.skip_clarify:
        slots["skip_clarify"] = True
    return slots


@app.post("/api/conversations")
def api_conv_create(body: ConversationCreate):
    return _store.create(body.title)


@app.get("/api/conversations")
def api_conv_list():
    return _store.list()


@app.get("/api/conversations/{cid}")
def api_conv_get(cid: str):
    conv = _store.get(cid)
    if not conv:
        raise HTTPException(404, "conversation not found")
    return conv


@app.patch("/api/conversations/{cid}")
def api_conv_patch(cid: str, body: ConversationPatch):
    if not _store.patch(cid, body.title, body.archived):
        raise HTTPException(404, "conversation not found")
    return {"ok": True}


@app.delete("/api/conversations/{cid}")
def api_conv_delete(cid: str):
    if not _store.delete(cid):
        raise HTTPException(404, "conversation not found")
    return {"ok": True}


@app.get("/api/conversations/{cid}/export")
def api_conv_export(cid: str):
    bundle = _store.export_bundle(cid)
    if not bundle:
        raise HTTPException(404, "conversation not found")
    return bundle


@app.post("/api/conversations/import")
def api_conv_import(bundle: dict):
    try:
        return _store.import_bundle(bundle)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    cid = req.conversation_id or _store.create().get("id")
    if req.conversation_id and not _store.get(cid):
        raise HTTPException(404, "conversation not found")
    _store.merge_slots(cid, releases=req.release_filter, platforms=req.platform_filter,
                       modules=req.module_filter)
    slots = _store.get_slots(cid) | _slots_from_req(req)
    if req.mode != "auto":
        slots["mode"] = req.mode
    prior = [{"role": m["role"], "content": m["content"]}
             for m in (_store.get(cid) or {}).get("messages", [])]
    _store.add_message(cid, "user", req.message)
    spec = _provider_spec(req)
    cancel: dict = {}
    events = list(run_staged(get_pipe(), req.message, spec, cancel, slots, history=prior))
    final = next((e for e in reversed(events) if e.get("event") == "complete"), None)
    clarify = next((e for e in events if e.get("event") == "clarify"), None)
    if clarify is not None:
        _store.add_message(cid, "assistant", clarify["question"], {"clarify": clarify.get("missing", [])})
        return {"conversation_id": cid, "needs_clarification": True, **clarify}
    answer = (final or {}).get("answer", "")
    evidence = [e for e in events if e.get("event") == "evidence"]
    _store.add_message(cid, "assistant", answer,
                       {"trace": (final or {}).get("trace", {}), "llm": (final or {}).get("llm", ""),
                        "plan": (final or {}).get("plan", {}),
                        "graph": (final or {}).get("graph", []),
                        "evidence": evidence,
                        "followups": (final or {}).get("followups", [])})
    return {"conversation_id": cid, "needs_clarification": False, **(final or {})}


@app.post("/api/chat/stream")
def api_chat_stream(req: ChatRequest):
    cid = req.conversation_id or _store.create().get("id")
    _store.merge_slots(cid, releases=req.release_filter, platforms=req.platform_filter,
                       modules=req.module_filter)
    slots = _store.get_slots(cid) | _slots_from_req(req)
    prior = [{"role": m["role"], "content": m["content"]}
             for m in (_store.get(cid) or {}).get("messages", [])]
    _store.add_message(cid, "user", req.message)
    spec = _provider_spec(req)
    _cancel[cid] = False
    cancel = {"stop": False}

    def gen():
        answer_parts: list[str] = []
        last: dict = {}
        evidence: list[dict] = []
        for ev in run_staged(get_pipe(), req.message, spec, cancel, slots, history=prior):
            if _cancel.get(cid):
                ev = {"event": "status", "stage": "cancelled", "message": "stopped"}
                yield f"data: {json.dumps(ev)}\n\n"
                break
            if ev.get("event") == "token":
                answer_parts.append(ev.get("text", ""))
            if ev.get("event") == "evidence":
                evidence.append(ev)
            if ev.get("event") == "complete":
                last = ev
            yield f"data: {json.dumps(ev)}\n\n"
        if last.get("answer"):
            _store.add_message(cid, "assistant", last["answer"],
                               {"trace": last.get("trace", {}), "llm": last.get("llm", ""),
                                "plan": last.get("plan", {}), "graph": last.get("graph", []),
                                "evidence": evidence,
                                "followups": last.get("followups", [])})
        elif answer_parts:
            _store.add_message(cid, "assistant", "".join(answer_parts), {"partial": True})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/chat/stop")
def api_chat_stop(body: dict):
    _cancel[body.get("conversation_id", "")] = True
    return {"ok": True}


@app.post("/api/documents/upload")
async def api_upload(file: UploadFile = File(...)):
    dest_dir = os.path.join(settings.pdf_dir, "uploads")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, file.filename or "upload.pdf")
    with open(dest, "wb") as f:
        f.write(await file.read())
    global _pipe
    result = run_ingest(settings.pdf_dir, "data/canonical")
    chunks = load_chunks(settings.canonical_db)
    idx = HybridIndex()
    idx.build(chunks)
    idx.save("data/indexes/hybrid")
    _pipe = None
    return {"saved": dest, **result}


@app.get("/api/documents")
def api_docs():
    conn = sqlite3.connect(settings.canonical_db)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT document_id, source_pdf, autosar_release, platform, module, document_type, page_count, quality FROM documents").fetchall()]
    conn.close()
    return rows


@app.get("/api/documents/{doc_id}")
def api_doc_get(doc_id: str):
    conn = sqlite3.connect(settings.canonical_db)
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM documents WHERE document_id = ?", (doc_id,)).fetchone()
    conn.close()
    if not r:
        raise HTTPException(404, "document not found")
    return dict(r)


@app.post("/api/documents/{doc_id}/reprocess")
def api_doc_reprocess(doc_id: str):
    global _pipe
    result = run_ingest(settings.pdf_dir, "data/canonical")
    chunks = load_chunks(settings.canonical_db)
    idx = HybridIndex()
    idx.build(chunks)
    idx.save("data/indexes/hybrid")
    _pipe = None
    return result


@app.get("/api/sources/{source_id}")
def api_source(source_id: str):
    conn = sqlite3.connect(settings.canonical_db)
    conn.row_factory = sqlite3.Row
    for table in ("chunks", "tables", "figures"):
        try:
            r = conn.execute(
                f"SELECT * FROM {table} WHERE chunk_id = ? OR evidence_id = ?", (source_id, source_id)).fetchone()
            if r:
                conn.close()
                return {"kind": table, **dict(r)}
        except Exception:
            continue
    conn.close()
    raise HTTPException(404, "source not found")


@app.get("/api/sources/{source_id}/page/{page}")
def api_source_page(source_id: str, page: int):
    conn = sqlite3.connect(settings.canonical_db)
    conn.row_factory = sqlite3.Row
    chunk = conn.execute("SELECT * FROM chunks WHERE chunk_id = ?", (source_id,)).fetchone()
    if not chunk:
        conn.close()
        raise HTTPException(404, "source not found")
    c = dict(chunk)
    sibs = [dict(r) for r in conn.execute(
        "SELECT chunk_id, section_title, page_start FROM chunks WHERE document_id = ? AND page_start = ? ORDER BY chunk_id LIMIT 20",
        (c["document_id"], page)).fetchall()]
    try:
        tabs = [dict(r) for r in conn.execute("SELECT * FROM tables WHERE document_id = ? AND page = ?", (c["document_id"], page)).fetchall()]
        figs = [dict(r) for r in conn.execute("SELECT * FROM figures WHERE document_id = ? AND page = ?", (c["document_id"], page)).fetchall()]
    except Exception:
        tabs, figs = [], []
    conn.close()
    return {"source": c, "page": page, "same_page_chunks": sibs, "tables": tabs, "figures": figs}


class FeedbackBody(BaseModel):
    conversation_id: str
    message_idx: int = 0
    rating: str = "up"
    note: str = ""


@app.post("/api/feedback")
def api_feedback(body: FeedbackBody):
    return {"id": _store.add_feedback(body.conversation_id, body.message_idx, body.rating, body.note)}


@app.get("/api/health")
def api_health():
    return {"status": "ok", "pipeline": PIPELINE_VERSION, "llm": settings.llm_model}


@app.get("/api/models")
def api_models():
    return {"ollama": list_ollama_models(settings.ollama_base_url),
            "cloud_hint": "OpenAI-compatible: set base_url + model + api_key (OpenAI, Gemini, Opencode/Cloud, OpenRouter)"}


@app.get("/api/releases")
def api_releases():
    conn = sqlite3.connect(settings.canonical_db)
    try:
        rels = sorted({r[0] for r in conn.execute("SELECT DISTINCT autosar_release FROM chunks") if r[0]})
        plats = sorted({r[0] for r in conn.execute("SELECT DISTINCT platform FROM chunks") if r[0]})
        mods = sorted({r[0] for r in conn.execute("SELECT DISTINCT module FROM chunks") if r[0]})
    except Exception:
        rels, plats, mods = [], [], []
    conn.close()
    return {"releases": rels, "platforms": plats}


@app.get("/api/modules")
def api_modules():
    conn = sqlite3.connect(settings.canonical_db)
    try:
        mods = sorted({r[0] for r in conn.execute("SELECT DISTINCT module FROM chunks") if r[0]})
        dts = sorted({r[0] for r in conn.execute("SELECT DISTINCT document_type FROM chunks") if r[0]})
    except Exception:
        mods, dts = [], []
    conn.close()
    return {"modules": mods, "document_types": dts}


# ---------------- Phase 2: enterprise orchestration (human-in-the-loop) ----------------
# ARXML parsed deterministically first; RAG only explains. All endpoints server-enforce
# tenant scope; cloud routing is policy-driven; code findings are advisory-only.

_ARXML_STORE: dict = {}  # artifact_id -> {topology, graph} (replace with object store per tenant)


def _ctx_from_headers(tenant: str = "default", user: str = "local-operator",
                      project: str = "", cloud: str = "local_only") -> "SecurityContext":
    from src.security.context import SecurityContext
    return SecurityContext(user_id=user, tenant_id=tenant, project_id=project or None,
                           cloud_policy=cloud if cloud in (
                               "local_only", "cloud_metadata_only",
                               "cloud_redacted_only", "cloud_allowed") else "local_only",
                           audit_request_id="api")


@app.get("/api/policies/effective")
def api_policies_effective(tenant: str = "default", cloud: str = "local_only"):
    from src.security.policy import classify_content
    ctx = _ctx_from_headers(tenant, cloud=cloud)
    return {"tenant_id": ctx.tenant_id, "cloud_policy": ctx.cloud_policy,
            "flags": {"pipeline": settings.pipeline_version if hasattr(settings, "pipeline_version") else "v1",
                      "arxml": settings.arxml_enabled, "diff": settings.diff_enabled,
                      "code_intel": settings.code_intel_enabled,
                      "strict_local_only": settings.strict_local_only},
            "note": classify_content("", "spec.pdf").policy_reason}


@app.post("/api/arxml/upload")
async def api_arxml_upload(file: UploadFile = File(...), tenant: str = "default", project: str = ""):
    if not settings.arxml_enabled:
        raise HTTPException(503, "ARXML intelligence disabled by feature flag")
    from src.ingestion.arxml import parse_arxml, export_graph
    from src.security.policy import classify_content
    data = await file.read()
    tmp = f"/tmp/{file.filename or 'upload.arxml'}"
    with open(tmp, "wb") as f:
        f.write(data)
    risk = classify_content(data.decode("utf-8", "ignore")[:20000], file.filename or "")
    topo = parse_arxml(tmp, tenant_id=tenant, project_scope=project)
    graph = export_graph(topo)
    _ARXML_STORE[topo.artifact.artifact_id] = {"topology": topo, "graph": graph}
    return {"artifact_id": topo.artifact.artifact_id, "classification": risk.classification,
            "route": "local", "components": len(topo.components), "ports": len(topo.ports),
            "interfaces": len(topo.interfaces), "connectors": len(topo.connectors),
            "warnings": topo.artifact.validation_warnings}


@app.get("/api/arxml/artifacts")
def api_arxml_list(tenant: str = "default"):
    return [{"artifact_id": k, "source": v["topology"].artifact.source_path,
             "tenant_id": v["topology"].artifact.tenant_id,
             "components": len(v["topology"].components)}
            for k, v in _ARXML_STORE.items() if v["topology"].artifact.tenant_id == tenant]


@app.get("/api/arxml/topology")
def api_arxml_topology(artifact_id: str, tenant: str = "default"):
    entry = _ARXML_STORE.get(artifact_id)
    if not entry or entry["topology"].artifact.tenant_id != tenant:
        raise HTTPException(404, "artifact not found or access denied")
    return entry["topology"].model_dump()


@app.get("/api/arxml/nodes/{node_id}/neighbors")
def api_arxml_neighbors(node_id: str, artifact_id: str, tenant: str = "default", depth: int = 1):
    from src.ingestion.arxml import neighbors
    entry = _ARXML_STORE.get(artifact_id)
    if not entry or entry["topology"].artifact.tenant_id != tenant:
        raise HTTPException(404, "artifact not found or access denied")
    return neighbors(entry["graph"], node_id, depth=min(depth, 3))


class DiffRequest(BaseModel):
    base: list[dict]
    target: list[dict]
    domain: str = "api"


@app.post("/api/diff")
def api_diff(req: DiffRequest):
    if not settings.diff_enabled:
        raise HTTPException(503, "diff engine disabled by feature flag")
    from src.diff import diff_records
    return [d.model_dump() for d in diff_records(req.base, req.target, req.domain)]


class CodeReviewRequest(BaseModel):
    source: str
    path: str = "input.c"
    port_names: list[str] = []


@app.post("/api/code/analyze")
def api_code_analyze(req: CodeReviewRequest):
    if not settings.code_intel_enabled:
        raise HTTPException(503, "code intelligence disabled by feature flag")
    from src.code_intelligence import preflight_checks, rte_call_sites, map_rte_to_arxml
    findings = preflight_checks(req.source, req.path)
    calls = rte_call_sites(req.source)
    links = map_rte_to_arxml(calls, req.port_names)
    return {"findings": [f.model_dump() for f in findings], "rte_calls": calls,
            "traceability": [lnk.model_dump() for lnk in links],
            "disclaimer": "Advisory only — not a MISRA/ISO 26262 compliance determination."}


class SarifRequest(BaseModel):
    sarif: dict
    tool: str = ""


@app.post("/api/code/sarif")
def api_code_sarif(req: SarifRequest):
    if not settings.code_intel_enabled:
        raise HTTPException(503, "code intelligence disabled by feature flag")
    from src.code_intelligence import ingest_sarif
    findings = ingest_sarif(req.sarif, req.tool)
    return {"findings": [f.model_dump() for f in findings],
            "disclaimer": "Tool-reported findings ingested verbatim — not a compliance determination."}


class DiagramRequest(BaseModel):
    image_path: str
    caption: str = ""
    page: int = 0
    document_id: str = ""


@app.post("/api/diagrams/analyze")
def api_diagram_analyze(req: DiagramRequest):
    from src.ingestion.vlm import analyze_diagram
    ev = analyze_diagram(req.image_path, req.caption, page=req.page, document_id=req.document_id)
    return {**ev.model_dump(),
            "note": "Supplemental only — cite the original figure for normative claims; processed locally."}


class DiagramRecreateRequest(BaseModel):
    pdf_path: str = ""
    page: int = 0
    pages: list[int] | None = None
    dpi: int = 200
    caption: str = ""
    provider: str = ""
    model: str = ""


@app.post("/api/diagrams/recreate")
def api_diagram_recreate(req: DiagramRecreateRequest):
    """Recreate PDF flowchart/diagram pages as validated ```mermaid blocks.

    Body: {pdf_path, page|pages, dpi, caption, provider, model}.
    Never breaks on missing pymupdf/vision — returns text fallback per page.
    """
    from src.ingestion.diagram_mermaid import recreate_diagrams_for_pdf
    if not req.pdf_path:
        raise HTTPException(400, "pdf_path is required")
    target = req.pages if req.pages is not None else [req.page]
    try:
        results = recreate_diagrams_for_pdf(req.pdf_path, pages=target, dpi=req.dpi,
                                            caption=req.caption, provider=req.provider,
                                            model=req.model)
    except FileNotFoundError:
        raise HTTPException(404, "pdf not found")
    except Exception as e:
        raise HTTPException(500, f"diagram recreation failed: {e}")
    return {"results": results,
            "note": "Supplemental only — cite the original figure for normative claims; processed locally."}


class SourceRegisterRequest(BaseModel):
    name: str
    location: str  # local PC folder/file or server Git link
    kind: str = "mixed"
    scope_type: str = "project"
    scope_name: str = "default"
    tenant_id: str = "default"
    project_id: str = "default"
    workspace_id: str = "default"


@app.get("/api/sources")
def api_sources_list():
    from src.ingestion import project_sources as _ps
    return {"sources": _ps.load_registry(),
            "scope_types": list(_ps.SCOPE_TYPES)}


@app.post("/api/sources/register")
def api_sources_register(req: SourceRegisterRequest):
    from src.ingestion import project_sources as _ps
    try:
        rec = _ps.register_source(req.name, req.location, kind=req.kind,
                                  scope_type=req.scope_type, scope_name=req.scope_name,
                                  tenant_id=req.tenant_id, project_id=req.project_id,
                                  workspace_id=req.workspace_id)
        res = _ps.ingest_source(rec["source_id"], settings.canonical_db)
        return {**rec, **res, "status": "indexed"}
    except (ValueError, FileNotFoundError, KeyError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"ingest failed: {e}")


@app.post("/api/sources/{source_id}/reindex")
def api_sources_reindex(source_id: str):
    from src.ingestion import project_sources as _ps
    try:
        return {**_ps.ingest_source(source_id, settings.canonical_db), "status": "indexed"}
    except KeyError:
        raise HTTPException(404, "unknown source")
    except Exception as e:
        raise HTTPException(500, f"reindex failed: {e}")


@app.get("/api/config/tokens")
def api_tokens_get():
    from src.config.settings import TOKEN_CAPS
    return {"caps": dict(TOKEN_CAPS), "file": "config/generation.yaml"}


# ---------------- Institutional assistant ----------------

class DiagnoseRequest(BaseModel):
    symptom: str
    code: str = ""
    module: str = ""
    release: str = ""
    provider: str = ""              # empty -> deterministic triage
    model: str = ""
    base_url: str = ""
    api_key: str = ""


@app.get("/api/assistant/capabilities")
def api_assistant_capabilities():
    """What the assistant knows and can do (derived from the canonical store)."""
    from src.assistant import capabilities
    return capabilities()


@app.get("/api/assistant/overview")
def api_assistant_overview():
    """Project knowledge overview: modules, releases, documents, concept flow."""
    from src.assistant import project_overview
    return project_overview()


@app.get("/api/assistant/prompts")
def api_assistant_prompts():
    """Curated starter-prompt library for the empty state."""
    from src.assistant import starter_prompts
    return {"groups": starter_prompts()}


@app.get("/api/assistant/triage/categories")
def api_assistant_triage_categories():
    """Symptom taxonomy used by the troubleshooting surface."""
    from src.assistant import triage_categories
    return {"categories": triage_categories()}


@app.post("/api/assistant/diagnose")
def api_assistant_diagnose(req: DiagnoseRequest):
    """Evidence-grounded triage of a reported symptom."""
    from src.assistant import diagnose
    spec = None
    if req.provider:
        if req.provider == "openai_compat":
            spec = ProviderSpec(kind="openai_compat", model=req.model or "gpt-4o-mini",
                                 base_url=req.base_url or "https://api.openai.com/v1",
                                 api_key=req.api_key, timeout_s=settings.ollama_timeout_s)
        elif req.provider == "ollama":
            from src.generation.answer import pick_model
            spec = ProviderSpec(kind="ollama", model=req.model or pick_model(),
                                 base_url=req.base_url or settings.ollama_base_url,
                                 timeout_s=settings.ollama_timeout_s)
    try:
        return diagnose(req.symptom, code=req.code, module=req.module,
                        release=req.release, spec=spec, pipe=get_pipe())
    except Exception as e:
        raise HTTPException(500, f"diagnosis failed: {e}")


# ---------------- v2: engineering workspace (additive) ----------------
# Everything under /api/v2 is new and additive. The 47 v1 routes keep their
# path, request shape and response keys. See docs/architecture/adr/0008.

_WORKSPACE_MODULES: list[dict] = [
    {
        "id": "chat",
        "title": "Evidence Chat",
        "href": "#/chat",
        "status": "available",
        "description": "Ask the indexed AUTOSAR corpus. Every claim is cited to a document, page and section.",
        "capability": "Cited answers, the retrieval steps that produced them and the sources behind them.",
        "missing": "",
        "phase": "Phase 1 - shipping now",
    },
    {
        "id": "knowledge",
        "title": "Knowledge Ingestion",
        "href": "#/knowledge",
        "status": "partial",
        "description": "Import specifications, ARXML and project sources and keep every version traceable.",
        "capability": "PDF ingestion into the canonical store with page-level provenance, plus an ARXML upload endpoint.",
        "missing": "Artifact registry, version history, access policy and background ingestion jobs (Phase 2-3).",
        "phase": "Phase 2-3",
    },
    {
        "id": "arxml",
        "title": "ARXML Explorer",
        "href": "#/arxml",
        "status": "available",
        "description": "Deterministic component, port, interface and ECUC topology parsed from the uploaded ARXML.",
        "capability": "Topology, neighbour traversal and unresolved-reference reporting straight from the parser.",
        "missing": "Line-level locations, UUIDs, schema validation results and a typed graph projection (Phase 4).",
        "phase": "Phase 4",
    },
    {
        "id": "graph",
        "title": "Knowledge Graph Explorer",
        "href": "#/graph",
        "status": "planned",
        "description": "Typed nodes and edges across requirements, ARXML elements, code symbols and test cases.",
        "capability": "Nothing yet - the current graph is derived per request and is not persisted.",
        "missing": "Typed graph store with provenance, traversal API and the graph explorer UI (Phase 2 and 4).",
        "phase": "Phase 2, 4, 5",
    },
    {
        "id": "requirements",
        "title": "Requirement Traceability",
        "href": "#/requirements",
        "status": "partial",
        "description": "Normalise requirements, link them to code and tests, and show coverage and orphans.",
        "capability": "Requirement identifiers are extracted from the specification corpus and are searchable.",
        "missing": "Requirement ingestion, revision status, reviewed trace links and the traceability matrix (Phase 6).",
        "phase": "Phase 6",
    },
    {
        "id": "tests",
        "title": "Test & Log Intelligence",
        "href": "#/tests",
        "status": "planned",
        "description": "Ingest test results and logs, cluster failures and link them to changes.",
        "capability": "Nothing yet.",
        "missing": "Test adapters, failure clustering and the test timeline (Phase 6).",
        "phase": "Phase 6",
    },
    {
        "id": "diffs",
        "title": "Diffs & Impact",
        "href": "#/diffs",
        "status": "available",
        "description": "Structural diff between two entity sets with compatibility risk per change.",
        "capability": "Entity-keyed diff with added/removed/modified classification and canned migration guidance.",
        "missing": "ChangeSet model, dependency-aware impact analysis and ARXML version diffing (Phase 7).",
        "phase": "Phase 7",
    },
    {
        "id": "diagrams",
        "title": "Mermaid & Report Studio",
        "href": "#/diagrams",
        "status": "partial",
        "description": "Recreate diagrams from specification figures and export evidence packages.",
        "capability": "Server-side Mermaid recreation from page images and PDF figure analysis through the local vision model.",
        "missing": "No studio UI in the React app yet, no diagram evidence binding and no PDF evidence package (Phase 7).",
        "phase": "Phase 7",
    },
    {
        "id": "code",
        "title": "Code Review",
        "href": "#/code",
        "status": "available",
        "description": "Advisory static checks on a C snippet. A human approves every change.",
        "capability": "Deterministic findings and SARIF export.",
        "missing": "Code symbol graph, commit anchoring and change approval workflow (Phase 3, 6).",
        "phase": "Phase 3, 6",
    },
    {
        "id": "evaluation",
        "title": "Evaluation & Audit",
        "href": "#/evaluation",
        "status": "partial",
        "description": "Measure answer quality, citation validity and abstention quality over a golden set.",
        "capability": "A benchmark runner over the seeded AUTOSAR question set.",
        "missing": "Answerability ground truth, per-route latency and cost metrics and a full audit trail (Phase 5, 8).",
        "phase": "Phase 5, 8",
    },
]


@app.get("/api/v2/modules")
def api_v2_modules():
    """The workspace module catalogue.

    `status` is deliberately honest: `available`, `partial` or `planned`. A
    module is never advertised as more than it is.
    """
    return {
        "workspace": {
            "id": "default",
            "title": "AsrBrain Engineering Workspace",
            "project": "local",
            "scope": "default workspace",
        },
        "modules": _WORKSPACE_MODULES,
    }


@app.get("/api/v2/answerability/{conversation_id}/{message_index}")
def api_v2_answerability(conversation_id: str, message_index: int):
    """The evidence-first answerability contract for one stored answer.

    Not implemented yet (Phase 5). Returns 501 with the reason so the UI can
    show an honest "not computed" state instead of inventing a status.
    """
    raise HTTPException(
        501,
        "answerability gate is not computed yet (Phase 5); the UI must not infer a "
        "status from the numeric confidence",
        headers={"X-AsrBrain-Reason": "answerability-gate-not-implemented"},
    )

