"""Tool layer: callable surface shared by the REST API, the agent loop and the LLM
tool-calling bridge."""
from .base import REGISTRY, ToolRegistry, ToolResult, ToolSpec
from .registry import build_registry, install

__all__ = ["REGISTRY", "ToolRegistry", "ToolResult", "ToolSpec",
           "build_registry", "install"]
