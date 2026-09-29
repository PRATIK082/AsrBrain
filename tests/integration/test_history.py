"""History carryover + model persistence use real pipeline with mocked LLM."""
from src.indexing.hybrid import HybridIndex, load_chunks
from src.retrieval.pipeline import RetrievalPipeline
from src.config.settings import settings
import src.workflows.stages as stages


def test_history_reaches_retrieval():
    chunks = load_chunks(settings.canonical_db)
    pipe = RetrievalPipeline(HybridIndex.load("data/indexes/hybrid"), chunks)
    orig = stages._generate
    stages._generate = lambda q, e, comp, spec=None, intent="": {"draft": "ok [E1].", "llm": "mock"}
    try:
        hist = [{"role": "user", "content": "What is SOME/IP?"},
                {"role": "assistant", "content": "A protocol. [E1]"}]
        evs = list(stages.run_staged(pipe, "its message format?", None, {},
                                      {"skip_clarify": True}, top_k=6, history=hist))
    finally:
        stages._generate = orig
    assert evs[-1]["event"] == "complete"
    assert "context:" not in evs[-1]["answer"]
