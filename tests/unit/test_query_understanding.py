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


def test_com_never_detected_inside_other_words():
    # the Com-flavor bug: "com" is a substring of all of these
    for q in ("Explain the communication path in the RTE",
              "Describe this software component completely",
              "Compare CanIf in AUTOSAR 4.2 and 4.4.",
              "Show a complex combination of signals"):
        p = parse(q)
        assert "Com" not in p.modules, q


def test_rte_detected_for_rte_questions():
    p = parse("Explain the RTE communication path and runnables")
    assert "RTE" in p.modules and "Com" not in p.modules


def test_dtc_routes_to_dem_not_com():
    p = parse("What is a DTC and how is it stored in diagnostics?")
    assert "Dem" in p.modules and "Com" not in p.modules


def test_api_prefix_implies_module():
    assert "Dem" in parse("Explain Dem_GetStatusOfDTC").modules
    assert "RTE" in parse("How does Rte_Read behave?").modules
    assert "Com" in parse("How does Com_SendSignal behave?").modules


def test_initialization_sequences_are_explanations():
    p = parse("Explain CanIf initialization sequence")
    assert p.intent == "deep_explanation"
    assert "CanIf" in p.modules
