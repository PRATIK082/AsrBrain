"""Diagram recreation: mermaid validation, fallback, prompt contract, page gating."""
from src.ingestion.vlm import (
    DIAGRAM_SYSTEM_PROMPT,
    extract_mermaid_block,
    summarize_steps_fallback,
    validate_mermaid,
    wrap_mermaid,
)
from src.ingestion.diagram_mermaid import page_likely_has_diagram, render_page_image


def test_system_prompt_contract():
    assert "systems layout engineer" in DIAGRAM_SYSTEM_PROMPT.lower()
    assert "```mermaid" in DIAGRAM_SYSTEM_PROMPT
    assert "only" in DIAGRAM_SYSTEM_PROMPT.lower()


def test_validate_mermaid_accepts_flowchart():
    good = "```mermaid\ngraph TD\n  A[Start] --> B{Decide}\n  B -->|yes| C[Done]\n```"
    assert validate_mermaid(good) is True
    assert validate_mermaid("graph LR\n  X --> Y") is True
    assert validate_mermaid("flowchart TD\n  A --- B") is True


def test_validate_mermaid_rejects_prose_and_empty():
    assert validate_mermaid("") is False
    assert validate_mermaid("Here is your architecture overview.") is False
    assert validate_mermaid("```mermaid\nhello world\n```") is False


def test_extract_and_wrap_roundtrip():
    code = extract_mermaid_block("prefix ```mermaid\ngraph TD\n A-->B\n``` suffix")
    assert code is not None and "graph TD" in code
    assert extract_mermaid_block("no fence here") is None
    assert validate_mermaid(wrap_mermaid("graph TD\n  A-->B")) is True


def test_fallback_never_breaks_pipeline():
    assert "unavailable" in summarize_steps_fallback().lower()
    out = summarize_steps_fallback("- Init\n- Decide\n- Act", caption="flow")
    assert "1. Init" in out and "2. Decide" in out
    # fallback output itself must not falsely validate as mermaid
    assert validate_mermaid(out) is False


def test_page_gating():
    assert page_likely_has_diagram("Figure 1: software architecture with arrows A->B and components") is True
    assert page_likely_has_diagram("x" * 500) is False  # long prose, no diagram hints
    assert page_likely_has_diagram("") is False
    assert page_likely_has_diagram("tiny", has_vector_drawings=True) is True


def test_render_page_image_graceful_without_backend(tmp_path):
    # nonexistent file and missing pymupdf must return None, never raise
    assert render_page_image(str(tmp_path / "missing.pdf"), 0) is None
