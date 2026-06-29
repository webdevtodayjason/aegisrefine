from starlette.testclient import TestClient

from app.main import app
from app.services import agent


def test_legacy_health_remains_api_only():
    data = TestClient(app).get("/health").json()

    assert data == {"status": "healthy"}


def test_agent_health_reports_ok_with_latency(monkeypatch):
    calls = {}

    def _decide(job, task_text, *, model=None, retries=1):
        calls.update({"job": job, "task_text": task_text, "model": model, "retries": retries})
        return {"can_run_locally": True}

    monkeypatch.setattr(agent, "decide", _decide)

    response = TestClient(app).get("/agent/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["model_name"] == "Aegis-14B"
    assert isinstance(data["latency_ms"], int)
    assert data["latency_ms"] >= 0
    assert "error" not in data
    assert calls["job"] == "triage"
    assert calls["model"] == "Aegis-14B"
    assert calls["retries"] == 0
    assert "health probe" in calls["task_text"].lower()


def test_agent_health_reports_degraded_on_decide_failure(monkeypatch):
    def _decide(job, task_text, *, model=None, retries=1):
        raise agent.AegisTemporarilyQueued("DGX Spark queue is saturated")

    monkeypatch.setattr(agent, "decide", _decide)

    response = TestClient(app).get("/agent/health")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "status": "degraded",
        "model_name": "Aegis-14B",
        "error": "DGX Spark queue is saturated",
    }
