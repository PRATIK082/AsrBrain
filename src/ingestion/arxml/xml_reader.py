"""Line-aware XML reader for ARXML.

`xml.etree.ElementTree` discards source positions, so a citation could only ever
say "somewhere in this file". This reader keeps the **line range** of every
element, which is what turns an ARXML fact into an addressable piece of
evidence (ADR-0005).

The reader is deliberately small and dependency-free:

* it does **not** resolve external entities (no DTD loading, no network);
* it keeps the raw prefixed tag names, so the AUTOSAR namespace URI is read
  from the root's ``xmlns`` attribute rather than from expanded tags;
* it reports the line where an element starts and where it ends.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import xml.parsers.expat

__all__ = ["XmlDocument", "XmlError", "parse_xml"]


class XmlError(ValueError):
    """Raised when the document is not well-formed XML."""


class XmlDocument:
    """A parsed document plus the positions of its elements."""

    def __init__(self, root: ET.Element, line_start: int, line_end: int):
        self.root = root
        self.line_start = line_start
        self.line_end = line_end

    @property
    def namespace(self) -> str:
        """The default namespace URI declared on the root element."""
        if "xmlns" in self.root.attrib:
            return str(self.root.attrib["xmlns"])
        for key, value in self.root.attrib.items():
            if key == "xmlns" or key.startswith("xmlns:"):
                if key == "xmlns":
                    return str(value)
        return ""

    @property
    def schema_version(self) -> str:
        """The schema version the document declares, if any."""
        for key, value in self.root.attrib.items():
            if key.upper() == "SCHEMA-VERSION":
                return str(value)
        return ""


class _Element(ET.Element):
    """An element that can carry its source position.

    The C implementation of ``Element`` has no ``__dict__``; the Python
    subclass adds one, which is where the line range is stored.
    """


class _Builder:
    """Builds an ElementTree while recording the line range of every element."""

    def __init__(self) -> None:
        self.root: ET.Element | None = None
        self.stack: list[ET.Element] = []
        self.line_start = 0
        self.line_end = 0

    def start(self, name: str, attrs: dict) -> None:
        element = _Element(name, {str(k): str(v) for k, v in attrs.items()})
        element._line_start = self._line
        element._line_end = self._line
        if self.stack:
            self.stack[-1].append(element)
        else:
            self.root = element
            self.line_start = self._line
        self.stack.append(element)

    def end(self, name: str) -> None:
        if not self.stack:
            return
        element = self.stack.pop()
        element._line_end = self._line
        if not self.stack:
            self.line_end = self._line

    def chars(self, data: str) -> None:
        if not self.stack:
            return
        element = self.stack[-1]
        element.text = (element.text or "") + data

    _line = 0


def parse_xml(raw: bytes) -> XmlDocument:
    """Parse XML into a tree that remembers where every element came from."""
    builder = _Builder()
    parser = xml.parsers.expat.ParserCreate()
    parser.buffer_text = True

    def start(name: str, attrs: dict) -> None:
        builder._line = parser.CurrentLineNumber
        builder.start(name, attrs)

    def end(name: str) -> None:
        builder._line = parser.CurrentLineNumber
        builder.end(name)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = builder.chars
    try:
        parser.Parse(raw, True)
    except xml.parsers.expat.ExpatError as exc:
        raise XmlError(f"malformed XML: {exc}") from exc
    if builder.root is None:
        raise XmlError("document has no root element")
    return XmlDocument(builder.root, builder.line_start, builder.line_end)


def line_of(element: ET.Element) -> int:
    """The line where an element starts (0 when unknown)."""
    return int(getattr(element, "_line_start", 0) or 0)


def line_end_of(element: ET.Element) -> int:
    """The line where an element ends (0 when unknown)."""
    return int(getattr(element, "_line_end", 0) or 0)
