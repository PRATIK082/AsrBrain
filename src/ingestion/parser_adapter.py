"""Async ParserAdapter protocol + routing (spec §4). Wraps existing sync parsers; additive."""
from __future__ import annotations
import asyncio
from typing import Protocol
from ..schema.canonical import CanonicalContent, make_content_id


class ParserAdapter(Protocol):
    name: str
    version: str

    async def inspect(self, path: str) -> dict: ...
    async def parse(self, path: str) -> list[CanonicalContent]: ...
    async def parse_pages(self, path: str, pages: list[int]) -> list[CanonicalContent]: ...


def route_parser(path: str, inspect_info: dict, prefer: str = "auto") -> str:
    """Routing by PDF type / scanned pages / table complexity / OCR need / quality / disagreement."""
    if prefer not in ("auto", ""):
        return prefer
    if inspect_info.get("scanned_pages"):
        return "pymupdf"  # OCR-capable path; docling/mineru only if installed
    if inspect_info.get("table_heavy"):
        return "pymupdf"
    if inspect_info.get("low_text_density"):
        return "pymupdf"
    return "auto"


class SyncParserAdapter:
    """Wrap a legacy sync BaseParser (parsers.py) into the async Protocol."""
    version = "1.0"

    def __init__(self, inner, document_id: str = "", source_sha256: str = ""):
        self._inner = inner
        self.name = getattr(inner, "name", "unknown")
        self._doc = document_id
        self._sha = source_sha256

    async def inspect(self, path: str) -> dict:
        def _run():
            try:
                pages = self._inner.parse(path)
            except Exception as e:
                return {"error": str(e)[:200], "page_count": 0}
            low = [p.index for p in pages if "low_text_density" in getattr(p, "needs_review", [])]
            tabs = sum(len(getattr(p, "tables", []) or []) for p in pages)
            return {"page_count": len(pages), "low_text_density": bool(low),
                    "scanned_pages": low, "table_heavy": tabs > 5,
                    "tables_detected": tabs,
                    "figures_detected": sum(len(getattr(p, "figures", []) or []) for p in pages)}
        return await asyncio.to_thread(_run)

    async def parse(self, path: str) -> list[CanonicalContent]:
        pages = await asyncio.to_thread(self._inner.parse, path)
        return self._to_canonical(path, pages)

    async def parse_pages(self, path: str, pages: list[int]) -> list[CanonicalContent]:
        all_items = await self.parse(path)
        wanted = set(pages)
        return [c for c in all_items if c.page_index in wanted]

    def _to_canonical(self, path: str, pages) -> list[CanonicalContent]:
        out: list[CanonicalContent] = []
        doc = self._doc or "doc-unknown"
        for p in pages:
            idx = getattr(p, "index", 0)
            text = getattr(p, "text", "") or ""
            out.append(CanonicalContent(
                content_id=make_content_id(doc, "text", idx, 0, text),
                document_id=doc, content_type="text", raw_text=text,
                source_pdf=path, source_sha256=self._sha, page_index=idx,
                parser_name=self.name, parser_version=self.version,
                quality_score=0.5 if getattr(p, "needs_review", None) else 1.0,
                requires_review=bool(getattr(p, "needs_review", None))))
            for t, tab in enumerate(getattr(p, "tables", []) or []):
                rows = tab.get("rows", []) or []
                md = "\n".join("| " + " | ".join(r) + " |" for r in rows[:50]) if rows else None
                out.append(CanonicalContent(
                    content_id=make_content_id(doc, "table", idx, t, str(rows)[:200]),
                    document_id=doc, content_type="table", raw_text=tab.get("caption"),
                    structured_data={"rows": rows},
                    source_pdf=path, source_sha256=self._sha, page_index=idx,
                    caption=tab.get("caption"), table_markdown=md,
                    parser_name=self.name, parser_version=self.version, quality_score=0.8))
            for f, fig in enumerate(getattr(p, "figures", []) or []):
                kind = (fig.get("kind") or "image").lower()
                ctype = kind if kind in ("diagram", "equation", "image") else "image"
                out.append(CanonicalContent(
                    content_id=make_content_id(doc, ctype, idx, f, fig.get("caption", "")),
                    document_id=doc, content_type=ctype,  # type: ignore[arg-type]
                    source_pdf=path, source_sha256=self._sha, page_index=idx,
                    caption=fig.get("caption"), parser_name=self.name,
                    parser_version=self.version, quality_score=0.7))
        return out


def get_async_adapter(prefer: str = "auto", document_id: str = "", sha: str = "") -> SyncParserAdapter:
    from .parsers import get_parser
    routed = prefer if prefer != "auto" else "auto"
    inner = get_parser("pymupdf" if routed == "auto" else routed)
    return SyncParserAdapter(inner, document_id, sha)
