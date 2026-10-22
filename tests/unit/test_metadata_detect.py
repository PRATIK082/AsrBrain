"""Release/platform/module detection: CP headers outrank R-number guesses."""
from src.ingestion.metadata import detect_release_platform, infer_module


def test_cp_template_with_r_number_is_classic():
    text = "System Template AUTOSAR CP R22-11\nclassic platform overview " * 200
    release, platform, doctype = detect_release_platform(text, "AUTOSAR_TPS_SystemTemplate.pdf")
    assert release == "R22-11" and platform == "Classic" and doctype == "TPS"


def test_foundation_prs_unchanged():
    text = "AUTOSAR FO PRS SOMEIPProtocol R24-11 foundation interoperability " * 200
    release, platform, doctype = detect_release_platform(text, "AUTOSAR_FO_PRS_SOMEIPProtocol.pdf")
    assert (release, platform, doctype) == ("R24-11", "Foundation", "PRS")


def test_multi_module_template_abstains():
    text = ("Scope " * 500 + "BSW Context EthIf x " * 5 + "BSW Context CanIf y " * 5
            + "BSW Context Com z " * 5 + "BSW Context TcpIp w " * 5 + "rte rte rte rte rte")
    assert infer_module(text) == ""


def test_bsw_marker_across_line_break():
    # Page-normalised text keeps single newlines: the marker and the module name
    # often sit on different lines ("BSW Context\nEthSwt").
    text = ("Scope " * 500 + "BSW Context\nEthSwt x " * 10 + "BSW Context\nMirror y " * 10)
    assert infer_module(text) == ""


def test_single_bsw_context_wins():
    text = "Scope " * 200 + "BSW Context CanIf CanIf/CanIfInit " * 10 + "rte mention once"
    assert infer_module(text) == "CanIf"


def test_unmapped_bsw_contexts_abstain():
    text = "Scope " * 200 + "BSW Context EthSwt x " * 10 + "BSW Context Mirror y " * 10
    assert infer_module(text) == ""
