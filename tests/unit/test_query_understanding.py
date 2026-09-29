from src.retrieval.query_understanding import parse


def test_exact_release_routing():
    p = parse("Explain CanIf in AUTOSAR 4.4.")
    assert p.release_mode == "exact" and "4.4" in p.releases and "CanIf" in p.modules


def test_comparison_routing():
    p = parse("Compare CanIf in AUTOSAR 4.2 and 4.4.")
    assert p.release_mode == "comparison" and p.needs_comparison_table


def test_requirement_and_api_extraction():
    p = parse("Which requirement defines CanIf_Init?")
    assert "CanIf_Init" in p.api_names
    assert p.intent in ("api_lookup", "requirement_lookup")


def test_troubleshooting_intent():
    p = parse("Why does CanIf_Transmit return E_NOT_OK?")
    assert p.intent == "troubleshooting"
