from starlette.testclient import TestClient

from app.main import app
from app.models.audit_certificate import AuditCertificate
from app.models.audit_log import AuditLog
from app.models.job import Job
from app.models.spend_ticket import SpendTicket
from app.models.user import User
from app.services import auth


def test_admin_job_receipt_includes_quote_spend_audit_and_certificate(db):
    admin = User(email="receipt-admin@test.com", is_admin=True)
    buyer = User(email="receipt-buyer@test.com")
    db.add_all([admin, buyer])
    db.commit()
    db.refresh(admin)
    db.refresh(buyer)
    job = Job(
        user_id=buyer.id,
        status="completed",
        input_file_path="https://example.com/data.jsonl",
        stripe_checkout_session_id="cs_test_receipt_admin",
        quote_amount=55.0,
        quote_breakdown={"n_records": 10, "complexity_scored_by": "aegis-14b"},
        actual_cost=0.003,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    db.add(SpendTicket(job_id=job.id, amount=0.003, status="executed", provider="MiniMax-M2"))
    db.add(AuditLog(job_id=job.id, action="triage", actor="agent", details={"model": "Aegis-14B"}))
    db.add(AuditCertificate(job_id=job.id, content='{"sig":{"alg":"Ed25519"}}'))
    db.commit()

    c = TestClient(app)
    c.cookies.set(auth.COOKIE, auth.make_token(admin))

    r = c.get(f"/admin/jobs/{job.id}/receipt")

    assert r.status_code == 200
    data = r.json()
    assert data["job"]["id"] == job.id
    assert data["job"]["stripe_checkout_session_id"] == "cs_test_receipt_admin"
    assert data["quote"]["n_records"] == 10
    assert data["quote"]["complexity_scored_by"] == "aegis-14b"
    assert data["spend_tickets"][0]["provider"] == "MiniMax-M2"
    assert data["audit_events"][0]["action"] == "triage"
    assert data["certificate"]["aar"] == f"/jobs/{job.id}/aar"
