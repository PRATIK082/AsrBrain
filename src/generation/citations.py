"""Render final citation block (spec §16)."""
from __future__ import annotations


def citation_block(evidence: list[dict]) -> str:
    lines = []
    for i, c in enumerate(evidence, start=1):
        # Phase 2: page numbers may be NULL (docling document-level text, code/config
        # chunks). Render "n/a" instead of "None-None" — a citation must never invent
        # a page that was never measured.
        ps, pe = c.get("page_start"), c.get("page_end")
        pages = f"{ps}-{pe}" if ps is not None and pe is not None else "n/a"
        lines.append(
            f"[E{i}] Source: {c.get('source_pdf')}\n"
            f"    Release: {c.get('platform','')} {c.get('autosar_release','')}\n"
            f"    Module: {c.get('module','')} | Type: {c.get('document_type','')}\n"
            f"    Section: {c.get('section_number','')} {c.get('section_title','')}\n"
            f"    Pages: {pages}\n"
            f"    Requirement: {', '.join(c.get('requirement_ids', [])[:3]) or '—'}\n"
            f"    Evidence ID: {c.get('chunk_id')}")
    return "\n".join(lines)
