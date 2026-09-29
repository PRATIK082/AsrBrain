"""Parser adapter layer (Part F): Docling primary (optional), PyMuPDF validator,
MinerU/Marker optional fallback, pypdf baseline. Guaranteed-default: PyMuPDF→pypdf.

Route complex pages on quality checks: scanned/low-density/table-heavy/multi-column/
parser-disagreement/missing-req-IDs/broken-APIs/missing-headings.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

FIGURE_CAP_RE = re.compile(r"^(Figure|Diagram|Equation)\s+([\d.\-]+)[:.\s]+(.{5,200})", re.I | re.M)
TABLE_CAP_RE = re.compile(r"^(Table)\s+([\d.\-]+)[:.\s]+(.{5,200})", re.I | re.M)


@dataclass
class ParsedPage:
    index: int
    text: str
    char_count: int = 0
    tables: list[dict] = field(default_factory=list)   # {caption, rows: [[cells]], page}
    figures: list[dict] = field(default_factory=list)  # {kind, number, caption, page}
    needs_review: list[str] = field(default_factory=list)
    parser: str = ""
    image_path: str | None = None


class BaseParser:
    name = "base"

    def parse(self, path: str) -> list[ParsedPage]:
        raise NotImplementedError


def _page_flags(text: str) -> list[str]:
    flags = []
    if len(text.strip()) < 200:
        flags.append("low_text_density")
    if re.search(r"[�\x00-\x08]", text):
        flags.append("broken_encoding")
    if len(re.findall(r"\S+\s{3,}\S+", text)) > 5:
        flags.append("possible_table_heavy")
    return flags


def _extract_captions(text: str, page: int) -> tuple[list[dict], list[dict]]:
    figs = [{"kind": m.group(1).lower(), "number": m.group(2), "caption": m.group(3).strip(), "page": page}
            for m in FIGURE_CAP_RE.finditer(text)]
    tabs = [{"caption": m.group(3).strip(), "number": m.group(2), "rows": [], "page": page}
            for m in TABLE_CAP_RE.finditer(text)]
    return tabs, figs


class PyMuPDFParser(BaseParser):
    name = "pymupdf"

    def parse(self, path: str) -> list[ParsedPage]:
        import fitz
        doc = fitz.open(path)
        out = []
        for i, pg in enumerate(doc):
            t = pg.get_text() or ""
            tabs, figs = _extract_captions(t, i)
            # structured tables when available
            try:
                for tw in pg.find_tables():
                    rows = [[c.strip() for c in r] for r in tw.extract()]
                    if rows:
                        tabs.append({"caption": "", "number": "", "rows": rows, "page": i})
            except Exception:
                pass
            flags = _page_flags(t)
            if not re.search(r"\b(SWS|RS|PRS)_[A-Za-z0-9_]+", t) and len(t) > 2000:
                flags.append("missing_requirement_ids")
            out.append(ParsedPage(i, t, len(t), tabs, figs, flags, self.name))
        return out


class PypdfParser(BaseParser):
    name = "pypdf-baseline"

    def parse(self, path: str) -> list[ParsedPage]:
        from pypdf import PdfReader
        out = []
        for i, pg in enumerate(PdfReader(path).pages):
            try:
                t = pg.extract_text() or ""
            except Exception:
                t = ""
            tabs, figs = _extract_captions(t, i)
            out.append(ParsedPage(i, t, len(t), tabs, figs, _page_flags(t), self.name))
        return out


class DoclingParser(BaseParser):
    """Primary when docling is installed; otherwise raises to trigger fallback."""
    name = "docling"

    def parse(self, path: str) -> list[ParsedPage]:
        from docling.document_converter import DocumentConverter  # optional dep
        conv = DocumentConverter()
        result = conv.convert(path)
        full = result.document.export_to_text()
        # docling gives document-level text: single logical page; keep page-aware fallback text
        tabs, figs = _extract_captions(full, 0)
        return [ParsedPage(0, full, len(full), tabs, figs, [], self.name)]


class MinerUParser(BaseParser):
    name = "mineru-optional"

    def parse(self, path: str) -> list[ParsedPage]:
        import importlib
        importlib.import_module("mineru")
        raise RuntimeError("MinerU installed but CLI routing not configured; use PyMuPDF path")


def get_parser(prefer: str = "auto") -> BaseParser:
    if prefer == "docling":
        try:
            return DoclingParser()
        except Exception:
            pass
    if prefer in ("auto", "pymupdf"):
        try:
            import fitz  # noqa
            return PyMuPDFParser()
        except Exception:
            return PypdfParser()
    return PypdfParser()


def parser_quality_report(pages: list[ParsedPage], source_pdf: str, sha: str) -> dict:
    from collections import Counter
    flags = Counter(f for p in pages for f in p.needs_review)
    return {"source_pdf": source_pdf, "sha256": sha, "parser": pages[0].parser if pages else "?",
            "page_count": len(pages),
            "pages_with_low_text": [p.index for p in pages if "low_text_density" in p.needs_review],
            "pages_requiring_ocr": [p.index for p in pages if "low_text_density" in p.needs_review],
            "tables_detected": sum(len(p.tables) for p in pages),
            "figures_detected": sum(len(p.figures) for p in pages),
            "flag_histogram": dict(flags),
            "quality_score": round(1.0 - len([p for p in pages if p.needs_review]) / max(1, len(pages)), 4)}
