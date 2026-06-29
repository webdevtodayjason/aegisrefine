import time
from types import SimpleNamespace

from starlette.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.job import Job
from app.services.quote_service import sign_quote_token


def _client():
    return TestClient(app, follow_redirects=False)


def _signup(c, email="buyer-checkout@test.com"):
    r = c.post("/auth/signup", json={"email": email, "password": "hunter2pass"})
    assert r.status_code == 200
    return email


def test_checkout_uses_local_return_url_when_started_from_localhost(monkeypatch):
    from app.routers import jobs

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(url="https://checkout.stripe.test/session")

    monkeypatch.setattr(jobs.stripe.checkout.Session, "create", fake_create)

    c = _client()
    email = _signup(c)
    token = sign_quote_token({"quoted_usd": 55.0}, "https://example.com/data.jsonl", email, int(time.time()))
    r = c.post(
        "/jobs/",
        json={"quote_token": token},
        headers={"origin": "http://localhost:3000"},
    )

    assert r.status_code == 200
    assert r.json()["checkout_url"] == "https://checkout.stripe.test/session"
    assert captured["success_url"] == "http://localhost:3000/dashboard?paid=1&session_id={CHECKOUT_SESSION_ID}"
    assert captured["cancel_url"] == "http://localhost:3000/new-order?canceled=1"
    assert captured["metadata"]["email"] == email


def test_checkout_sync_verifies_paid_session_and_is_idempotent(monkeypatch):
    from app.routers import jobs
    from app.services import job_runner

    c = _client()
    email = _signup(c, "buyer-sync@test.com")
    session = {
        "id": "cs_test_sync_123",
        "payment_status": "paid",
        "amount_total": 5500,
        "metadata": {
            "service": "refine",
            "dataset_url": "https://example.com/data.jsonl",
            "email": email,
            "quoted_usd": "55.00",
            "target_margin_pct": "0.65",
        },
    }

    monkeypatch.setattr(jobs.stripe.checkout.Session, "retrieve", lambda sid: session)
    monkeypatch.setattr(job_runner, "auto_run_job", lambda job_id: None)

    r1 = c.post("/jobs/checkout/sync", json={"session_id": "cs_test_sync_123"})
    r2 = c.post("/jobs/checkout/sync", json={"session_id": "cs_test_sync_123"})

    assert r1.status_code == 200
    assert r1.json()["created"] is True
    assert r2.status_code == 200
    assert r2.json()["created"] is False
    assert r1.json()["job_id"] == r2.json()["job_id"]

    db = SessionLocal()
    try:
        rows = db.query(Job).filter(Job.stripe_checkout_session_id == "cs_test_sync_123").all()
        assert len(rows) == 1
        assert rows[0].quote_amount == 55.0
        assert rows[0].revenue_collected == 55.0
        assert rows[0].input_file_path == "https://example.com/data.jsonl"
    finally:
        db.close()


def test_checkout_sync_rejects_wrong_user(monkeypatch):
    from app.routers import jobs

    c = _client()
    _signup(c, "buyer-one@test.com")
    session = {
        "id": "cs_test_wrong_user",
        "payment_status": "paid",
        "amount_total": 5500,
        "metadata": {
            "service": "refine",
            "dataset_url": "https://example.com/data.jsonl",
            "email": "buyer-two@test.com",
            "quoted_usd": "55.00",
        },
    }
    monkeypatch.setattr(jobs.stripe.checkout.Session, "retrieve", lambda sid: session)

    r = c.post("/jobs/checkout/sync", json={"session_id": "cs_test_wrong_user"})

    assert r.status_code == 403
