"""Query flywheel (Phase 4, slice 1): logging, outcomes, mining, drift gate."""
import importlib.util
import json
import os

import pytest

from src.chat import store as store_mod
from src.chat.store import ChatStore, classify_outcome
from src.evaluation.runner import run_evaluation
from src.evaluation.splits import apply_split, load_split, save_split, split_ids, verify_split


def _miner():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "scripts", "mine_queries.py")
    spec = importlib.util.spec_from_file_location("mine_queries", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_classify_outcome_covers_contract_outcomes():
    assert classify_outcome("", clarify=True) == "CLARIFY"
    assert classify_outcome("I could not verify this answer from the indexed AUTOSAR docs.") == "ABSTAIN"
    assert classify_outcome("cited answer", citation_coverage=0.5) == "PARTIAL"
    assert classify_outcome("cited answer", citation_coverage=1.0) == "ANSWERED"
    assert classify_outcome("plain answer") == "ANSWERED"


def test_log_query_roundtrip_and_joinable_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(store_mod, "QUERY_LOG_ENABLED", True)
    db = str(tmp_path / "chat.db")
    s = ChatStore(db)
    cid = s.create()["id"]
    qid = s.log_query(cid, "what is a SwComponentPrototype?", ["chunk-a", "chunk-b"],
                      "ANSWERED", intent="definition", latency_s=1.5, llm="qwen3:14b",
                      confidence=0.8)
    assert qid.startswith("qlog-")
    rows = s.list_query_log()
    assert len(rows) == 1 and rows[0]["evidence_ids"] == ["chunk-a", "chunk-b"]
    assert rows[0]["outcome"] == "ANSWERED" and rows[0]["intent"] == "definition"
    assert rows[0]["conversation_id"] == cid


def test_log_query_respects_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setattr(store_mod, "QUERY_LOG_ENABLED", False)
    s = ChatStore(str(tmp_path / "chat.db"))
    assert s.log_query("c", "q", [], "ANSWERED") == ""
    assert s.list_query_log() == []


def test_cluster_groups_paraphrases_not_strangers():
    miner = _miner()
    groups = miner.cluster_queries([
        "need detailed information on application sw component configuration with example",
        "explain application software component configuration with an example",
        "what is the CAN frame length?",
    ], threshold=0.4)
    sizes = sorted((len(g) for g in groups), reverse=True)
    assert sizes[0] == 2 and sizes[-1] == 1


def test_rank_clusters_surfaces_failures_first():
    miner = _miner()
    rows = [{"query": "sw component config example", "outcome": "ABSTAIN", "intent": "definition"},
            {"query": "sw component configuration with example", "outcome": "ABSTAIN", "intent": ""},
            {"query": "can frame length", "outcome": "ANSWERED", "intent": ""},
            {"query": "can frame size bits", "outcome": "ANSWERED", "intent": ""}]
    ranked = miner.rank_clusters(rows, threshold=0.4)
    assert ranked[0]["outcomes"].get("ABSTAIN") == 2


def _mini_golden(path, n=6):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for i in range(n):
            fh.write(json.dumps({"query_id": f"q-T-{i:04d}", "question": f"q {i}"}) + "\n")


def test_drift_gate_fails_closed_and_promote_refreezes(tmp_path):
    golden = str(tmp_path / "golden.jsonl")
    split = str(tmp_path / "split.json")
    _mini_golden(golden)
    items = [{"query_id": f"q-T-{i:04d}", "question": f"q {i}"} for i in range(6)]
    save_split(split, items, golden)
    assert verify_split(items, load_split(split), golden) == []

    with open(golden, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"query_id": "q-SNEAK-0001", "question": "sneaky"}) + "\n")
    items2 = items + [{"query_id": "q-SNEAK-0001", "question": "sneaky"}]
    assert verify_split(items2, load_split(split), golden) != []
    with pytest.raises(RuntimeError, match="split drift"):
        run_evaluation(golden_path=golden, canonical=str(tmp_path / "none.db"),
                       index_path=str(tmp_path / "idx"), out_dir=str(tmp_path / "out"),
                       split_path=split, mode="retrieval", use_llm=False)

    miner = _miner()
    res = miner.promote_labels([{"question": "labelled mined question",
                                 "gold_evidence_ids": ["chunk-x"],
                                 "required_modules": ["Rte"]}], golden, split)
    assert len(res["added"]) == 1 and res["added"][0].startswith("q-M-")
    items3 = items2 + [{"query_id": res["added"][0], "question": "labelled mined question"}]
    assert verify_split(items3, load_split(split), golden) == []
    train, holdout = apply_split(items3, load_split(split))
    assert len(train) + len(holdout) == len(items3)
    assert res["train"] + res["holdout"] == sorted(res["train"] + res["holdout"])
    assert set(split_ids([{"query_id": q} for q in res["added"]])["train"] +
               split_ids([{"query_id": q} for q in res["added"]])["holdout"]) == set(res["added"])
