"""Ollama + cloud generation with deterministic fallback (works without any LLM)."""
from __future__ import annotations
import re
import time
import httpx
import sqlite3
from pathlib import Path
from ..config.settings import settings, TOKEN_CAPS
from .prompts import build_prompt
from .providers import ProviderSpec, complete as _provider_complete

# A draft that does not end with terminal punctuation was cut by the token cap.
_TERMINAL_RE = re.compile(r"[.!?…;:\"'”’)>\]}]$")


def was_cut_off(draft: str) -> bool:
    """True when a draft ends mid-sentence — i.e. the length cap truncated it."""
    s = (draft or "").strip()
    if not s:
        return False
    return _TERMINAL_RE.search(s) is None


CUT_NOTICE = ("> Answer reached the response length cap and may be incomplete — "
              "pick Detailed length for the full procedure.")


def ollama_available() -> tuple[bool, str]:
    try:
        r = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
        return (r.status_code == 200, "Connected" if r.status_code == 200 else f"HTTP {r.status_code}")
    except Exception as e:
        return False, str(e)


def available_models() -> list[str]:
    try:
        r = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
        return [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        return []


def pick_model() -> str:
    models = available_models()
    if not models:
        return settings.llm_model
    if settings.llm_model in models:
        return settings.llm_model
    # prefer same-size instruct models, else first available (avoids hanging on a missing pull)
    return models[0]


def extractive_fallback(query: str, evidence: list[dict], note: str = "") -> str:
    """No-LLM path: never hallucinates. Shows a short reason and source list only."""
    lines = ["## Direct answer (extractive fallback — no LLM available)", ""]
    if note:
        lines.append(f"**Reason:** {note}")
        lines.append("")
    lines.append("No LLM was available to synthesize an answer from the retrieved evidence. "
                 "The sources below are the best matches; connect an LLM (Ollama or cloud) "
                 "for a synthesized, cited answer.")
    lines.append("")
    lines.append("## Sources")
    for i, c in enumerate(evidence[:8], start=1):
        snippet = (c.get("compressed") or c.get("normalized_text") or "")[:240].replace("\n", " ")
        lines.append(f"[E{i}] {c.get('source_pdf')} p.{c.get('page_start')}-{c.get('page_end')} "
                     f"({c.get('autosar_release') or 'unknown'}/{c.get('platform') or 'unknown'})")
        if snippet:
            lines.append(f"    {snippet}")
    return "\n".join(lines)


def default_spec() -> ProviderSpec:
    """Local-first default; model auto-resolved to an installed Ollama model."""
    return ProviderSpec(kind="ollama", model=pick_model(),
                        base_url=settings.ollama_base_url,
                        timeout_s=settings.ollama_timeout_s)


def _record_usage(model: str, kind: str, start: float, prompt_chars: int) -> None:
    try:
        import uuid, sqlite3, time
        from datetime import datetime, timezone
        conn = sqlite3.connect(settings.canonical_db)
        conn.execute("INSERT INTO model_usage(usage_id,model,kind,latency_ms,prompt_chars,created_at) VALUES (?,?,?,?,?,?)",
                     ("mu-" + uuid.uuid4().hex[:12], model, kind,
                      round((time.time() - start) * 1000, 1), prompt_chars,
                      datetime.now(timezone.utc).isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass


def _record_usage(model: str, kind: str, start: float, prompt_chars: int) -> None:
    try:
        import uuid, sqlite3, time
        from datetime import datetime, timezone
        conn = sqlite3.connect(settings.canonical_db)
        conn.execute("INSERT INTO model_usage(usage_id,model,kind,latency_ms,prompt_chars,created_at) VALUES (?,?,?,?,?,?)",
                     ("mu-" + uuid.uuid4().hex[:12], model, kind,
                      round((time.time() - start) * 1000, 1), prompt_chars,
                      datetime.now(timezone.utc).isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass


def generate(query: str, evidence: list[dict], comparison: bool = False,
             spec: ProviderSpec | None = None, intent: str = "") -> dict:
    import time
    start = time.time()
    if spec is None:
        # legacy path: local Ollama default (keeps POST /query working unchanged)
        ok, msg = ollama_available()
        if not ok:
            _record_usage("fallback", "ollama", start, len(query))
            return {"draft": extractive_fallback(query, evidence, note=msg), "llm": "fallback", "note": msg}
        out = _generate_ollama(query, evidence, comparison, intent=intent)
        _record_usage(out.get("llm", "ollama"), "ollama", start, len(query))
        return out
    if not evidence:
        _record_usage("fallback", spec.kind, start, len(query))
        return {"draft": extractive_fallback(query, evidence, note="no evidence"), "llm": "fallback",
                "note": "no evidence"}
    prompt = build_prompt(query, evidence, comparison, intent=intent)
    draft, note = _provider_complete(prompt, spec)
    if draft:
        _record_usage(f"{spec.kind}:{spec.model}", spec.kind, start, len(prompt))
        return {"draft": draft, "llm": f"{spec.kind}:{spec.model}"}
    _record_usage("fallback", spec.kind, start, len(prompt))
    return {"draft": extractive_fallback(query, evidence, note=note), "llm": "fallback", "note": note}


def _generate_ollama(query: str, evidence: list[dict], comparison: bool = False,
                   intent: str = "") -> dict:
    model = pick_model()
    prompt = build_prompt(query, evidence, comparison, intent)
    try:
        r = httpx.post(f"{settings.ollama_base_url}/api/generate",
                        json={"model": model, "prompt": prompt, "stream": False,
                              "options": {"temperature": 0.2, "num_ctx": TOKEN_CAPS.get("num_ctx", 8192), "top_p": 0.9,
                                          "num_predict": settings.llm_num_predict}},
                       timeout=settings.ollama_timeout_s)
        if r.status_code == 200:
            return {"draft": r.json().get("response", ""), "llm": model}
        return {"draft": extractive_fallback(query, evidence, note=f"HTTP {r.status_code}"), "llm": "fallback",
                "note": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"draft": extractive_fallback(query, evidence, note=str(e)), "llm": "fallback", "note": str(e)}
