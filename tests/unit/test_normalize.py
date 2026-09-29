from src.retrieval.normalize import correct_query


def test_alias_canonicalisation():
    fixed, changes = correct_query("Explain canif initialization")
    assert "CanIf" in fixed and changes


def test_spaced_alias_merge():
    fixed, _ = correct_query("what is can if?")
    assert "CanIf" in fixed


def test_typo_fix_with_record():
    fixed, changes = correct_query("How to configurare CanIf?")
    assert "configure" in fixed
    assert any(a == "configurare" for a, _ in changes)


def test_protected_identifiers_untouched():
    q = "Which requirement defines CanIf_Init in 4.4.0 [E1]?"
    fixed, changes = correct_query(q)
    assert "CanIf_Init" in fixed and "4.4.0" in fixed and "[E1]" in fixed
    assert not any("CanIf_Init" in a for a, _ in changes)


def test_requirement_id_untouched():
    fixed, _ = correct_query("What does PRS_SOMEIP_00043 specify?")
    assert "PRS_SOMEIP_00043" in fixed
