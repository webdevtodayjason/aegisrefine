from app.services import escalation


def test_no_key_is_inert(monkeypatch):
    for env in ("OPENROUTER_API_KEY", "NVIDIA_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    assert escalation.available() == []
    assert escalation.escalate([{"role": "user", "content": "hi"}]) is None


def test_estimate_cost_uses_catalog():
    assert escalation.estimate_cost("openrouter") > 0
