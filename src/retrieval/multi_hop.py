"""Multi-hop sub-retrieval planner (generic).

Given a refined query profile, decide whether multiple independent context
lookups are required and return a prioritized list of sub-retrieval tasks.
Falls back to a single task when no LLM is available.
"""
from __future__ import annotations
import json
import re
from ..config.settings import settings


MULTI_HOP_PROMPT = """You are the central Routing Controller of an AUTOSAR Knowledge Engine.
Look at the expanded developer query profile and decide if multiple independent context
lookups are required.

[QUERY PROFILE]
{profile}
[END QUERY PROFILE]

Output a JSON array of objects with keys step, target, focus. Example:
[{{"step": 1, "target": "AUTOSAR SWS", "focus": "BswM MainFunction timing constraints"}}]

Output ONLY the raw JSON array. If a single lookup suffices, return a one-element array.
"""


def plan_subqueries(profile: dict) -> list[dict]:
    """Return list of {'step','target','focus'} tasks. Always at least one."""
    base = {"step": 1, "target": "AUTOSAR context", "focus": profile.get("keywords", [""])[0] if profile.get("keywords") else ""}
    try:
        from ..generation.providers import ProviderSpec, complete as _complete
        spec = ProviderSpec(kind="ollama", model=settings.llm_model,
                           base_url=settings.ollama_base_url, timeout_s=15.0)
        prompt = MULTI_HOP_PROMPT.format(profile=json.dumps(profile, ensure_ascii=False))
        text, _ = _complete(prompt, spec)
        if text:
            m = re.search(r"\[.*\]", text, re.S)
            if m:
                arr = json.loads(m.group(0))
                if isinstance(arr, list) and arr:
                    return arr
    except Exception:
        pass
    # ollama fallback
    try:
        import httpx
        r = httpx.post(f"{settings.ollama_base_url}/api/generate",
                       json={"model": settings.llm_model,
                             "prompt": MULTI_HOP_PROMPT.format(profile=json.dumps(profile)),
                             "stream": False, "options": {"temperature": 0.1, "num_predict": 300}},
                       timeout=15.0)
        if r.status_code == 200:
            text = r.json().get("response", "")
            m = re.search(r"\[.*\]", text, re.S)
            if m:
                arr = json.loads(m.group(0))
                if isinstance(arr, list) and arr:
                    return arr
    except Exception:
        pass
    return [base]