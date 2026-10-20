"""Tool framework: the callable surface shared by the agent loop, the REST API and
the LLM tool-calling bridge.

A tool is a plain function plus a JSON-Schema description.  Tools never mutate the
corpus except when explicitly declared `mutating=True` (only `graph.build` is).

The registry is the single place that knows which tools exist, so the API listing and
the agent planner can never drift apart.
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

ToolFn = Callable[..., Any]


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    fn: ToolFn
    tags: list[str] = field(default_factory=list)
    mutating: bool = False

    def json_schema(self) -> dict:
        """OpenAI-compatible function-tool schema."""
        return {"type": "function",
                "function": {"name": self.name, "description": self.description,
                             "parameters": self.parameters or {"type": "object", "properties": {}}}}


@dataclass
class ToolResult:
    tool: str
    ok: bool
    data: dict = field(default_factory=dict)
    error: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {"tool": self.tool, "ok": self.ok, "data": self.data,
                "error": self.error, "duration_ms": self.duration_ms}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    # ------------------------------------------------------------- registration
    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = spec
        return spec

    def tool(self, name: str, description: str, parameters: dict | None = None,
             tags: list[str] | None = None, mutating: bool = False):
        """Decorator form: ``@registry.tool("graph.search", "...")``."""
        def deco(fn: ToolFn) -> ToolFn:
            self.register(ToolSpec(name=name, description=description,
                                   parameters=parameters or _default_schema(),
                                   fn=fn, tags=list(tags or []), mutating=mutating))
            return fn
        return deco

    # ------------------------------------------------------------------ access
    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [self._tools[n] for n in sorted(self._tools)]

    def list(self) -> list[dict]:
        return [{"name": t.name, "description": t.description, "parameters": t.parameters,
                 "tags": t.tags, "mutating": t.mutating}
                for t in sorted(self._tools.values(), key=lambda x: x.name)]

    def schemas(self) -> list[dict]:
        return [t.json_schema() for t in sorted(self._tools.values(), key=lambda x: x.name)]

    def select(self, names: list[str] | None = None, tags: list[str] | None = None) -> list[ToolSpec]:
        out = list(self._tools.values())
        if names:
            wanted = set(names)
            out = [t for t in out if t.name in wanted]
        if tags:
            wanted_tags = set(tags)
            out = [t for t in out if wanted_tags & set(t.tags)]
        return sorted(out, key=lambda x: x.name)

    # ------------------------------------------------------------------ invoke
    def invoke(self, name: str, args: dict | None = None) -> ToolResult:
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(tool=name, ok=False, error=f"unknown tool: {name}")
        started = time.perf_counter()
        try:
            data = spec.fn(**(args or {}))
        except TypeError as e:
            return ToolResult(tool=name, ok=False, error=f"invalid arguments: {e}")
        except Exception as e:  # tool failures must never kill the agent loop
            return ToolResult(tool=name, ok=False, error=f"{type(e).__name__}: {e}",
                              duration_ms=int((time.perf_counter() - started) * 1000),
                              data={"traceback": traceback.format_exc(limit=3)})
        if not isinstance(data, dict):
            data = {"result": data}
        return ToolResult(tool=name, ok=True, data=data,
                          duration_ms=int((time.perf_counter() - started) * 1000))


def _default_schema() -> dict:
    return {"type": "object", "properties": {}, "required": []}


#: global registry - populated by `src.tools.registry.build_registry`
REGISTRY = ToolRegistry()


def tool_context() -> dict:
    """Runtime context injected into tools (graph db path, canonical db path...)."""
    from ..config.settings import settings
    return {"canonical_db": settings.canonical_db, "graph_db": settings.graph_db}
