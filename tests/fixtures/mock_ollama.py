"""Deterministic Ollama mock for tests."""
from __future__ import annotations


class MockOllama:
    response = "Mock answer [E1]."

    @classmethod
    def generate(cls, query: str, evidence: list[dict], comparison: bool = False) -> dict:
        return {"draft": cls.response, "llm": "mock"}
