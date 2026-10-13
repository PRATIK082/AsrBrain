"""Conditional PDF page-image extraction + diagram recreation orchestration.

Text embedding/chunking is never disturbed: image rendering is opt-in per page
(diagram signals or explicit page list) and every failure returns a text fallback.
"""
from __future__ import annotations

import os
import re

_DIAGRAM_HINTS = re.compile(
    r"(figure|diagram|flowchart|architecture|sequence|state\s?machine|process\s?flow"
    r"|decision|arrow|swimlane|component\s+diagram|deployment\s+view)", re.I)


def page_likely_has_diagram(page_text: str, has_vector_drawings: bool = False) -> bool:
    """Heuristic gate: caption hints, sparse text with structure words, or vector drawings."""
    if has_vector_drawings:
        return True
    t = page_text or ""
    if _DIAGRAM_HINTS.search(t):
        return True
    if len(t.strip()) < 120:
        return False
    return False


def render_page_image(pdf_path: str, page_index: int = 0, dpi: int = 200) -> bytes | None:
    """Render one PDF page to PNG bytes via PyMuPDF. Returns None when unavailable."""
    try:
        import fitz  # PyMuPDF, optional
    except Exception:
        return None
    try:
        doc = fitz.open(pdf_path)
        if page_index < 0 or page_index >= len(doc):
            return None
        page = doc[page_index]
        pix = page.get_pixmap(dpi=dpi)
        return bytes(pix.tobytes("png"))
    except Exception:
        return None


def page_has_vector_drawings(pdf_path: str, page_index: int = 0) -> bool:
    """True when the page contains vector drawings/images (diagram candidate)."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        page = doc[page_index]
        return bool(page.get_drawings() or page.get_images(full=True))
    except Exception:
        return False


def recreate_diagrams_for_pdf(pdf_path: str, pages: list[int] | None = None,
                              dpi: int = 200, caption: str = "",
                              provider: str = "", model: str = "") -> list[dict]:
    """End-to-end: gate pages -> render PNG -> vision -> validate-or-fallback.

    `pages`: explicit 0-based page list; when None, auto-gate every page on
    diagram signals. Each result: {page, mermaid?|fallback?, ...provenance}.
    Text pipeline callers ignore image failures and keep original chunks.
    """
    from .vlm import recreate_mermaid_from_image, summarize_steps_fallback

    # Resolve candidate pages
    candidates: list[int] = []
    if pages is not None:
        candidates = [int(p) for p in pages]
    else:
        try:
            import fitz
            doc = fitz.open(pdf_path)
            for i, pg in enumerate(doc):
                try:
                    text = pg.get_text() or ""
                except Exception:
                    text = ""
                drawings = False
                try:
                    drawings = bool(pg.get_drawings() or pg.get_images(full=True))
                except Exception:
                    drawings = False
                if page_likely_has_diagram(text, drawings):
                    candidates.append(i)
        except Exception:
            return [{"page": -1,
                     "fallback": summarize_steps_fallback("", caption),
                     "error": "page-image backend unavailable (install pymupdf)",
                     "source_pdf": os.path.basename(pdf_path)}]
    results: list[dict] = []
    for p in candidates:
        img = render_page_image(pdf_path, p, dpi=dpi)
        if img is None:
            results.append({"page": p,
                            "fallback": summarize_steps_fallback("", caption),
                            "error": "page render unavailable (install pymupdf)",
                            "source_pdf": os.path.basename(pdf_path)})
            continue
        out = recreate_mermaid_from_image(img, caption=caption,
                                          provider=provider or os.environ.get("VLM_PROVIDER", "ollama"),
                                          model=model or os.environ.get("VLM_MODEL", ""))
        results.append({"page": p, **out, "source_pdf": os.path.basename(pdf_path),
                        "is_inferred": True,
                        "note": "Mermaid is recreated from figure pixels; cite original figure for normative claims."})
    return results
