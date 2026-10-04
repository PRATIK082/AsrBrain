"""Provider-neutral interfaces + task routing + privacy (spec §6). Bridges existing ProviderSpec."""
from __future__ import annotations
from typing import Protocol, Literal

Task = Literal["text_answer", "requirement_extraction", "table_interpretation",
               "diagram_analysis", "entity_extraction", "relationship_extraction",
               "answer_verification"]
Privacy = Literal["local_only", "cloud_allowed", "cloud_for_non-source-query_only",
                  "never_send_document_images"]

STRICT_SYSTEM = (
    "You are an AUTOSAR technical assistant.\n\n"
    "Use only the supplied evidence.\n"
    "Do not rely on general memory when evidence is missing.\n"
    "Do not mix AUTOSAR releases.\n"
    "Do not mix Classic and Adaptive platforms.\n"
    "Do not convert inferred graph relationships into normative requirements.\n"
    "Preserve shall, shall not, should, may, and optional behavior.\n"
    "Every technical claim must include an evidence citation.\n"
    "If evidence is insufficient, say so and abstain.\n"
    "For comparisons, cite each release independently.\n"
    "For tables, preserve exact parameter names and values.\n"
    "For diagrams, distinguish source-visible facts from model-generated interpretation.")


class GenerationProvider(Protocol):
    async def generate(self, messages: list[dict], **kwargs) -> str: ...


class VisionProvider(Protocol):
    async def generate_with_images(self, messages: list[dict], images: list[str], **kwargs) -> str: ...


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


TASK_PREFERENCE: dict[str, str] = {
    "text_answer": "any", "requirement_extraction": "local",
    "table_interpretation": "local", "diagram_analysis": "local-vision",
    "entity_extraction": "local", "relationship_extraction": "local",
    "answer_verification": "local",
}


def check_privacy(policy: Privacy, provider_kind: str, sends_source: bool,
                  sends_images: bool) -> None:
    """Raise if policy forbids this call. Never send source content/images to cloud when forbidden."""
    is_cloud = provider_kind != "ollama"
    if policy == "local_only" and is_cloud:
        raise PermissionError("local_only: cloud provider blocked")
    if policy == "never_send_document_images" and sends_images and is_cloud:
        raise PermissionError("never_send_document_images: image upload to cloud blocked")
    if policy == "cloud_for_non-source-query_only" and sends_source and is_cloud:
        raise PermissionError("cloud_for_non-source-query_only: source content stays local")


def route_task(task: Task, policy: Privacy, ollama_model: str = "",
               cloud_model: str = "") -> dict:
    """Decide provider kind without executing; caller bridges to providers.complete/stream."""
    pref = TASK_PREFERENCE.get(task, "any")
    if policy in ("local_only", "never_send_document_images") or pref.startswith("local"):
        return {"kind": "ollama", "model": ollama_model, "task": task}
    if policy == "cloud_allowed":
        return {"kind": "openai_compat" if cloud_model else "ollama",
                "model": cloud_model or ollama_model, "task": task}
    return {"kind": "ollama", "model": ollama_model, "task": task}


def to_messages(prompt: str) -> list[dict]:
    return [{"role": "system", "content": STRICT_SYSTEM}, {"role": "user", "content": prompt}]
