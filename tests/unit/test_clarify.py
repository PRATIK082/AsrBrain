from src.retrieval.clarify import missing_slots, clarification_question, apply_user_confirmation
from src.retrieval.query_understanding import parse


def test_no_clarify_when_corpus_single_release():
    p = parse("What is SOME/IP?")
    assert missing_slots({"releases": [], "platforms": []}, ["R24-11"], ["Foundation"]) == []


def test_ask_back_when_corpus_spans_versions():
    p = parse("Explain CanIf initialization")
    missing = missing_slots({"releases": p.releases, "platforms": p.platforms},
                            ["4.2.2", "4.4.0"], ["Classic", "Adaptive"])
    assert "release" in missing and "platform" in missing


def test_module_never_required_but_proposed():
    p = parse("Explain CanIf initialization in 4.4")
    missing = missing_slots({"releases": p.releases, "platforms": p.platforms}, ["4.2.2", "4.4.0"], ["Classic", "Adaptive"])
    assert "module" not in missing
    q = clarification_question({"modules": p.modules}, missing)
    assert "CanIf" in q and "confirm" in q.lower()


def test_user_reply_folds_into_plan():
    p = parse("Explain CanIf initialization")
    p2 = apply_user_confirmation(p, "4.4.0 Classic")
    assert "4.4.0" in p2.releases and "Classic" in p2.platforms
