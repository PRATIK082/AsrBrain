"""LLM provider abstraction (req. 4): local Ollama + any OpenAI-compatible cloud
(OpenAI GPT, Gemini OpenAI-compat endpoint, Opencode/Cloud, OpenRouter, self-hosted).

API keys are passed per-request from UI session state — never logged, never persisted.
Supports streaming (SSE-style token events) and non-streaming drafts.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Iterator
import httpx


@dataclass
class ProviderSpec:
    kind: str = "ollama"          # ollama | openai_compat
    model: str = ""
    base_url: str = "http://127.0.0.1:11434"
    api_key: str = ""             # session-only
    timeout_s: float = 120.0


def _redact(spec: ProviderSpec) -> str:
    return f"{spec.kind}:{spec.model}@{spec.base_url}"


def list_ollama_models(base_url: str = "http://127.0.0.1:11434") -> list[str]:
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=5.0)
        return [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        return []


def complete(prompt: str, spec: ProviderSpec) -> tuple[str, str]:
    """Returns (draft, note). Falls back to '' on any error (caller uses extractive fallback)."""
    from ..config.settings import settings as _s
    num_predict = _s.llm_num_predict
    try:
        if spec.kind == "ollama":
            r = httpx.post(f"{spec.base_url}/api/generate",
                           json={"model": spec.model, "prompt": prompt, "stream": False,
                                 "options": {"temperature": 0.2, "num_ctx": 8192, "top_p": 0.9,
                                             "num_predict": num_predict}},
                           timeout=spec.timeout_s)
            if r.status_code == 200:
                return r.json().get("response", ""), ""
            return "", f"ollama HTTP {r.status_code}"
        # OpenAI-compatible: POST {base}/chat/completions {model, messages}
        headers = {"Authorization": f"Bearer {spec.api_key}"} if spec.api_key else {}
        r = httpx.post(f"{spec.base_url.rstrip('/')}/chat/completions",
                       json={"model": spec.model,
                             "messages": [{"role": "system", "content": "You are an AUTOSAR specification assistant. Answer only from provided evidence with [E#] citations."},
                                          {"role": "user", "content": prompt}],
                             "temperature": 0.2, "max_tokens": num_predict},
                       headers=headers, timeout=spec.timeout_s)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"], ""
        return "", f"cloud HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return "", str(e)[:200]


def _normalize_tool_calls(raw_calls: list) -> list[dict]:
    """Normalize provider tool calls to ``[{name, arguments(dict)}, ...]``."""
    out: list[dict] = []
    for call in raw_calls or []:
        if not isinstance(call, dict):
            continue
        fn = call.get("function") or call
        name = fn.get("name") or ""
        if not name:
            continue
        args = fn.get("arguments", fn.get("parameters", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except Exception:
                args = {"_raw": args}
        if not isinstance(args, dict):
            args = {}
        out.append({"name": name, "arguments": args})
    return out


def chat_with_tools(messages: list[dict], tools: list[dict],
                     spec: ProviderSpec) -> dict:
    """Native tool-calling round trip.

    ``tools`` is a list of OpenAI-style function schemas.  Returns
    ``{"content": str, "tool_calls": [{"name", "arguments"}], "error": str}``.
    Never raises: a provider error is reported through the ``error`` key so the
    agent can fall back to its deterministic planner.
    """
    payload_messages = list(messages or [])
    payload_tools = list(tools or [])
    try:
        if spec.kind == "ollama":
            r = httpx.post(f"{spec.base_url.rstrip('/')}/api/chat",
                           json={"model": spec.model, "messages": payload_messages,
                                 "tools": payload_tools, "stream": False,
                                 "options": {"temperature": 0.1, "num_ctx": 8192}},
                           timeout=spec.timeout_s)
            if r.status_code != 200:
                return {"content": "", "tool_calls": [], "error": f"ollama HTTP {r.status_code}"}
            data = r.json()
            message = data.get("message", {}) or {}
            return {"content": message.get("content", "") or "",
                    "tool_calls": _normalize_tool_calls(message.get("tool_calls", [])),
                    "error": ""}
        headers = {"Authorization": f"Bearer {spec.api_key}"} if spec.api_key else {}
        r = httpx.post(f"{spec.base_url.rstrip('/')}/chat/completions",
                       json={"model": spec.model, "messages": payload_messages,
                             "tools": payload_tools, "temperature": 0.1},
                       headers=headers, timeout=spec.timeout_s)
        if r.status_code != 200:
            return {"content": "", "tool_calls": [],
                    "error": f"cloud HTTP {r.status_code}: {r.text[:200]}"}
        message = (r.json().get("choices", [{}])[0].get("message", {}) or {})
        return {"content": message.get("content", "") or "",
                "tool_calls": _normalize_tool_calls(message.get("tool_calls", [])),
                "error": ""}
    except Exception as e:
        return {"content": "", "tool_calls": [], "error": str(e)[:200]}


def stream(prompt: str, spec: ProviderSpec) -> Iterator[str]:
    """Yield token strings. Ollama: stream:true NDJSON; OpenAI-compat: SSE data: lines."""
    from ..config.settings import settings as _s
    num_predict = _s.llm_num_predict
    try:
        if spec.kind == "ollama":
            with httpx.stream("POST", f"{spec.base_url}/api/generate",
                              json={"model": spec.model, "prompt": prompt, "stream": True,
                                    "options": {"temperature": 0.2, "num_ctx": 8192,
                                                "num_predict": num_predict}},
                              timeout=spec.timeout_s) as r:
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        import json as _j
                        d = _j.loads(line)
                        t = d.get("response", "")
                        if t:
                            yield t
                        if d.get("done"):
                            break
                    except Exception:
                        continue
        else:
            headers = {"Authorization": f"Bearer {spec.api_key}"} if spec.api_key else {}
            with httpx.stream("POST", f"{spec.base_url.rstrip('/')}/chat/completions",
                              json={"model": spec.model,
                                    "messages": [{"role": "user", "content": prompt}],
                                    "temperature": 0.2, "stream": True},
                              headers=headers, timeout=spec.timeout_s) as r:
                for line in r.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        import json as _j
                        d = _j.loads(payload)
                        t = d["choices"][0]["delta"].get("content", "")
                        if t:
                            yield t
                    except Exception:
                        continue
    except Exception:
        return
