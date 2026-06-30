from starlette.testclient import TestClient
from uuid import uuid4

from app.main import app
from app.models.job import Job
from app.models.spend_ticket import SpendTicket
from app.models.user import User
from app.routers import admin as admin_router
from app.services import auth


def _admin_client(db):
    suffix = uuid4().hex[:8]
    admin = User(email=f"spend-admin-{suffix}@test.com", is_admin=True)
    buyer = User(email=f"spend-buyer-{suffix}@test.com")
    db.add_all([admin, buyer])
    db.commit()
    db.refresh(admin)
    db.refresh(buyer)
    c = TestClient(app)
    c.cookies.set(auth.COOKIE, auth.make_token(admin))
    return c, buyer


def _approved_ticket(db, buyer):
    job = Job(user_id=buyer.id, status="processing", quote_amount=55.0, approved_cap=55.0)
    db.add(job)
    db.commit()
    db.refresh(job)
    ticket = SpendTicket(
        job_id=job.id,
        amount=12.0,
        description="OCR enrichment",
        provider="ainode_compute",
        status="approved",
        approved_by="ops@test.com",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return job, ticket


def test_admin_execute_requires_verified_stripe_transfer(db, monkeypatch):
    c, buyer = _admin_client(db)
    _job, ticket = _approved_ticket(db, buyer)
    monkeypatch.setenv("STRIPE_AGENT_SPEND_VENDOR_ACCOUNT", "acct_vendor")

    def fake_dispatch(*_args, **_kwargs):
        return {
            "result": {
                "spend": {
                    "executed": {
                        "stripe_transfer_id": "tr_verified",
                        "amount_cents": 1200,
                        "destination": "acct_vendor",
                    }
                }
            }
        }

    def fake_verify(transfer_id, approved_cap_cents, expected_destination):
        assert transfer_id == "tr_verified"
        assert approved_cap_cents == 1200
        assert expected_destination == "acct_vendor"
        return {
            "executed": {
                "stripe_transfer_id": "tr_verified",
                "amount_cents": 1200,
                "currency": "usd",
                "destination": "acct_vendor",
                "livemode": False,
            },
            "verified_against_stripe": True,
            "cap_respected": True,
            "destination_ok": True,
            "route": "continue",
        }

    monkeypatch.setattr(admin_router.hermes_operator, "dispatch_job", fake_dispatch)
    monkeypatch.setattr(admin_router.stripe_spend, "verify_agent_transfer", fake_verify)

    r = c.post(f"/admin/gate/{ticket.id}/execute")

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "executed"
    assert data["stripe_spend"]["executed"]["stripe_transfer_id"] == "tr_verified"
    db.refresh(ticket)
    assert ticket.status == "executed"
    assert ticket.actual_amount == 12.0
    assert ticket.stripe_transfer_id == "tr_verified"
    assert ticket.stripe_spend_status == "verified"


def test_admin_execute_queues_when_transfer_is_not_verified(db, monkeypatch):
    c, buyer = _admin_client(db)
    _job, ticket = _approved_ticket(db, buyer)
    monkeypatch.setenv("STRIPE_AGENT_SPEND_VENDOR_ACCOUNT", "acct_vendor")

    monkeypatch.setattr(
        admin_router.hermes_operator,
        "dispatch_job",
        lambda *_args, **_kwargs: {"result": {"spend": {"executed": {"stripe_transfer_id": "tr_bad"}}}},
    )
    monkeypatch.setattr(
        admin_router.stripe_spend,
        "verify_agent_transfer",
        lambda *_args, **_kwargs: {
            "executed": None,
            "status": "verified_but_rejected",
            "route": "temporarily_queue",
            "error": "wrong destination",
        },
    )

    r = c.post(f"/admin/gate/{ticket.id}/execute")

    assert r.status_code == 503
    db.refresh(ticket)
    assert ticket.status == "approved"
    assert ticket.executed_at is None
    assert ticket.stripe_transfer_id is None
    assert ticket.stripe_spend_status == "verified_but_rejected"
    assert ticket.stripe_spend_error == "wrong destination"


def test_admin_execute_does_not_accept_missing_transfer_by_default(db, monkeypatch):
    c, buyer = _admin_client(db)
    _job, ticket = _approved_ticket(db, buyer)

    monkeypatch.delenv("ALLOW_AGENT_PAYMENT_INTENT_SPEND", raising=False)
    monkeypatch.setattr(
        admin_router.hermes_operator,
        "dispatch_job",
        lambda *_args, **_kwargs: {"result": {"spend": {"executed": None}}},
    )

    r = c.post(f"/admin/gate/{ticket.id}/execute")

    assert r.status_code == 503
    db.refresh(ticket)
    assert ticket.status == "approved"
    assert ticket.stripe_spend_status == "missing_transfer"


def test_admin_execute_requires_configured_vendor_destination(db, monkeypatch):
    c, buyer = _admin_client(db)
    _job, ticket = _approved_ticket(db, buyer)

    monkeypatch.delenv("STRIPE_AGENT_SPEND_VENDOR_ACCOUNT", raising=False)
    monkeypatch.setattr(
        admin_router.hermes_operator,
        "dispatch_job",
        lambda *_args, **_kwargs: {"result": {"spend": {"executed": {"stripe_transfer_id": "tr_verified"}}}},
    )

    r = c.post(f"/admin/gate/{ticket.id}/execute")

    assert r.status_code == 503
    db.refresh(ticket)
    assert ticket.status == "approved"
    assert ticket.stripe_spend_status == "missing_vendor_account"
