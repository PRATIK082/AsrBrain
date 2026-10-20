"""Command line access to the tool registry and the agent workflows.

    python -m src.tools.cli list
    python -m src.tools.cli call graph.stats
    python -m src.tools.cli call graph.search query="CanIf init" mode=local
    python -m src.tools.cli mindmap CanIf --source graph --depth 2
    python -m src.tools.cli agent "trace SWS_CanIf_00123" --workflow auto
    python -m src.tools.cli workflows

Everything here is a thin wrapper around the same registry the API and the agent use,
so a CLI result and an API result never drift apart.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .base import REGISTRY
from .registry import install


def _parse_value(raw: str) -> Any:
    """Parse a CLI argument value as JSON, falling back to the raw string."""
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def _parse_args(pairs: list[str]) -> dict:
    out: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"invalid argument '{pair}' (expected key=value)")
        key, _, value = pair.partition("=")
        out[key.strip()] = _parse_value(value)
    return out


def _provider_spec(provider: str, model: str, base_url: str, api_key: str):
    if provider == "none":
        return None
    from ..config.settings import settings
    from ..generation.providers import ProviderSpec
    if provider == "openai_compat":
        return ProviderSpec(kind="openai_compat", model=model or "gpt-4o-mini",
                            base_url=base_url or "https://api.openai.com/v1",
                            api_key=api_key, timeout_s=settings.ollama_timeout_s)
    from ..generation.answer import pick_model
    return ProviderSpec(kind="ollama", model=model or pick_model(),
                        base_url=base_url or settings.ollama_base_url,
                        timeout_s=settings.ollama_timeout_s)


def _cmd_list(args: argparse.Namespace) -> int:
    reg = install()
    for spec in reg.specs():
        flags = " [mutating]" if spec.mutating else ""
        print(f"{spec.name}{flags}\n    {spec.description}")
    print(f"\n{len(reg.names())} tools")
    return 0


def _cmd_call(args: argparse.Namespace) -> int:
    install()
    result = REGISTRY.invoke(args.name, _parse_args(args.arg or []))
    print(json.dumps(result.to_dict(), indent=2, default=str))
    return 0 if result.ok else 1


def _cmd_mindmap(args: argparse.Namespace) -> int:
    install()
    result = REGISTRY.invoke("mindmap.build", {
        "topic": args.topic, "source": args.source, "depth": args.depth,
        "outline": json.loads(args.outline) if args.outline else None,
    })
    if not result.ok:
        print(result.error, file=sys.stderr)
        return 1
    data = result.data or {}
    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(data.get("mermaid", ""))
    return 0


def _cmd_workflows(args: argparse.Namespace) -> int:
    from ..agents.runner import list_workflow_catalogue
    for wf in list_workflow_catalogue():
        print(f"{wf['name']}  (intent: {wf.get('intent', '')})\n    {wf.get('description', '')}")
    return 0


def _cmd_agent(args: argparse.Namespace) -> int:
    from ..agents.runner import run_auto, run_generic, run_workflow
    install()
    spec = _provider_spec(args.provider, args.model, args.base_url, args.api_key)
    if args.workflow == "auto":
        events = run_auto(args.query, spec=spec, allow_mutating=args.allow_mutating)
    elif args.workflow == "freeform":
        events = run_generic(args.query, spec=spec, allow_mutating=args.allow_mutating)
    else:
        events = run_workflow(args.workflow, args.query, spec=spec,
                              allow_mutating=args.allow_mutating)
    answer = ""
    for event in events:
        kind = event.get("event")
        if kind == "error":
            print(event.get("error", "unknown error"), file=sys.stderr)
            return 1
        if kind == "tool_call":
            print(f"-> {event.get('tool')} {json.dumps(event.get('args', {}), default=str)}")
        elif kind == "tool_result":
            print(f"<- {event.get('tool')}: {event.get('summary', '')}")
        elif kind == "tool_skipped":
            print(f"!! {event.get('tool')}: {event.get('reason', '')}")
        elif kind == "complete":
            answer = event.get("answer", "")
    print("\n" + answer)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.tools.cli",
                                 description="Tool registry and agent workflow CLI")
    sub = ap.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list every registered tool")
    p_list.set_defaults(func=_cmd_list)

    p_call = sub.add_parser("call", help="invoke one tool with key=value arguments")
    p_call.add_argument("name")
    p_call.add_argument("arg", nargs="*")
    p_call.set_defaults(func=_cmd_call)

    p_map = sub.add_parser("mindmap", help="render a Mermaid mindmap for a topic")
    p_map.add_argument("topic")
    p_map.add_argument("--source", default="auto",
                       choices=["auto", "graph", "evidence", "outline"])
    p_map.add_argument("--depth", type=int, default=2)
    p_map.add_argument("--outline", default="", help="JSON outline for --source outline")
    p_map.add_argument("--json", action="store_true")
    p_map.set_defaults(func=_cmd_mindmap)

    p_wf = sub.add_parser("workflows", help="list the agent workflows")
    p_wf.set_defaults(func=_cmd_workflows)

    p_agent = sub.add_parser("agent", help="run an agent workflow")
    p_agent.add_argument("query")
    p_agent.add_argument("--workflow", default="auto",
                         help="workflow name, 'auto' or 'freeform'")
    p_agent.add_argument("--provider", default="ollama",
                         choices=["ollama", "openai_compat", "none"])
    p_agent.add_argument("--model", default="")
    p_agent.add_argument("--base-url", dest="base_url", default="")
    p_agent.add_argument("--api-key", dest="api_key", default="")
    p_agent.add_argument("--allow-mutating", dest="allow_mutating", action="store_true")
    p_agent.set_defaults(func=_cmd_agent)

    args = ap.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
