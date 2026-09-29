from src.generation.providers import ProviderSpec, complete


def test_unreachable_provider_fails_fast_to_fallback():
    draft, note = complete("hi", ProviderSpec(kind="ollama", model="none", base_url="http://127.0.0.1:1", timeout_s=5))
    assert draft == "" and note


def test_cloud_without_key_returns_note_not_crash():
    draft, note = complete("hi", ProviderSpec(kind="openai_compat", model="x", base_url="http://127.0.0.1:1", timeout_s=5))
    assert draft == "" and note
