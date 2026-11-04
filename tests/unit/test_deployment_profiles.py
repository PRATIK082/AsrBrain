from src.config.deployment import load_profile, profile_defaults


def test_load_profile_defaults():
    for name in ("workstation", "onprem-server", "cloud-saas"):
        p = load_profile(name)
        assert p["profile"] == name
        assert "defaults" in p


def test_profile_defaults_workstation():
    d = profile_defaults("workstation")
    assert d.get("strict_local_only") is True