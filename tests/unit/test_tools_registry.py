"""Unit tests for the tool framework and the global tool registry."""
from __future__ import annotations

import pytest

from src.tools.base import ToolRegistry, ToolResult, ToolSpec
from src.tools.registry import build_registry, install


def test_registry_decorator_registers_and_invokes():
    reg = ToolRegistry()

    @reg.tool("demo.echo", "Echo the message", {"type": "object", "properties": {"msg": {"type": "string"}}},
              tags=["demo"])
    def echo(msg: str = "") -> dict:
        return {"msg": msg}

    assert reg.names() == ["demo.echo"]
    result = reg.invoke("demo.echo", {"msg": "hi"})
    assert isinstance(result, ToolResult)
    assert result.ok is True
    assert result.data == {"msg": "hi"}
    assert result.duration_ms >= 0


def test_registry_rejects_duplicate_names():
    reg = ToolRegistry()
    reg.register(ToolSpec(name="a.b", description="", parameters={}, fn=lambda: {}))
    with pytest.raises(ValueError):
        reg.register(ToolSpec(name="a.b", description="", parameters={}, fn=lambda: {}))


def test_registry_invoke_unknown_tool_is_an_error_result():
    reg = ToolRegistry()
    result = reg.invoke("nope", {})
    assert result.ok is False
    assert "unknown tool" in result.error


def test_registry_invoke_bad_arguments_is_an_error_result():
    reg = ToolRegistry()
    reg.register(ToolSpec(name="x.y", description="", parameters={}, fn=lambda a: {"a": a}))
    result = reg.invoke("x.y", {"wrong": 1})
    assert result.ok is False
    assert "invalid arguments" in result.error


def test_registry_invoke_tool_exception_does_not_raise():
    reg = ToolRegistry()

    def boom() -> dict:
        raise RuntimeError("kaboom")

    reg.register(ToolSpec(name="x.boom", description="", parameters={}, fn=boom))
    result = reg.invoke("x.boom", {})
    assert result.ok is False
    assert "kaboom" in result.error


def test_tool_spec_json_schema_is_openai_compatible():
    spec = ToolSpec(name="a.b", description="d", parameters={"type": "object"}, fn=lambda: {})
    schema = spec.json_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "a.b"
    assert schema["function"]["parameters"]["type"] == "object"


def test_build_registry_exposes_every_tool_family():
    reg = build_registry()
    names = set(reg.names())
    for expected in ("graph.search", "graph.neighbors", "graph.path", "graph.communities",
                     "graph.community", "graph.stats", "graph.build", "mindmap.build",
                     "arxml.artifacts", "arxml.topology", "arxml.neighbors", "arxml.search",
                     "arxml.config", "code.symbols", "code.callgraph", "code.rte_map",
                     "code.analyze", "trace.links", "trace.requirements", "trace.tests",
                     "trace.matrix", "trace.gaps"):
        assert expected in names


def test_only_graph_build_is_mutating():
    reg = build_registry()
    mutating = {s.name for s in reg.specs() if s.mutating}
    assert mutating == {"graph.build"}


def test_registry_schemas_are_valid_json_schema_objects():
    reg = build_registry()
    for schema in reg.schemas():
        assert schema["type"] == "function"
        fn = schema["function"]
        assert fn["name"]
        assert fn["description"]
        assert fn["parameters"]["type"] == "object"


def test_install_is_idempotent():
    from src.tools.base import REGISTRY
    install()
    before = len(REGISTRY.names())
    install()
    install()
    assert len(REGISTRY.names()) == before
    assert before > 0


def test_select_by_tag():
    reg = build_registry()
    graph_tools = reg.select(tags=["graph"])
    assert graph_tools
    assert all("graph" in t.tags for t in graph_tools)
