"""LLM-assisted ingestion enrichment (optional, offline).

For each text chunk, produce a structural context header:
Layer, Target_Modules, Document_Type, Contextual_Summary. Intended to be run
as a batch job over the corpus and stored alongside chunks; not on the hot path.
"""
from __future__ import annotations
import json
import re
from ..config.settings import settings

ENRICHMENT_PROMPT = """You are an expert AUTOSAR Architecture Ingestion Engine. Analyze the text
chunk and output a JSON object.

[INPUT CHUNK]
{chunk}
[END INPUT CHUNK]

Return ONLY valid JSON with keys:
"Layer": one of ASW, RTE, BSW-Services, BSW-Memory, BSW-Communication, MCAL, CDD, System.
"Target_Modules": list of AUTOSAR modules referenced.
"Document_Type": SWS, SRS, TR, Internal Architecture Guideline, Source Code Comment, ARXML Schema.
"Contextual_Summary": one concise sentence of what this chunk governs, including dependencies.
"""


def enrich_chunk(chunk_text: str) -> dict:
    """Return enrichment dict; empty dict on failure (never raises)."""
    try:
        from ..generation.providers import ProviderSpec, complete as _complete
        spec = ProviderSpec(kind="ollama", model=settings.llm_model,
                           base_url=settings.ollama_base_url, timeout_s=30.0)
        text, _ = _complete(ENRICHMENT_PROMPT.format(chunk=chunk_text[:4000]), spec)
        if text:
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict):
                    return obj
    except Exception:
        pass
    try:
        import httpx
        r = httpx.post(f"{settings.ollama_base_url}/api/generate",
                       json={"model": settings.llm_model,
                             "prompt": ENRICHMENT_PROMPT.format(chunk=chunk_text[:4000]),
                             "stream": False, "options": {"temperature": 0.1, "num_predict": 250}},
                       timeout=30.0)
        if r.status_code == 200:
            text = r.json().get("response", "")
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict):
                    return obj
    except Exception:
        pass
    return {}