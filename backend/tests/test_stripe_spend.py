from types import SimpleNamespace

from app.services import stripe_spend


def test_verify_agent_transfer_accepts_only_verified_cap_and_destination(monkeypatch):
    def retrieve(tid):
        assert tid == "tr_verified"
        return SimpleNamespace(
            id=tid,
            amount=1200,
            currency="usd",
            destination="acct_vendor",
            livemode=False,
            metadata={"service": "ainode_compute"},
        )

    monkeypatch.setattr(stripe_spend.stripe.Transfer, "retrieve", retrieve)

    out = stripe_spend.verify_agent_transfer("tr_verified", 1500, "acct_vendor")

    assert out["verified_against_stripe"] is True
    assert out["cap_respected"] is True
    assert out["destination_ok"] is True
    assert out["executed"]["stripe_transfer_id"] == "tr_verified"
    assert out["executed"]["amount_cents"] == 1200
    assert out["executed"]["destination"] == "acct_vendor"
    assert out["executed"]["livemode"] is False


def test_verify_agent_transfer_rejects_wrong_destination(monkeypatch):
    monkeypatch.setattr(
        stripe_spend.stripe.Transfer,
        "retrieve",
        lambda tid: SimpleNamespace(
            id=tid,
            amount=1200,
            currency="usd",
            destination="acct_other",
            livemode=False,
            metadata={},
        ),
    )

    out = stripe_spend.verify_agent_transfer("tr_verified", 1500, "acct_vendor")

    assert out["executed"] is None
    assert out["status"] == "verified_but_rejected"
    assert out["cap_respected"] is True
    assert out["destination_ok"] is False
    assert out["route"] == "temporarily_queue"


def test_verify_agent_transfer_rejects_over_cap(monkeypatch):
    monkeypatch.setattr(
        stripe_spend.stripe.Transfer,
        "retrieve",
        lambda tid: SimpleNamespace(
            id=tid,
            amount=1600,
            currency="usd",
            destination="acct_vendor",
            livemode=False,
            metadata={},
        ),
    )

    out = stripe_spend.verify_agent_transfer("tr_verified", 1500, "acct_vendor")

    assert out["executed"] is None
    assert out["status"] == "verified_but_rejected"
    assert out["cap_respected"] is False
    assert out["destination_ok"] is True
    assert out["route"] == "temporarily_queue"


def test_verify_agent_transfer_never_synthesizes_ids_on_stripe_error(monkeypatch):
    def boom(_tid):
        raise RuntimeError("stripe is down")

    monkeypatch.setattr(stripe_spend.stripe.Transfer, "retrieve", boom)

    out = stripe_spend.verify_agent_transfer("tr_verified", 1500, "acct_vendor")

    assert out["executed"] is None
    assert out["status"] == "unverified"
    assert out["route"] == "temporarily_queue"
