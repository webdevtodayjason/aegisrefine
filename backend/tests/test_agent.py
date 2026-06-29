import json

import pytest

from app.services import agent


def test_schema_instruction_names_every_required_key():
    prompt = agent.build_prompt("triage", "Score this dataset.")

    for key in agent.JOB_SCHEMAS["triage"]:
        assert f'"{key}"' in prompt
    assert "Do not omit any required key" in prompt


def test_parse_error_includes_clipped_raw_response():
    with pytest.raises(agent.AgentError) as exc:
        agent.parse_decision("triage", json.dumps({"complexity": 0.2}))

    msg = str(exc.value)
    assert "missing required fields" in msg
    assert "raw=" in msg
    assert '"complexity": 0.2' in msg


def test_decide_sends_explicit_schema_contract(monkeypatch):
    captured = {}

    class _Message:
        content = json.dumps({
            "complexity": 0.2,
            "risk": "low",
            "est_tokens": 1000,
            "noise_level": 0.1,
            "steps": ["parse", "normalize"],
            "can_run_locally": True,
        })

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Response()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(agent, "_client", lambda: _Client())

    out = agent.decide("triage", "Score this dataset.", retries=0)

    assert out["can_run_locally"] is True
    user_prompt = captured["messages"][1]["content"]
    for key in agent.JOB_SCHEMAS["triage"]:
        assert f'"{key}"' in user_prompt
    assert captured["response_format"] == {"type": "json_object"}
