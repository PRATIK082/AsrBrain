"""Ollama + cloud generation with deterministic fallback (works without any LLM)."""
from __future__ import annotations
import httpx
from ..config.settings import settings, TOKEN_CAPS
from .prompts import build_prompt
from .providers import ProviderSpec, complete as _provider_complete


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


def extractive_fallback(query: str, evidence: list[dict]) -> str:
    """No-LLM path: returns top compressed passages with evidence labels. Never hallucinates."""
    lines = ["## Direct answer (extractive fallback — no LLM available)", ""]
    for i, c in enumerate(evidence[:5], start=1):
        lines.append(f"[E{i}] p.{c.get('page_start')}: {c.get('compressed', c.get('normalized_text',''))[:800]}")
        lines.append("")
    lines.append("## Sources")
    for i, c in enumerate(evidence[:5], start=1):
        lines.append(f"[E{i}] {c.get('source_pdf')} p.{c.get('page_start')}-{c.get('page_end')} "
                     f"({c.get('autosar_release') or 'unknown'}/{c.get('platform') or 'unknown'})")
    return "\n".join(lines)


def default_spec() -> ProviderSpec:
    """Local-first default; model auto-resolved to an installed Ollama model."""
    return ProviderSpec(kind="ollama", model=pick_model(),
                        base_url=settings.ollama_base_url,
                        timeout_s=settings.ollama_timeout_s)


def generate(query: str, evidence: list[dict], comparison: bool = False,
             spec: ProviderSpec | None = None) -> dict:
    if spec is None:
        # legacy path: local Ollama default (keeps POST /query working unchanged)
        ok, msg = ollama_available()
        if not ok:
            return {"draft": extractive_fallback(query, evidence), "llm": "fallback", "note": msg}
        return _generate_ollama(query, evidence, comparison)
    if not evidence:
        return {"draft": extractive_fallback(query, evidence), "llm": "fallback",
                "note": "no evidence"}
    prompt = build_prompt(query, evidence, comparison)
    draft, note = _provider_complete(prompt, spec)
    if draft:
        return {"draft": draft, "llm": f"{spec.kind}:{spec.model}"}
    return {"draft": extractive_fallback(query, evidence), "llm": "fallback", "note": note}


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
        return {"draft": extractive_fallback(query, evidence), "llm": "fallback",
                "note": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"draft": extractive_fallback(query, evidence), "llm": "fallback", "note": str(e)}
