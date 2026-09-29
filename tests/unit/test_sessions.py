from src.chat.store import ChatStore


def test_bundle_roundtrip(tmp_path):
    s = ChatStore(str(tmp_path / "c.db"))
    cid = s.create(title="t")["id"]
    s.merge_slots(cid, releases=["4.4.0"], modules=["CanIf"])
    s.add_message(cid, "user", "hi")
    s.add_message(cid, "assistant", "hello [E1]",
                  {"trace": {"a": 1}, "evidence": [{"label": "E1"}], "followups": ["q?"]})
    b = s.export_bundle(cid)
    assert b["format"] == "autosar-session/1" and len(b["messages"]) == 2
    imp = s.import_bundle(b)
    back = s.get(imp["id"])
    assert back["slots"]["modules"] == ["CanIf"]
    assert back["messages"][-1]["meta"]["followups"] == ["q?"]


def test_bundle_rejects_garbage(tmp_path):
    import pytest
    s = ChatStore(str(tmp_path / "c.db"))
    with pytest.raises(ValueError):
        s.import_bundle({"format": "nope"})
