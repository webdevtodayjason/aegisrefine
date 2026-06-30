from starlette.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.job import Job
from app.models.user import User
from app.services import hermes_operator
from app.services.audit import log_action


def test_dispatch_job_posts_redacted_payload_and_persists_receipt(db, user, monkeypatch):
    job = Job(
        user_id=user.id,
        status="pending",
        input_file_path="users/1/uploads/private.jsonl",
        service="refine",
        quote_amount=55.0,
        approved_cap=55.0,
        revenue_collected=55.0,
        quote_breakdown={"n_records": 10, "complexity_scored_by": "aegis-14b"},
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    captured = {}

    def fake_post(url, payload, timeout, token):
        captured.update({"url": url, "payload": payload, "timeout": timeout, "token": token})
        return {
            "operator": "Hermes Agent",
            "skill": "aegis-refine",
            "route": "run_local",
            "next_action": "continue",
            "telegram_sent": False,
        }

    monkeypatch.setenv("HERMES_OPERATOR_URL", "http://bridge.test/operate")
    monkeypatch.setenv("HERMES_OPERATOR_TOKEN", "test-token")
    monkeypatch.setattr(hermes_operator, "_post_json", fake_post)

    out = hermes_operator.dispatch_job(db, job, phase="paid_job_created")

    assert out["operator"] == "Hermes Agent"
    assert captured["url"] == "http://bridge.test/operate"
    assert captured["token"] == "test-token"
    assert captured["payload"]["job_id"] == job.id
    assert captured["payload"]["source"] == {"kind": "uploaded_file", "value": "uploaded_file"}

    row = (
        db.query(AuditLog)
        .filter(AuditLog.job_id == job.id, AuditLog.action == "hermes_operator_decision")
        .one()
    )
    assert row.actor == "hermes"
    assert row.details["phase"] == "paid_job_created"
    assert row.details["result"]["route"] == "run_local"


def test_operator_receipt_endpoint_is_scoped_to_job_owner(db):
    c = TestClient(app, follow_redirects=False)
    email = "operator-owner@test.com"
    assert c.post("/auth/signup", json={"email": email, "password": "hunter2pass"}).status_code == 200

    u = db.query(User).filter(User.email == email).one()
    job = Job(user_id=u.id, status="completed", input_file_path="https://example.com/data.jsonl")
    db.add(job)
    db.commit()
    db.refresh(job)
    log_action(db, job.id, "hermes_operator_decision", "hermes", {
        "phase": "completed",
        "operator": "Hermes Agent",
        "route": "run_local",
        "result": {"operator": "Hermes Agent", "route": "run_local"},
    })

    r = c.get(f"/jobs/{job.id}/operator")

    assert r.status_code == 200
    assert r.json()["details"]["operator"] == "Hermes Agent"
    assert r.json()["details"]["phase"] == "completed"


def test_operator_receipt_endpoint_hides_other_users_job(db, user):
    other = User(email="operator-other@test.com")
    db.add(other)
    db.commit()
    db.refresh(other)
    job = Job(user_id=other.id, status="completed", input_file_path="https://example.com/data.jsonl")
    db.add(job)
    db.commit()
    db.refresh(job)

    c = TestClient(app, follow_redirects=False)
    assert c.post("/auth/signup", json={"email": "operator-viewer@test.com", "password": "hunter2pass"}).status_code == 200

    assert c.get(f"/jobs/{job.id}/operator").status_code == 404


def test_dispatch_job_unconfigured_is_non_blocking(db, user, monkeypatch):
    monkeypatch.delenv("HERMES_OPERATOR_URL", raising=False)
    job = Job(user_id=user.id, status="pending", input_file_path="https://example.com/data.jsonl")
    db.add(job)
    db.commit()
    db.refresh(job)

    out = hermes_operator.dispatch_job(db, job, phase="paid_job_created")

    assert out == {"ok": False, "status": "unconfigured"}
    rows = db.query(AuditLog).filter(AuditLog.job_id == job.id).all()
    assert rows == []
