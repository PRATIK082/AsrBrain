"""VLM diagram analysis (Phase 2 §15, P2). Local VLM by default; descriptions are
supplemental — every statement keeps original figure/page provenance and graph links
are confidence-scored, never authoritative facts.

Extension: multimodal diagram recreation — PDF page snapshots are fed to a vision
endpoint which recreates flowcharts/architectures as fenced ```mermaid blocks.
Generated mermaid is structurally validated; on failure we fall back to a text
step summary so text embedding/chunking never breaks.
"""
from __future__ import annotations

import base64
import os
import re

from pydantic import BaseModel, Field

DIAGRAM_SYSTEM_PROMPT = (
    "You are an expert systems layout engineer. Look closely at this PDF page "
    "screenshot containing a flowchart, architectural layout, or process diagram. "
    "Analyze all paths, structural labels, decision diamonds, connection boundaries, "
    "and directional arrows. Recreate this entire diagram accurately by converting it "
    "into valid Mermaid.js diagram syntax. Return ONLY the raw mermaid code wrapped "
    "securely inside a ```mermaid markdown block. Do not write introductory or "
    "concluding filler text."
)

_MERMAID_MARKERS = ("graph td", "graph lr", "graph tb", "graph bt", "graph rl",
                    "flowchart", "sequencediagram", "sequenceDiagram", "subgraph",
                    "stateDiagram", "classDiagram", "erDiagram", "gantt", "pie")


def extract_mermaid_block(text: str) -> str | None:
    """Return raw mermaid code inside the first ```mermaid fence, else None."""
    m = re.search(r"```mermaid\s+(.*?)```", text or "", re.I | re.S)
    if not m:
        return None
    return m.group(1).strip()


def validate_mermaid(text: str) -> bool:
    """Check for standard Mermaid structural markers inside (or outside) a fence."""
    code = extract_mermaid_block(text) or (text or "")
    low = code.lower()
    if not code.strip():
        return False
    # must contain a diagram declaration marker
    if not any(marker in low for marker in _MERMAID_MARKERS):
        return False
    # must contain at least one edge/node connector to avoid single-word false positives
    if not re.search(r"(-->|---|==>|\|.*?\||\[.*?\]|\(.*?\)|\{.*?\})", code):
        return False
    return True


def wrap_mermaid(code: str) -> str:
    code = (code or "").strip().strip("`").strip()
    return f"```mermaid\n{code}\n```"


def summarize_steps_fallback(ocr_text: str = "", caption: str = "") -> str:
    """Safe text fallback when vision output fails validation — never raises."""
    lines = [ln.strip("-•* \t") for ln in (ocr_text or "").splitlines()]
    steps = [ln for ln in lines if len(ln) > 3][:12]
    if not steps and caption:
        steps = [caption.strip()]
    if not steps:
        return ("Diagram text summary unavailable — page contained no extractable "
                "labels; original figure preserved for manual review.")
    numbered = "\n".join(f"{i}. {s[:200]}" for i, s in enumerate(steps, 1))
    return f"Diagram steps (text fallback — figure preserved):\n{numbered}"


def recreate_mermaid_from_image(image_bytes: bytes, caption: str = "",
                                provider: str = "ollama",
                                model: str = "",
                                timeout_s: float = 60.0) -> dict:
    """Feed a page snapshot to a vision endpoint; return validated mermaid or fallback.

    Providers: 'ollama' (local vision, default), 'openai' (OpenAI-compatible chat
    completions with image_url). Never raises — returns {'mermaid': ...} or
    {'fallback': ...} so the pipeline cannot break text chunking.
    """
    import httpx

    provider = (provider or os.environ.get("VLM_PROVIDER", "ollama")).lower()
    model = model or os.environ.get("VLM_MODEL", "llava" if provider == "ollama" else "gpt-4o-mini")
    b64 = base64.b64encode(image_bytes).decode("ascii")
    raw = ""
    try:
        if provider == "openai":
            base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            key = os.environ.get("OPENAI_API_KEY", "")
            r = httpx.post(f"{base}/chat/completions",
                           headers={"Authorization": f"Bearer {key}"},
                           json={"model": model, "max_tokens": 1500,
                                 "messages": [
                                     {"role": "system", "content": DIAGRAM_SYSTEM_PROMPT},
                                     {"role": "user", "content": [
                                         {"type": "text", "text": f"Recreate this diagram. Caption: {caption or 'n/a'}"},
                                         {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]},
                           timeout=timeout_s)
            r.raise_for_status()
            raw = str(r.json()["choices"][0]["message"]["content"] or "")
        else:  # ollama local vision (/api/chat with images)
            base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
            r = httpx.post(f"{base}/api/chat",
                           json={"model": model, "stream": False,
                                 "messages": [
                                     {"role": "system", "content": DIAGRAM_SYSTEM_PROMPT},
                                     {"role": "user", "content": f"Recreate this diagram. Caption: {caption or 'n/a'}",
                                      "images": [b64]}]},
                           timeout=timeout_s)
            r.raise_for_status()
            raw = str(r.json().get("message", {}).get("content", "") or "")
    except Exception as e:
        return {"fallback": summarize_steps_fallback("", caption),
                "error": f"vision endpoint unreachable ({type(e).__name__})",
                "provider": provider, "model": model}
    code = extract_mermaid_block(raw) or raw.strip()
    candidate = wrap_mermaid(code) if "```mermaid" not in raw.lower() else raw.strip()
    if validate_mermaid(candidate):
        return {"mermaid": candidate, "provider": provider, "model": model}
    return {"fallback": summarize_steps_fallback(code, caption),
            "error": "vision output failed mermaid validation",
            "provider": provider, "model": model, "raw_preview": raw[:500]}


class DiagramEvidence(BaseModel):
    evidence_id: str
    source_document: str = ""
    page: int = 0
    caption: str = ""
    ocr_text: str = ""
    vlm_description: str = ""
    linked_entities: list[dict] = Field(default_factory=list)
    is_inferred: bool = True
    provenance: dict = Field(default_factory=dict)


def analyze_diagram(image_path: str, caption: str = "", ocr_text: str = "",
                    page: int = 0, document_id: str = "",
                    local_vlm: object | None = None) -> DiagramEvidence:
    """Run local VLM (or deterministic fallback) and wrap output with provenance."""
    desc = ""
    if local_vlm is not None and hasattr(local_vlm, "describe"):
        desc = str(local_vlm.describe(image_path))
    else:
        desc = f"Diagram supplemental description pending local-VLM review. Caption: {caption or 'n/a'}."
    eid = f"fig-{abs(hash(image_path)) % 10**8:08d}"
    return DiagramEvidence(
        evidence_id=eid, source_document=document_id, page=page, caption=caption,
        ocr_text=ocr_text, vlm_description=desc, is_inferred=True,
        provenance={"image_path": image_path, "page": page, "document_id": document_id,
                    "caption": caption, "model": getattr(local_vlm, "model_name", "local-vlm-fallback"),
                    "note": "VLM output is supplemental; cite original figure for normative claims"})
