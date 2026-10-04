"""Independent modality processors (spec §5). Operate on CanonicalContent; preserve raw source."""
from __future__ import annotations
import re
from ..schema.canonical import CanonicalContent

NORM_RE = re.compile(r"[ \t]+")
HEADING_RE = re.compile(r"^(?:\d+(?:\.\d+)*)\s+\S+", re.M)
REQ_RE = re.compile(r"\b(?:SWS|RS|PRS)_[A-Za-z0-9_\-]+\b")
API_RE = re.compile(r"\b([A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+)\b")
MODAL_RE = re.compile(r"\b(shall not|shall|should|may)\b", re.I)


class TextProcessor:
    async def process(self, content: CanonicalContent) -> CanonicalContent:
        t = content.raw_text or ""
        t = NORM_RE.sub(" ", t).strip()
        content.raw_text = t  # normalized; normative words preserved (no paraphrase)
        struct = dict(content.structured_data or {})
        struct["has_heading"] = bool(HEADING_RE.search(t))
        struct["references"] = sorted(set(REQ_RE.findall(t)))[:20]
        struct["apis"] = sorted(set(API_RE.findall(t)))[:20]
        content.structured_data = struct
        return content


class RequirementProcessor:
    async def process(self, content: CanonicalContent) -> CanonicalContent:
        t = content.raw_text or ""
        ids = sorted(set(REQ_RE.findall(t)))
        if ids and content.content_type == "text":
            content.content_type = "requirement"
        content.requirement_ids = sorted(set(content.requirement_ids) | set(ids))
        modals = [m.lower() for m in MODAL_RE.findall(t)]
        struct = dict(content.structured_data or {})
        struct["modals"] = modals
        struct["has_condition"] = bool(re.search(r"\b(if|when|unless|except)\b", t, re.I))
        content.structured_data = struct
        return content


class TableProcessor:
    async def process(self, content: CanonicalContent) -> CanonicalContent:
        rows = (content.structured_data or {}).get("rows", []) if content.structured_data else []
        if content.content_type != "table" or not rows:
            return content
        # markdown + html + json preserved; never summarize away original
        md = content.table_markdown or "\n".join("| " + " | ".join(r) + " |" for r in rows[:100])
        html = "<table>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows[:100]) + "</table>"
        content.table_markdown = md
        content.table_html = html
        struct = dict(content.structured_data or {})
        struct["headers"] = rows[0] if rows else []
        struct["row_count"] = len(rows)
        struct["params"] = [c for r in rows for c in r if re.match(r"^[A-Za-z][A-Za-z0-9_]*$", (c or "").strip())][:30]
        struct["spans_pages"] = False  # set by merger when captions continue
        content.structured_data = struct
        if struct["row_count"] == 0:
            content.requires_review = True
        return content


class ImageProcessor:
    async def process(self, content: CanonicalContent) -> CanonicalContent:
        if content.content_type not in ("image", "diagram", "equation"):
            return content
        struct = dict(content.structured_data or {})
        struct["original_preserved"] = bool(content.image_path or content.caption or content.raw_text)
        struct["entities"] = sorted(set(API_RE.findall((content.caption or "") + (content.ocr_text or ""))))[:20]
        content.structured_data = struct
        return content  # VLM description filled by routing layer; always supplementary


class DiagramProcessor:
    async def process(self, content: CanonicalContent) -> CanonicalContent:
        if content.content_type != "diagram":
            return content
        cap = (content.caption or "").lower()
        decorative = any(w in cap for w in ("logo", "cover", "decorat", "background"))
        struct = dict(content.structured_data or {})
        struct["likely_diagram"] = not decorative
        struct["is_decorative"] = decorative
        struct["uncertain_relationships"] = True  # inferred edges must stay uncertain
        content.structured_data = struct
        if decorative:
            content.quality_score = min(content.quality_score, 0.3)
        return content


class EquationProcessor:
    async def process(self, content: CanonicalContent) -> CanonicalContent:
        if content.content_type != "equation":
            return content
        struct = dict(content.structured_data or {})
        struct["latex_preserved"] = bool(content.equation_latex)
        struct["image_preserved"] = bool(content.image_path)
        content.structured_data = struct
        return content
