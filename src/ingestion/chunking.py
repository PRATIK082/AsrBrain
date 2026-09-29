"""AUTOSAR-aware hierarchical chunking (spec §5): atomic + context + parent."""
from __future__ import annotations
import hashlib
import re
from ..schema.documents import Chunk

ATOMIC_TARGET_WORDS = 220
CONTEXT_TARGET_WORDS = 600


def _stable_id(*parts: str) -> str:
    return "chunk-" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


def split_paragraphs(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return paras


def build_chunks(document_id: str, source_pdf: str, sha: str, release: str, platform: str,
                 module: str, doctype: str, pages, base_meta: dict | None = None) -> list[Chunk]:
    """pages: list of PageText (already normalised). Emits atomic chunks with page ranges,
    then derives context chunks by merging adjacent atomics within the same page window."""
    from .pdf_extract import extract_signals
    atomics: list[Chunk] = []
    for pg in pages:
        for pi, para in enumerate(split_paragraphs(pg.text)):
            if len(para) < 40:
                continue
            sig = extract_signals(para)
            words = para.split()
            # split very long paragraphs into atomic windows
            for w in range(0, len(words), ATOMIC_TARGET_WORDS):
                window = " ".join(words[w:w + ATOMIC_TARGET_WORDS])
                if len(window) < 40:
                    continue
                cid = _stable_id(document_id, str(pg.index), str(pi), str(w))
                atomics.append(Chunk(
                    chunk_id=cid, document_id=document_id, source_pdf=source_pdf,
                    source_sha256=sha, page_start=pg.index + 1, page_end=pg.index + 1,
                    pdf_page_index=pg.index, autosar_release=release, platform=platform,
                    module=module, document_type=doctype,
                    section_number=sig["headings"][0][0] if sig["headings"] else "",
                    section_title=sig["headings"][0][1] if sig["headings"] else "",
                    requirement_ids=sig["requirement_ids"][:10], api_names=sig["api_names"][:10],
                    ecu_parameters=sig["ecu_parameters"][:10],
                    text=window, normalized_text=re.sub(r"\s+", " ", window).strip(),
                    chunk_kind="atomic"))
    # context chunks: merge up to CONTEXT_TARGET_WORDS of consecutive atomics on same/adjacent pages
    contexts: list[Chunk] = []
    buf: list[Chunk] = []
    buf_words = 0
    def flush(buf: list[Chunk]):
        if len(buf) < 2:
            return
        text = "\n\n".join(c.text for c in buf)
        cid = _stable_id(document_id, "ctx", buf[0].chunk_id, buf[-1].chunk_id)
        contexts.append(Chunk(
            chunk_id=cid, document_id=document_id, source_pdf=source_pdf, source_sha256=sha,
            page_start=buf[0].page_start, page_end=buf[-1].page_end,
            pdf_page_index=buf[0].pdf_page_index, autosar_release=release, platform=platform,
            module=module, document_type=doctype, section_number=buf[0].section_number,
            section_title=buf[0].section_title,
            requirement_ids=sorted({r for c in buf for r in c.requirement_ids})[:20],
            api_names=sorted({a for c in buf for a in c.api_names})[:20],
            text=text, normalized_text=re.sub(r"\s+", " ", text).strip(), chunk_kind="context"))
        for c in buf:
            c.parent_chunk_id = cid
    for c in atomics:
        buf.append(c)
        buf_words += len(c.text.split())
        if buf_words >= CONTEXT_TARGET_WORDS:
            flush(buf)
            buf, buf_words = [], 0
    flush(buf)
    return atomics + contexts
