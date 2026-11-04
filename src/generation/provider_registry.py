"""Persistent model provider registry (Slice 3)."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from .providers import ProviderSpec, list_ollama_models
import httpx


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_provider(conn: sqlite3.Connection, workspace_id: str | None, name: str, kind: str,
                    task: str, base_url: str, model: str, api_key_env: str = "",
                    timeout_s: float = 120.0, data_transfer_policy: str = "local_only",
                    enabled: bool = True) -> str:
    provider_id = "prov-" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO model_providers(provider_id,workspace_id,name,kind,task,base_url,model,"
        "api_key_env,timeout_s,data_transfer_policy,enabled,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (provider_id, workspace_id, name, kind, task, base_url, model, api_key_env,
         timeout_s, data_transfer_policy, 1 if enabled else 0, _now(), _now()))
    conn.commit()
    return provider_id


def list_providers(conn: sqlite3.Connection, workspace_id: str | None = None,
                   task: str | None = None) -> list[dict]:
    q = "SELECT provider_id,workspace_id,name,kind,task,base_url,model,api_key_env,timeout_s,data_transfer_policy,enabled FROM model_providers WHERE 1=1"
    params: list = []
    if workspace_id is not None:
        q += " AND (workspace_id = ? OR workspace_id IS NULL)"
        params.append(workspace_id)
    if task:
        q += " AND task = ?"
        params.append(task)
    rows = conn.execute(q, params).fetchall()
    cols = ["provider_id", "workspace_id", "name", "kind", "task", "base_url", "model",
            "api_key_env", "timeout_s", "data_transfer_policy", "enabled"]
    return [dict(zip(cols, r)) for r in rows]


def get_provider(conn: sqlite3.Connection, provider_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT provider_id,workspace_id,name,kind,task,base_url,model,api_key_env,timeout_s,data_transfer_policy,enabled "
        "FROM model_providers WHERE provider_id = ?", (provider_id,)).fetchone()
    if not row:
        return None
    cols = ["provider_id", "workspace_id", "name", "kind", "task", "base_url", "model",
            "api_key_env", "timeout_s", "data_transfer_policy", "enabled"]
    return dict(zip(cols, row))


def update_provider(conn: sqlite3.Connection, provider_id: str, **fields) -> bool:
    allowed = {"name", "kind", "task", "base_url", "model", "api_key_env", "timeout_s",
               "data_transfer_policy", "enabled"}
    sets = []
    params = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        sets.append(f"{k} = ?")
        params.append(v)
    if not sets:
        return False
    sets.append("updated_at = ?")
    params.append(_now())
    params.append(provider_id)
    conn.execute(f"UPDATE model_providers SET {', '.join(sets)} WHERE provider_id = ?", params)
    conn.commit()
    return True


def delete_provider(conn: sqlite3.Connection, provider_id: str) -> bool:
    conn.execute("DELETE FROM model_providers WHERE provider_id = ?", (provider_id,))
    conn.commit()
    return True


def to_spec(provider: dict) -> ProviderSpec:
    import os
    api_key = os.getenv(provider.get("api_key_env") or "", "") if provider.get("api_key_env") else ""
    return ProviderSpec(
        kind=provider.get("kind", "ollama"),
        model=provider.get("model", ""),
        base_url=provider.get("base_url", "http://127.0.0.1:11434"),
        api_key=api_key,
        timeout_s=float(provider.get("timeout_s") or 120.0),
    )


def test_connection(provider: dict) -> dict:
    kind = provider.get("kind")
    base_url = provider.get("base_url", "")
    try:
        if kind == "ollama":
            models = list_ollama_models(base_url)
            return {"ok": True, "models": models[:20], "count": len(models)}
        # OpenAI-compatible: GET /models
        headers = {}
        import os
        if provider.get("api_key_env"):
            key = os.getenv(provider["api_key_env"], "")
            if key:
                headers["Authorization"] = f"Bearer {key}"
        r = httpx.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=10.0)
        if r.status_code == 200:
            data = r.json().get("data", [])
            return {"ok": True, "models": [m.get("id") for m in data][:20], "count": len(data)}
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def discover_models(provider: dict) -> list[str]:
    res = test_connection(provider)
    return res.get("models", []) if res.get("ok") else []
