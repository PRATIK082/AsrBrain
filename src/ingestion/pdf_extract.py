"""Staged PDF ingestion pipeline (spec §4). PyMuPDF preferred, pypdf fallback, OCR flagged not silent."""
from __future__ import annotations
import hashlib
import os
import re
from dataclasses import dataclass

from .metadata import detect_release_platform


@dataclass
class PageText:
    index: int          # 0-based pdf page index
    text: str
    char_count: int


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def discover_pdfs(root: str) -> list[str]:
    out = []
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if fn.lower().endswith(".pdf"):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def extract_pages(path: str) -> tuple[list[PageText], dict]:
    """Try PyMuPDF, else pypdf. Returns pages + extractor report."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        pages = [PageText(i, (p.get_text() or ""), 0) for i, p in enumerate(doc)]
        for pg in pages:
            pg.char_count = len(pg.text)
        return pages, {"extractor": "pymupdf", "page_count": len(pages)}
    except Exception:
        pass
    from pypdf import PdfReader
    reader = PdfReader(path)
    pages = []
    for i, p in enumerate(reader.pages):
        try:
            t = p.extract_text() or ""
        except Exception:
            t = ""
        pages.append(PageText(i, t, len(t)))
    return pages, {"extractor": "pypdf-fallback", "page_count": len(pages)}


HEADER_FOOTER_PATTERNS = [
    re.compile(r"AUTOSAR\s+.*(?:Release|Specification).*", re.I),
    re.compile(r"Page\s+\d+\s+of\s+\d+", re.I),
    re.compile(r"Document\s+(ID|Status|Title).*", re.I),
]


def normalize_page_text(t: str) -> str:
    lines = []
    for ln in t.splitlines():
        s = ln.strip()
        if not s:
            continue
        if any(p.search(s) for p in HEADER_FOOTER_PATTERNS) and len(s) < 120:
            continue
        lines.append(ln)
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


REQ_PATTERNS = [
    re.compile(r"\b((?:SWS|RS|PRS)_[A-Za-z0-9_]+)"),
    re.compile(r"\[(PRS_[A-Za-z0-9_\-]+)\]"),
]
API_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:_[A-Z][A-Za-z0-9_]*)+)\b")
HEADING_PATTERN = re.compile(r"^(\d+(?:\.\d+){0,3})\s+(.{3,120})$", re.M)
ECUC_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9]*[Cc]fg|[A-Z][A-Za-z0-9]*Config[A-Za-z0-9]*)\b")


def extract_signals(text: str) -> dict:
    req_ids: list[str] = []
    for p in REQ_PATTERNS:
        req_ids.extend(p.findall(text))
    # flatten tuple matches from second pattern
    flat: list[str] = []
    for r in req_ids:
        flat.append(r[0] if isinstance(r, tuple) else r)
    apis = sorted(set(API_PATTERN.findall(text)))
    # keep only plausible API tokens (contain underscore, CamelCase-ish)
    apis = [a for a in apis if "_" in a and len(a) <= 64][:50]
    headings = [(m.group(1), m.group(2).strip()) for m in HEADING_PATTERN.finditer(text)]
    ecuc = sorted(set(ECUC_PATTERN.findall(text)))[:50]
    return {"requirement_ids": sorted(set(flat))[:100], "api_names": apis,
            "headings": headings[:200], "ecu_parameters": ecuc}


def quality_report(source_pdf: str, sha: str, pages: list[PageText], signals: dict) -> dict:
    low = [p.index for p in pages if p.char_count < 200]
    return {"source_pdf": source_pdf, "sha256": sha, "page_count": len(pages),
            "pages_with_low_text": low, "pages_requiring_ocr": low,
            "tables_detected": 0, "requirements_detected": len(signals["requirement_ids"]),
            "headings_detected": len(signals["headings"]), "duplicate_pages": [],
            "extraction_warnings": ["table-extraction-stub" ] if True else [],
            "quality_score": round(1.0 - len(low) / max(1, len(pages)), 4)}
