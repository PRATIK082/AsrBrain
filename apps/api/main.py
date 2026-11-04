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
from datetime import datetime, timezone
import time
import uuid
import logging
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Response
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from src.config.settings import settings
from src.config.pipeline_config import (create_config, get_active, list_configs,
                                       activate_config, rollback, validate_config,
                                       DEFAULT_CONFIG)
from src.indexing.hybrid import HybridIndex, db_fingerprint, load_chunks
from src.retrieval.pipeline import RetrievalPipeline
from src.workflows.router import answer_query
from src.workflows.stages import run_staged
from src.generation.providers import ProviderSpec, list_ollama_models
from src.chat.store import ChatStore, classify_outcome
from src.schema.evidence import normalize_evidence
from src.system.context import build_self_context
from src.ingestion.pipeline import run as run_ingest
from src.ingestion.migrations import migrate as migrate_canonical
from src.security.auth import (hash_password, verify_password, create_session,
                              resolve_session, revoke_session, authenticate,
                              create_user)
from src.security.workspaces import (create_workspace, add_member, get_membership,
                                    list_workspaces_for_user, create_collection,
                                    list_collections, add_document_to_collection,
                                    authorized_document_ids, log_audit)
from src.security.permissions import has_permission
from src.generation.provider_registry import (create_provider, list_providers, get_provider,
                                            update_provider, delete_provider, test_connection,
                                            to_spec)
from src.evaluation.datasets import write_seed

app = FastAPI(title="AsrBrain API")


@app.middleware("http")
async def _observability_middleware(request: Request, call_next):
    rid = request.headers.get("x-request-id") or str(uuid.uuid4())
    start = time.time()
    # Simple per-client rate limit
    client = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = _RATE_BUCKETS.setdefault(client, [])
    bucket[:] = [t for t in bucket if now - t < 60]
    if len(bucket) >= _RATE_LIMIT:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "rate limit exceeded"}, status_code=429,
                            headers={"X-Request-ID": rid})
    bucket.append(now)
    response = await call_next(request)
    dur_ms = round((time.time() - start) * 1000, 1)
    response.headers["X-Request-ID"] = rid
    _METRICS["requests"] += 1
    _METRICS["latency_ms_sum"] += dur_ms
    if response.status_code >= 400:
        _METRICS["errors"] += 1
    _logger.info("%s %s %s %sms rid=%s", request.method, request.url.path,
                 response.status_code, dur_ms, rid)
    return response

_pipe: RetrievalPipeline | None = None
_store = ChatStore()
_cancel: dict[str, bool] = {}
_logger = logging.getLogger("asrbrain.api")
_RATE_BUCKETS: dict[str, list[float]] = {}
_RATE_LIMIT = int(os.environ.get("ASRBRAIN_RATE_LIMIT_PER_MIN", "120"))
_METRICS: dict[str, float] = {"requests": 0, "errors": 0, "latency_ms_sum": 0.0}


def _canonical_conn():
    conn = sqlite3.connect(settings.canonical_db)
    conn.execute("PRAGMA foreign_keys = ON")
    migrate_canonical(conn)
    return conn


def _current_user(request) -> str | None:
    token = request.cookies.get("asrbrain_session")
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    if not token:
        return None
    conn = _canonical_conn()
    try:
        return resolve_session(conn, token)
    finally:
        conn.close()
# Single source of truth for the pipeline flag: settings reads RAG_PIPELINE_VERSION
# first, ASRBRAIN_PIPELINE_VERSION as fallback.
PIPELINE_VERSION = settings.pipeline_version


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
        # Phase 2: staleness is proven by content fingerprint, not row count — a
        # re-ingest that replaces content at the same row count must rebuild.
        fp_now = db_fingerprint(settings.canonical_db)
        try:
            idx = HybridIndex.load("data/indexes/hybrid")
            if getattr(idx, "meta_fingerprint", {}) != fp_now:
                raise ValueError("stale index")
        except Exception:
            idx = HybridIndex()
            idx.build(chunks)
            idx.save("data/indexes/hybrid", fingerprint=fp_now)
        _pipe = RetrievalPipeline(idx, chunks)
    return _pipe


@app.get("/health")
def health():
    return {"status": "ok", "llm": settings.llm_model, "backend": settings.embedding_backend,
            "pipeline": PIPELINE_VERSION}


@app.get("/api/context")
def self_context():
    """Machine-readable description of this instance (profile, capabilities, data, health)."""
    return build_self_context()


@app.get("/api/features")
def feature_catalog():
    """List discoverable features and their availability on this instance."""
    return {"features": build_self_context()["features"]}


@app.get("/api/admin/metrics")
def admin_metrics(request: Request):
    user = _require_user(request)
    if not user:
        raise HTTPException(401, "authentication required")
    reqs = _METRICS["requests"] or 1
    return {
        "requests": int(_METRICS["requests"]),
        "errors": int(_METRICS["errors"]),
        "avg_latency_ms": round(_METRICS["latency_ms_sum"] / reqs, 1),
        "context": build_self_context(),
    }


@app.get("/api/admin/backup")
def admin_backup(request: Request):
    """Create a zip backup of canonical and chat databases (authenticated)."""
    user = _require_user(request)
    if not user:
        raise HTTPException(401, "authentication required")
    import zipfile
    from pathlib import Path
    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = backup_dir / f"asrbrain-backup-{stamp}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in (settings.canonical_db, "data/canonical/chat.db"):
            path = Path(p)
            if path.exists():
                zf.write(path, arcname=path.name)
    log_audit(_canonical_conn(), None, user, "backup", "system", str(out))
    return {"backup_path": str(out), "created_by": user}


@app.post("/api/admin/restore")
async def admin_restore(request: Request, file: UploadFile = File(...)):
    user = _require_user(request)
    if not user:
        raise HTTPException(401, "authentication required")
    import zipfile
    import tempfile
    from pathlib import Path
    import shutil
    content = await file.read()
    tmp = Path(tempfile.mkdtemp())
    zip_path = tmp / "restore.zip"
    zip_path.write_bytes(content)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp / "extracted")
    except Exception as exc:
        raise HTTPException(400, f"invalid zip: {exc}")
    extracted = tmp / "extracted"
    # Safety: only known db files
    for name in ("canonical.db", "chat.db"):
        src = extracted / name
        if src.exists():
            dst = Path("data/canonical") / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                shutil.copy2(dst, dst.with_suffix(dst.suffix + ".pre-restore"))
            shutil.copy2(src, dst)
    log_audit(_canonical_conn(), None, user, "restore", "system", file.filename)
    return {"restored": True, "by": user}


@app.get("/api/admin/embedding-benchmark")
def embedding_benchmark(request: Request):
    user = _require_user(request)
    if not user:
        raise HTTPException(401, "authentication required")
    conn = _canonical_conn()
    try:
        chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    finally:
        conn.close()
    return {"backend": settings.embedding_backend, "chunks": chunks,
            "note": "Switch ASRBRAIN_EMBEDDING_BACKEND and re-index to compare; golden-set eval provides metrics."}


@app.post("/api/admin/purge")
def admin_purge(body: dict, request: Request):
    user = _require_user(request)
    if not user:
        raise HTTPException(401, "authentication required")
    if body.get("confirm") != "DELETE ALL DATA":
        raise HTTPException(400, "confirm must be 'DELETE ALL DATA'")
    conn = _canonical_conn()
    try:
        for t in ("chunks", "documents", "tables", "figures"):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
        log_audit(conn, None, user, "purge", "system", "all", {"confirmed": True})
    finally:
        conn.close()
    return {"purged": True, "by": user}


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
    idx.save("data/indexes/hybrid", fingerprint=db_fingerprint(settings.canonical_db))
    _pipe = None
    return result


@app.post("/evaluate")
def evaluate():
    write_seed("data/benchmarks/autosar_benchmark_v1.jsonl")
    from src.evaluation.run import run_benchmark
    return run_benchmark("data/benchmarks/autosar_benchmark_v1.jsonl",
                         settings.canonical_db, "data/indexes/hybrid",
                         "reports/evaluation/validated.json")["summary"]


# ---------------- Slice 1: auth, workspaces, collections ----------------

class BootstrapRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""
    workspace_name: str = "Default workspace"


class LoginRequest(BaseModel):
    email: str
    password: str


class WorkspaceCreate(BaseModel):
    name: str
    slug: str = ""


class MemberAdd(BaseModel):
    user_id: str
    role: str = "member"


class CollectionCreate(BaseModel):
    workspace_id: str
    name: str
    description: str = ""
    visibility: str = "private"


class CollectionDoc(BaseModel):
    document_id: str


def _require_user(request: Request) -> str:
    uid = _current_user(request)
    if not uid:
        raise HTTPException(401, "authentication required")
    return uid


def _allowed_docs_for(request: Request) -> set | None:
    uid = _current_user(request)
    if not uid:
        return None
    conn = _canonical_conn()
    try:
        workspaces = list_workspaces_for_user(conn, uid)
        if not workspaces:
            return set()
        ws = workspaces[0]["workspace_id"]
        role = workspaces[0]["role"]
        return authorized_document_ids(conn, uid, ws, role)
    finally:
        conn.close()


def _require_workspace(conn, user_id: str, workspace_id: str, permission: str) -> str:
    role = get_membership(conn, user_id, workspace_id)
    if not role:
        raise HTTPException(404, "workspace not found")
    if not has_permission(role, permission):
        raise HTTPException(403, "permission denied")
    return role


@app.post("/api/auth/bootstrap")
def auth_bootstrap(body: BootstrapRequest, response: Response):
    conn = _canonical_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count > 0:
            raise HTTPException(409, "bootstrap already completed")
        uid = create_user(conn, body.email, body.password, body.display_name, "active")
        ws = create_workspace(conn, body.workspace_name, body.workspace_name.lower().replace(" ", "-"), uid)
        add_member(conn, ws, uid, "owner", uid)
        log_audit(conn, ws, uid, "bootstrap", "user", uid)
        token = create_session(conn, uid)
        response.set_cookie("asrbrain_session", token, httponly=True, samesite="lax", secure=False)
        return {"user_id": uid, "workspace_id": ws, "token": token}
    finally:
        conn.close()


@app.post("/api/auth/login")
def auth_login(body: LoginRequest, response: Response):
    conn = _canonical_conn()
    try:
        uid = authenticate(conn, body.email, body.password)
        if not uid:
            raise HTTPException(401, "invalid credentials")
        token = create_session(conn, uid)
        response.set_cookie("asrbrain_session", token, httponly=True, samesite="lax", secure=False)
        return {"user_id": uid, "token": token}
    finally:
        conn.close()


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    token = request.cookies.get("asrbrain_session")
    auth = request.headers.get("authorization", "")
    if not token and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    if token:
        conn = _canonical_conn()
        try:
            revoke_session(conn, token)
        finally:
            conn.close()
    response.delete_cookie("asrbrain_session")
    return {"status": "ok"}


@app.get("/api/auth/me")
def auth_me(request: Request):
    uid = _current_user(request)
    if not uid:
        raise HTTPException(401, "not authenticated")
    conn = _canonical_conn()
    try:
        row = conn.execute("SELECT user_id,email,display_name,status FROM users WHERE user_id = ?",
                           (uid,)).fetchone()
        if not row:
            raise HTTPException(401, "not authenticated")
        workspaces = list_workspaces_for_user(conn, uid)
        return {"user_id": row[0], "email": row[1], "display_name": row[2],
                "status": row[3], "workspaces": workspaces}
    finally:
        conn.close()


@app.get("/api/workspaces")
def list_workspaces(request: Request):
    uid = _require_user(request)
    conn = _canonical_conn()
    try:
        return {"workspaces": list_workspaces_for_user(conn, uid)}
    finally:
        conn.close()


@app.post("/api/workspaces")
def create_workspace_endpoint(body: WorkspaceCreate, request: Request):
    uid = _require_user(request)
    conn = _canonical_conn()
    try:
        ws = create_workspace(conn, body.name, body.slug or body.name.lower().replace(" ", "-"), uid)
        add_member(conn, ws, uid, "owner", uid)
        log_audit(conn, ws, uid, "workspace.create", "workspace", ws)
        return {"workspace_id": ws}
    finally:
        conn.close()


@app.get("/api/workspaces/{workspace_id}/members")
def list_members(workspace_id: str, request: Request):
    uid = _require_user(request)
    conn = _canonical_conn()
    try:
        role = _require_workspace(conn, uid, workspace_id, "workspace.read")
        rows = conn.execute(
            "SELECT user_id,role FROM workspace_memberships WHERE workspace_id = ?",
            (workspace_id,)).fetchall()
        return {"members": [{"user_id": r[0], "role": r[1]} for r in rows]}
    finally:
        conn.close()


@app.post("/api/workspaces/{workspace_id}/members")
def add_member_endpoint(workspace_id: str, body: MemberAdd, request: Request):
    uid = _require_user(request)
    conn = _canonical_conn()
    try:
        role = _require_workspace(conn, uid, workspace_id, "members.manage")
        add_member(conn, workspace_id, body.user_id, body.role, uid)
        log_audit(conn, workspace_id, uid, "member.add", "user", body.user_id,
                  {"role": body.role})
        return {"status": "ok"}
    finally:
        conn.close()


@app.get("/api/collections")
def list_collections_endpoint(workspace_id: str, request: Request):
    uid = _require_user(request)
    conn = _canonical_conn()
    try:
        role = _require_workspace(conn, uid, workspace_id, "collection.read")
        return {"collections": list_collections(conn, workspace_id, uid, role)}
    finally:
        conn.close()


@app.post("/api/collections")
def create_collection_endpoint(body: CollectionCreate, request: Request):
    uid = _require_user(request)
    conn = _canonical_conn()
    try:
        role = _require_workspace(conn, uid, body.workspace_id, "collection.create")
        cid = create_collection(conn, body.workspace_id, body.name, body.description,
                                body.visibility, uid)
        log_audit(conn, body.workspace_id, uid, "collection.create", "collection", cid)
        return {"collection_id": cid}
    finally:
        conn.close()


@app.post("/api/collections/{collection_id}/documents")
def add_collection_document(collection_id: str, body: CollectionDoc, request: Request):
    uid = _require_user(request)
    conn = _canonical_conn()
    try:
        row = conn.execute("SELECT workspace_id,owner_id FROM collections WHERE collection_id = ?",
                           (collection_id,)).fetchone()
        if not row:
            raise HTTPException(404, "collection not found")
        workspace_id, owner_id = row
        role = _require_workspace(conn, uid, workspace_id, "collection.update")
        add_document_to_collection(conn, collection_id, body.document_id, uid)
        # tag document workspace if unset
        conn.execute("UPDATE documents SET workspace_id = COALESCE(workspace_id, ?), "
                     "owner_user_id = COALESCE(owner_user_id, ?) WHERE document_id = ?",
                     (workspace_id, uid, body.document_id))
        conn.commit()
        log_audit(conn, workspace_id, uid, "collection.add_document", "document",
                  body.document_id, {"collection_id": collection_id})
        return {"status": "ok"}
    finally:
        conn.close()


class ProviderCreate(BaseModel):
    workspace_id: str = ""
    name: str
    kind: str = "ollama"
    task: str = "generation"
    base_url: str = "http://127.0.0.1:11434"
    model: str = ""
    api_key_env: str = ""
    timeout_s: float = 120.0
    data_transfer_policy: str = "local_only"
    enabled: bool = True


@app.get("/api/providers")
def list_providers_endpoint(workspace_id: str = "", task: str = "", request: Request = None):
    conn = _canonical_conn()
    try:
        return {"providers": list_providers(conn, workspace_id or None, task or None)}
    finally:
        conn.close()


@app.post("/api/providers")
def create_provider_endpoint(body: ProviderCreate, request: Request):
    uid = _require_user(request)
    conn = _canonical_conn()
    try:
        if body.workspace_id:
            _require_workspace(conn, uid, body.workspace_id, "workspace.manage" if False else "workspace.read")
        pid = create_provider(conn, body.workspace_id or None, body.name, body.kind, body.task,
                              body.base_url, body.model, body.api_key_env, body.timeout_s,
                              body.data_transfer_policy, body.enabled)
        log_audit(conn, body.workspace_id or None, uid, "provider.create", "provider", pid)
        return {"provider_id": pid}
    finally:
        conn.close()


@app.get("/api/providers/{provider_id}")
def get_provider_endpoint(provider_id: str, request: Request):
    conn = _canonical_conn()
    try:
        p = get_provider(conn, provider_id)
        if not p:
            raise HTTPException(404, "provider not found")
        return p
    finally:
        conn.close()


@app.patch("/api/providers/{provider_id}")
def update_provider_endpoint(provider_id: str, body: dict, request: Request):
    uid = _require_user(request)
    conn = _canonical_conn()
    try:
        ok = update_provider(conn, provider_id, **(body or {}))
        if not ok:
            raise HTTPException(404, "provider not found")
        log_audit(conn, None, uid, "provider.update", "provider", provider_id)
        return {"status": "ok"}
    finally:
        conn.close()


@app.delete("/api/providers/{provider_id}")
def delete_provider_endpoint(provider_id: str, request: Request):
    uid = _require_user(request)
    conn = _canonical_conn()
    try:
        delete_provider(conn, provider_id)
        log_audit(conn, None, uid, "provider.delete", "provider", provider_id)
        return {"status": "ok"}
    finally:
        conn.close()


@app.post("/api/providers/{provider_id}/test")
def test_provider_endpoint(provider_id: str, request: Request):
    conn = _canonical_conn()
    try:
        p = get_provider(conn, provider_id)
        if not p:
            raise HTTPException(404, "provider not found")
        return test_connection(p)
    finally:
        conn.close()


@app.post("/api/providers/test")
def test_provider_inline(body: ProviderCreate):
    p = body.dict()
    return test_connection(p)


class PipelineConfigCreate(BaseModel):
    config: dict
    note: str = ""
    activate: bool = False


@app.get("/api/config/pipeline")
def get_pipeline_config():
    conn = _canonical_conn()
    try:
        active = get_active(conn)
        if not active:
            return {"config": DEFAULT_CONFIG, "version": 0, "active": False}
        return active
    finally:
        conn.close()


@app.get("/api/config/pipeline/versions")
def list_pipeline_configs(request: Request):
    _require_user(request)
    conn = _canonical_conn()
    try:
        return {"versions": list_configs(conn)}
    finally:
        conn.close()


@app.post("/api/config/pipeline")
def create_pipeline_config(body: PipelineConfigCreate, request: Request):
    uid = _require_user(request)
    conn = _canonical_conn()
    try:
        # admin/owner only
        # allow if any workspace membership role owner/admin
        rows = conn.execute(
            "SELECT role FROM workspace_memberships WHERE user_id = ?", (uid,)).fetchall()
        if not any(r[0] in ("owner", "admin") for r in rows):
            raise HTTPException(403, "admin required")
        cid = create_config(conn, body.config, created_by=uid, note=body.note, activate=body.activate)
        log_audit(conn, None, uid, "config.create", "pipeline_config", cid)
        return {"config_id": cid}
    finally:
        conn.close()


@app.post("/api/config/pipeline/{config_id}/activate")
def activate_pipeline_config(config_id: str, request: Request):
    uid = _require_user(request)
    conn = _canonical_conn()
    try:
        rows = conn.execute(
            "SELECT role FROM workspace_memberships WHERE user_id = ?", (uid,)).fetchall()
        if not any(r[0] in ("owner", "admin") for r in rows):
            raise HTTPException(403, "admin required")
        if not activate_config(conn, config_id):
            raise HTTPException(404, "config not found")
        log_audit(conn, None, uid, "config.activate", "pipeline_config", config_id)
        return {"status": "ok"}
    finally:
        conn.close()


@app.post("/api/config/pipeline/rollback")
def rollback_pipeline_config(request: Request, version: int | None = None):
    uid = _require_user(request)
    conn = _canonical_conn()
    try:
        rows = conn.execute(
            "SELECT role FROM workspace_memberships WHERE user_id = ?", (uid,)).fetchall()
        if not any(r[0] in ("owner", "admin") for r in rows):
            raise HTTPException(403, "admin required")
        cid = rollback(conn, version)
        if not cid:
            raise HTTPException(404, "nothing to roll back to")
        log_audit(conn, None, uid, "config.rollback", "pipeline_config", cid)
        return {"config_id": cid}
    finally:
        conn.close()


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
    # Per-task model routing: prefer a registered provider for chat when available.
    try:
        conn = _canonical_conn()
        try:
            from src.generation.provider_registry import list_providers, to_spec
            providers = list_providers(conn, task="chat")
            if providers and not req.model:
                return to_spec(providers[0])
        finally:
            conn.close()
    except Exception:
        pass
    from src.generation.answer import pick_model, available_models
    model = req.model or pick_model()
    if model not in available_models() and available_models():
        model = pick_model()
    return ProviderSpec(kind="ollama", model=model,
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
def api_conv_create(body: ConversationCreate, request: Request):
    uid = _current_user(request)
    ws = None
    if uid:
        conn = _canonical_conn()
        try:
            workspaces = list_workspaces_for_user(conn, uid)
            ws = workspaces[0]["workspace_id"] if workspaces else None
        finally:
            conn.close()
    return _store.create(body.title, owner_user_id=uid, workspace_id=ws)


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
def api_chat(req: ChatRequest, request: Request):
    cid = req.conversation_id or _store.create().get("id")
    if req.conversation_id and not _store.get(cid):
        raise HTTPException(404, "conversation not found")
    allowed_docs = _allowed_docs_for(request)
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
    import time as _time
    _t0 = _time.time()
    events = list(run_staged(get_pipe(), req.message, spec, cancel, slots, history=prior,
                             allowed_doc_ids=allowed_docs))
    final = next((e for e in reversed(events) if e.get("event") == "complete"), None)
    clarify = next((e for e in events if e.get("event") == "clarify"), None)
    if clarify is not None:
        _store.add_message(cid, "assistant", clarify["question"], {"clarify": clarify.get("missing", [])})
        _store.log_query(cid, req.message, [], classify_outcome("", clarify=True),
                         intent=(clarify.get("plan") or {}).get("intent", "") if isinstance(clarify.get("plan"), dict) else "",
                         pipeline_version=PIPELINE_VERSION, latency_s=_time.time() - _t0)
        return {"conversation_id": cid, "needs_clarification": True, **clarify}
    answer = (final or {}).get("answer", "")
    _store.add_message(cid, "assistant", answer,
                       {"trace": (final or {}).get("trace", {}), "llm": (final or {}).get("llm", ""),
                        "plan": (final or {}).get("plan", {}),
                        "followups": (final or {}).get("followups", [])})
    _ev_ids = [e.get("source_id", "") for e in events
               if e.get("event") == "evidence" and e.get("source_id")]
    _store.log_query(cid, req.message, _ev_ids,
                     classify_outcome(answer, citation_coverage=(final or {}).get("citation_coverage")),
                     intent=((final or {}).get("plan") or {}).get("intent", ""),
                     pipeline_version=PIPELINE_VERSION, latency_s=_time.time() - _t0,
                     llm=(final or {}).get("llm", ""), confidence=(final or {}).get("confidence"))
    return {"conversation_id": cid, "needs_clarification": False, **(final or {})}


@app.post("/api/chat/stream")
def api_chat_stream(req: ChatRequest, request: Request):
    cid = req.conversation_id or _store.create().get("id")
    allowed_docs = _allowed_docs_for(request)
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
        for ev in run_staged(get_pipe(), req.message, spec, cancel, slots, history=prior,
                             allowed_doc_ids=allowed_docs):
            if _cancel.get(cid):
                ev = {"event": "status", "stage": "cancelled", "message": "stopped"}
                yield f"data: {json.dumps(ev)}\n\n"
                break
            if ev.get("event") == "token":
                answer_parts.append(ev.get("text", ""))
            if ev.get("event") == "complete":
                last = ev
            yield f"data: {json.dumps(ev)}\n\n"
        if last.get("answer"):
            _store.add_message(cid, "assistant", last["answer"],
                               {"trace": last.get("trace", {}), "llm": last.get("llm", ""),
                                "plan": last.get("plan", {}), "graph": last.get("graph", []),
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
def api_doc_get(doc_id: str, request: Request):
    conn = _canonical_conn()
    try:
        row = conn.execute("SELECT * FROM documents WHERE document_id = ?", (doc_id,)).fetchone()
        if not row:
            raise HTTPException(404, "document not found")
        cols = [d[0] for d in conn.execute("SELECT * FROM documents LIMIT 1").description]
        data = dict(zip(cols, row))
        uid = _current_user(request)
        if uid:
            allowed = _allowed_docs_for(request)
            if allowed is not None and doc_id not in (allowed or set()):
                raise HTTPException(403, "access denied")
        return data
    finally:
        conn.close()


@app.get("/api/documents/{doc_id}/preview")
def api_doc_preview(doc_id: str, request: Request):
    conn = _canonical_conn()
    try:
        row = conn.execute("SELECT source_pdf FROM documents WHERE document_id = ?", (doc_id,)).fetchone()
        if not row:
            raise HTTPException(404, "document not found")
        source_pdf = row[0] or ""
        uid = _current_user(request)
        if uid:
            allowed = _allowed_docs_for(request)
            if allowed is not None and doc_id not in (allowed or set()):
                raise HTTPException(403, "access denied")
    finally:
        conn.close()
    if not source_pdf:
        raise HTTPException(404, "source file not available")
    # Resolve safely under repo root or configured pdf dir.
    root = Path(ROOT)
    candidate = (root / source_pdf).resolve() if not os.path.isabs(source_pdf) else Path(source_pdf).resolve()
    if not candidate.exists():
        # try pdf dir
        candidate = (root / settings.pdf_dir / os.path.basename(source_pdf)).resolve()
    if not candidate.exists() or root not in candidate.parents and candidate != root:
        raise HTTPException(404, "source file not available")
    media = "application/pdf" if candidate.suffix.lower() == ".pdf" else "application/octet-stream"
    return FileResponse(str(candidate), media_type=media, filename=candidate.name)


@app.get("/api/evidence/{evidence_id}")
def api_evidence_get(evidence_id: str, request: Request):
    chunks = load_chunks(settings.canonical_db)
    chunk = next((c for c in chunks if c.get("chunk_id") == evidence_id), None)
    if not chunk:
        raise HTTPException(404, "evidence not found")
    uid = _current_user(request)
    if uid:
        allowed = _allowed_docs_for(request)
        if allowed is not None and chunk.get("document_id") not in (allowed or set()):
            raise HTTPException(403, "access denied")
    return normalize_evidence(chunk)


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


@app.get("/api/arxml/topology/mermaid")
def api_arxml_topology_mermaid(artifact_id: str, tenant: str = "default"):
    entry = _ARXML_STORE.get(artifact_id)
    if not entry or entry["topology"].artifact.tenant_id != tenant:
        raise HTTPException(404, "artifact not found or access denied")
    topo = entry["topology"]
    lines = ["flowchart LR"]
    ids = {}
    for c in topo.components:
        nid = "C" + str(len(ids))
        ids[c.qualified_name] = nid
        lines.append(f'  {nid}["{c.short_name}"]')
    for conn in topo.connectors:
        src = ids.get(conn.provider_component_ref or "")
        dst = ids.get(conn.requester_component_ref or "")
        if src and dst:
            label = conn.connector_type or "conn"
            lines.append(f'  {src} -->|{label}| {dst}')
    if not any("-->" in l for l in lines):
        # fallback: list components only
        pass
    return {"mermaid": "\\n".join(lines)}


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


# ---------------------------------------------------------------------------------------
# Evaluation screen
# ---------------------------------------------------------------------------------------

EVAL_DIR = os.environ.get("EVAL_REPORTS_DIR", "reports/evaluation")


def _eval_read_json(name: str, default):
    path = os.path.join(EVAL_DIR, name)
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


@app.get("/api/evaluation/latest")
def api_evaluation_latest():
    """The most recent evaluation run: headline metrics, per-category scores, worst failures."""
    payload = _eval_read_json("latest.json", None)
    if not payload:
        return {"available": False,
                "hint": "run: python -m src.evaluation.cli run --mode retrieval"}
    agg = payload.get("aggregate", {})
    return {
        "available": True,
        "label": payload.get("label"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "split": payload.get("split"),
        "llm_model": payload.get("llm_model"),
        "golden_sha256": payload.get("golden_sha256"),
        "coverage": payload.get("coverage"),
        "metrics_methods": payload.get("metrics_methods"),
        "aggregate": agg,
        "worst": payload.get("worst", [])[:20],
        "split_drift": payload.get("split_drift", []),
    }


@app.get("/api/evaluation/runs")
def api_evaluation_runs():
    """Run history for the trend view."""
    return {"runs": _eval_read_json(os.path.join("runs", "index.json"), [])}


@app.get("/api/evaluation/gate")
def api_evaluation_gate():
    """The last gate verdict against the agreed thresholds."""
    thresholds = _eval_read_json(os.path.join("..", "..", "data", "benchmarks",
                                              "eval_gate.json"), None) or {}
    return {"gate": _eval_read_json("gate.json", None),
            "thresholds": {k: v for k, v in thresholds.items() if not k.startswith("_")}}


@app.get("/api/evaluation/golden")
def api_evaluation_golden():
    """The golden set's coverage mix and the split that is frozen against it."""
    from src.evaluation.golden import coverage_report, load_golden
    from src.evaluation.splits import load_split
    path = os.environ.get("EVAL_GOLDEN_PATH", "data/benchmarks/autosar_golden_v2.jsonl")
    if not os.path.exists(path):
        return {"available": False, "path": path}
    items = load_golden(path)
    split_path = os.path.join(os.path.dirname(path), "holdout_v2.json")
    manifest = load_split(split_path) if os.path.exists(split_path) else None
    return {
        "available": True,
        "path": path,
        "coverage": coverage_report(items),
        "split": {"counts": (manifest or {}).get("counts"),
                  "ratio": (manifest or {}).get("holdout_ratio"),
                  "salt": (manifest or {}).get("salt"),
                  "golden_sha256": (manifest or {}).get("golden_sha256")},
    }


@app.get("/api/evaluation/review-sample")
def api_evaluation_review_sample():
    """The stratified sample that still needs expert review."""
    import csv
    path = os.environ.get("EVAL_REVIEW_CSV", "data/benchmarks/expert_review_v2.csv")
    if not os.path.exists(path):
        return {"available": False, "path": path}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    pending = [r for r in rows if not (r.get("review_decision") or "").strip()]
    return {"available": True, "path": path, "total": len(rows), "pending": len(pending),
            "rows": rows[:50]}


# ---------------- Test results, defects, release delta, config diff (P2) ----------------
class TestResultIngest(BaseModel):
    run_name: str = "manual"
    results: list[dict]


@app.post("/api/test-results")
def ingest_test_results(body: TestResultIngest, request: Request):
    user = _require_user(request)
    if not user:
        raise HTTPException(401, "authentication required")
    conn = _canonical_conn()
    try:
        run_id = "tr-" + uuid.uuid4().hex[:12]
        conn.execute("INSERT INTO test_runs(run_id,name,created_by,created_at) VALUES (?,?,?,?)",
                     (run_id, body.run_name, user, datetime.now(timezone.utc).isoformat()))
        for r in body.results:
            conn.execute(
                "INSERT INTO test_results(result_id,run_id,test_case_id,requirement_id,module,status,message,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("tres-" + uuid.uuid4().hex[:12], run_id, r.get("test_case_id"), r.get("requirement_id"),
                 r.get("module"), str(r.get("status", "unknown")), r.get("message"), datetime.now(timezone.utc).isoformat()))
        conn.commit()
        log_audit(conn, None, user, "ingest_test_results", "test_run", run_id, {"count": len(body.results)})
    finally:
        conn.close()
    return {"run_id": run_id, "ingested": len(body.results)}


@app.get("/api/test-results")
def list_test_results(request: Request, status: str = "", requirement_id: str = ""):
    user = _require_user(request)
    if not user:
        raise HTTPException(401, "authentication required")
    conn = _canonical_conn()
    try:
        q = "SELECT result_id,run_id,test_case_id,requirement_id,module,status,message,created_at FROM test_results WHERE 1=1"
        args = []
        if status:
            q += " AND status=?"; args.append(status)
        if requirement_id:
            q += " AND requirement_id=?"; args.append(requirement_id)
        rows = [dict(zip(["result_id","run_id","test_case_id","requirement_id","module","status","message","created_at"], r))
                for r in conn.execute(q, args).fetchall()]
    finally:
        conn.close()
    return {"results": rows, "count": len(rows)}


@app.get("/api/test-results/clusters")
def cluster_failures(request: Request):
    user = _require_user(request)
    if not user:
        raise HTTPException(401, "authentication required")
    conn = _canonical_conn()
    try:
        rows = conn.execute("SELECT status,message,COUNT(*) FROM test_results WHERE status!='passed' GROUP BY status,message").fetchall()
        clusters = [{"status": r[0], "message": r[1], "count": r[2]} for r in rows]
    finally:
        conn.close()
    return {"clusters": clusters}


@app.post("/api/defects")
def create_defect(body: dict, request: Request):
    user = _require_user(request)
    if not user:
        raise HTTPException(401, "authentication required")
    conn = _canonical_conn()
    try:
        did = "def-" + uuid.uuid4().hex[:12]
        conn.execute("INSERT INTO defects(defect_id,title,requirement_id,severity,status,created_by,created_at) VALUES (?,?,?,?,?,?,?)",
                     (did, body.get("title", "untitled"), body.get("requirement_id"), body.get("severity", "medium"),
                      "open", user, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        log_audit(conn, None, user, "create_defect", "defect", did)
    finally:
        conn.close()
    return {"defect_id": did}


@app.get("/api/defects")
def list_defects(request: Request, status: str = ""):
    user = _require_user(request)
    if not user:
        raise HTTPException(401, "authentication required")
    conn = _canonical_conn()
    try:
        q = "SELECT defect_id,title,requirement_id,severity,status,created_by,created_at FROM defects"
        args = []
        if status:
            q += " WHERE status=?"; args.append(status)
        rows = [dict(zip(["defect_id","title","requirement_id","severity","status","created_by","created_at"], r))
                for r in conn.execute(q, args).fetchall()]
    finally:
        conn.close()
    return {"defects": rows, "count": len(rows)}


@app.post("/api/safety-goals")
def create_safety_goal(body: dict, request: Request):
    user = _require_user(request)
    if not user:
        raise HTTPException(401, "authentication required")
    conn = _canonical_conn()
    try:
        gid = "sg-" + uuid.uuid4().hex[:12]
        conn.execute("INSERT INTO safety_goals(goal_id,asil,description,requirement_id,created_by,created_at) VALUES (?,?,?,?,?,?)",
                     (gid, body.get("asil", "QM"), body.get("description", ""), body.get("requirement_id"),
                      user, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        log_audit(conn, None, user, "create_safety_goal", "safety_goal", gid)
    finally:
        conn.close()
    return {"goal_id": gid}


@app.get("/api/safety-goals")
def list_safety_goals(request: Request, asil: str = ""):
    user = _require_user(request)
    if not user:
        raise HTTPException(401, "authentication required")
    conn = _canonical_conn()
    try:
        q = "SELECT goal_id,asil,description,requirement_id,created_by,created_at FROM safety_goals"
        args = []
        if asil:
            q += " WHERE asil=?"; args.append(asil)
        rows = [dict(zip(["goal_id","asil","description","requirement_id","created_by","created_at"], r))
                for r in conn.execute(q, args).fetchall()]
    finally:
        conn.close()
    return {"safety_goals": rows, "count": len(rows)}


@app.post("/api/auth/sso/login")
def auth_sso_login(body: dict, request: Request, response: Response):
    secret = os.environ.get("ASRBRAIN_SSO_SECRET", "")
    if not secret:
        raise HTTPException(503, "SSO not configured (set ASRBRAIN_SSO_SECRET)")
    token = body.get("token", "")
    if not token:
        raise HTTPException(400, "token required")
    try:
        import jwt
        claims = jwt.decode(token, secret, algorithms=["HS256"])
    except Exception as exc:
        raise HTTPException(401, f"invalid SSO token: {exc}")
    email = claims.get("email") or claims.get("sub")
    if not email:
        raise HTTPException(400, "token missing email/sub")
    display_name = claims.get("name") or str(email).split("@")[0]
    conn = _canonical_conn()
    try:
        row = conn.execute("SELECT user_id FROM users WHERE email=?", (str(email).lower(),)).fetchone()
        if row:
            user_id = row[0]
        else:
            user_id = create_user(conn, str(email), os.urandom(16).hex(), display_name=display_name)
        token_val = create_session(conn, user_id, user_agent=request.headers.get("user-agent", ""),
                                  ip=request.client.host if request.client else "")
    finally:
        conn.close()
    response.set_cookie("asrbrain_session", token_val, httponly=True, samesite="lax")
    return {"user_id": user_id, "email": email}


@app.get("/api/model-usage")
def model_usage(request: Request):
    user = _require_user(request)
    if not user:
        raise HTTPException(401, "authentication required")
    conn = _canonical_conn()
    try:
        rows = [dict(zip(["usage_id","model","kind","latency_ms","prompt_chars","created_at"], r))
                for r in conn.execute("SELECT usage_id,model,kind,latency_ms,prompt_chars,created_at FROM model_usage ORDER BY created_at DESC LIMIT 100").fetchall()]
    finally:
        conn.close()
    return {"usage": rows, "count": len(rows)}


@app.get("/api/releases/delta")
def release_delta(base: str, target: str):
    conn = _canonical_conn()
    try:
        base_chunks = conn.execute("SELECT chunk_id,requirement_ids FROM chunks WHERE autosar_release=?", (base,)).fetchall()
        target_chunks = conn.execute("SELECT chunk_id,requirement_ids FROM chunks WHERE autosar_release=?", (target,)).fetchall()
        base_ids = {r[0] for r in base_chunks}
        target_ids = {r[0] for r in target_chunks}
        base_reqs = {rid for r in base_chunks for rid in (r[1] or "").split(",") if rid}
        target_reqs = {rid for r in target_chunks for rid in (r[1] or "").split(",") if rid}
    finally:
        conn.close()
    return {
        "base": base, "target": target,
        "base_chunks": len(base_ids), "target_chunks": len(target_ids),
        "added_chunks": len(target_ids - base_ids), "removed_chunks": len(base_ids - target_ids),
        "added_requirements": sorted(target_reqs - base_reqs)[:50],
        "removed_requirements": sorted(base_reqs - target_reqs)[:50],
    }


@app.get("/api/config/pipeline/diff")
def config_diff(from_version: int, to_version: int):
    conn = _canonical_conn()
    try:
        from src.config.pipeline_config import list_configs
        configs = list_configs(conn)
    finally:
        conn.close()
    a = next((c for c in configs if c.get("version") == from_version), None)
    b = next((c for c in configs if c.get("version") == to_version), None)
    if not a or not b:
        raise HTTPException(404, "config version not found")
    import json as _json
    try:
        from src.diff.engine import diff_records
        diff = diff_records([a], [b])
    except Exception:
        diff = {"from": a.get("config_json"), "to": b.get("config_json")}
    return {"from_version": from_version, "to_version": to_version, "diff": diff}
