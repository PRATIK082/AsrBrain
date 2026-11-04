from src.system.context import build_self_context


def test_build_self_context_shape():
    ctx = build_self_context()
    assert ctx["profile"] in {"workstation", "onprem-server", "cloud-saas"}
    assert "capabilities" in ctx
    assert "features" in ctx
    assert "health" in ctx
    assert "recommended_actions" in ctx
    assert isinstance(ctx["features"], list)
    assert all("status" in f for f in ctx["features"])