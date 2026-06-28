from app.services import escalation, provider_catalog as pc


def test_no_key_is_inert(monkeypatch):
    for p in pc.ARSENAL.values():
        monkeypatch.delenv(p["env_var"], raising=False)
    assert escalation.available() == []
    assert escalation.pick_model("hard/reasoning") is None
    assert escalation.escalate([{"role": "user", "content": "hi"}]) is None


def test_picks_cheapest_capable_with_key(monkeypatch):
    for p in pc.ARSENAL.values():
        monkeypatch.delenv(p["env_var"], raising=False)
    # only a Z.ai key present -> hard/reasoning ladder should resolve to a Z.ai model
    monkeypatch.setenv("ZAI_API_KEY", "test")
    m = escalation.pick_model("hard/reasoning")
    assert m and pc._ARSENAL_PROVIDER[m] == "zai"
    assert escalation.estimate_cost(m) > 0


def test_estimate_cost_uses_catalog():
    assert escalation.estimate_cost("glm-4.5-air") > 0
