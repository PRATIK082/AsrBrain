"""LLM-assisted query refinement (generic, not module-specific).

Maps a natural-language question to an AUTOSAR domain profile:
intent, expanded keywords, implied modules, target layers. Falls back to a
deterministic, alias-based profile when no LLM is available so retrieval
keeps working offline.
"""
from __future__ import annotations
import json
import re
from ..config.settings import settings
from ..generation.providers import ProviderSpec, complete as _provider_complete
from .query_understanding import parse as _parse_qu


REFINER_PROMPT = """You are an Advanced Automotive and AUTOSAR Query Refiner. Rewrite the user's
natural language question into an optimized retrieval profile.

[USER QUERY]
{query}
[END USER QUERY]

Output using exactly this format:
INTENT: [Configuration Troubleshooting|API Usage|Architectural Design|ARXML Syntax|BSW Module Interaction|Definition|Other]
KEYWORDS: [comma-separated synonyms, acronyms, standard technical phrases]
MODULES: [comma-separated AUTOSAR BSW/RTE modules]
LAYERS: [comma-separated AUTOSAR stack layers]
"""


def _fallback_profile(query: str) -> dict:
    plan = _parse_qu(query)
    return {
        "intent": plan.intent,
        "keywords": [query] + list(plan.modules) + list(plan.api_names),
        "modules": list(plan.modules),
        "layers": [],
        "raw": "",
    }


def _parse_profile(text: str, query: str) -> dict:
    intent = ""
    keywords: list[str] = []
    modules: list[str] = []
    layers: list[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        m = re.match(r"INTENT:\s*(.*)", line, re.I)
        if m:
            intent = m.group(1).strip()
            continue
        m = re.match(r"KEYWORDS:\s*(.*)", line, re.I)
        if m:
            keywords = [x.strip() for x in m.group(1).split(",") if x.strip()]
            continue
        m = re.match(r"MODULES:\s*(.*)", line, re.I)
        if m:
            modules = [x.strip() for x in m.group(1).split(",") if x.strip()]
            continue
        m = re.match(r"LAYERS:\s*(.*)", line, re.I)
        if m:
            layers = [x.strip() for x in m.group(1).split(",") if x.strip()]
            continue
    if not intent:
        return _fallback_profile(query)
    return {"intent": intent, "keywords": keywords or [query], "modules": modules,
            "layers": layers, "raw": text}


def refine(query: str, spec: ProviderSpec | None = None) -> dict:
    """Return a profile dict. Uses LLM when available, else deterministic fallback."""
    if spec is None:
        try:
            from ..generation.answer import default_spec
            spec = default_spec()
        except Exception:
            spec = None
    if spec is not None:
        try:
            from ..generation.providers import complete as _complete
            prompt = REFINER_PROMPT.format(query=query)
            text, _ = _complete(prompt, spec)
            if text:
                return _parse_profile(text, query)
        except Exception:
            pass
    # try ollama directly as a last resort
    try:
        import httpx
        r = httpx.post(f"{settings.ollama_base_url}/api/generate",
                       json={"model": settings.llm_model, "prompt": REFINER_PROMPT.format(query=query),
                             "stream": False, "options": {"temperature": 0.1, "num_predict": 200}},
                       timeout=15.0)
        if r.status_code == 200:
            return _parse_profile(r.json().get("response", ""), query)
    except Exception:
        pass
    return _fallback_profile(query)