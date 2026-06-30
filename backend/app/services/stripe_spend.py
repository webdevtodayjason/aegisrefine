"""Verified Stripe spend receipts.

The agent may initiate a Stripe spend, but the backend independently verifies the
Stripe object before any SpendTicket is marked executed.
"""

from __future__ import annotations

import os
from typing import Any

import stripe


stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


def _ensure_api_key() -> None:
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY") or stripe.api_key


def verify_agent_transfer(transfer_id: str, approved_cap_cents: int,
                          expected_destination: str | None = None) -> dict[str, Any]:
    """Verify a Stripe Connect Transfer the agent claims it made.

    Returns an executed record only when Stripe confirms the Transfer exists, stayed
    within the approved cap, and optionally went to the expected AINode vendor
    account. Never fabricates a transfer id.
    """
    tid = (transfer_id or "").strip()
    if not tid.startswith("tr_"):
        return {"executed": None, "status": "missing_transfer", "route": "temporarily_queue"}

    try:
        _ensure_api_key()
        tr = stripe.Transfer.retrieve(tid)
    except Exception as e:
        return {
            "executed": None,
            "status": "unverified",
            "route": "temporarily_queue",
            "error": str(e)[:200],
        }

    within_cap = int(tr.amount or 0) <= int(approved_cap_cents or 0)
    destination_ok = not expected_destination or tr.destination == expected_destination
    if not (within_cap and destination_ok):
        return {
            "executed": None,
            "status": "verified_but_rejected",
            "cap_respected": within_cap,
            "destination_ok": destination_ok,
            "route": "temporarily_queue",
        }

    meta = dict(tr.metadata or {})
    return {
        "executed": {
            "stripe_transfer_id": tr.id,
            "amount_cents": int(tr.amount),
            "currency": tr.currency,
            "destination": tr.destination,
            "service": meta.get("service", "unverified"),
            "livemode": bool(tr.livemode),
        },
        "cap_respected": True,
        "destination_ok": True,
        "verified_against_stripe": True,
        "route": "continue",
    }


def verify_agent_spend(payment_intent_id: str, approved_cap_cents: int) -> dict[str, Any]:
    """Backward-compatible PaymentIntent verifier.

    Prefer `verify_agent_transfer` for agent outbound spend. This remains useful
    if a Stripe Skill returns a PaymentIntent for a service purchase instead of a
    Connect Transfer.
    """
    pid = (payment_intent_id or "").strip()
    if not pid.startswith("pi_"):
        return {"executed": None, "status": "missing_payment_intent", "route": "temporarily_queue"}

    try:
        _ensure_api_key()
        pi = stripe.PaymentIntent.retrieve(pid)
    except Exception as e:
        return {"executed": None, "status": "unverified", "route": "temporarily_queue", "error": str(e)[:200]}

    within_cap = int(pi.amount or 0) <= int(approved_cap_cents or 0)
    if not (pi.status == "succeeded" and within_cap):
        return {"executed": None, "status": pi.status, "cap_respected": within_cap, "route": "temporarily_queue"}

    meta = dict(pi.metadata or {})
    return {
        "executed": {
            "stripe_payment_id": pi.id,
            "amount_cents": int(pi.amount),
            "currency": pi.currency,
            "status": pi.status,
            "service": meta.get("service", "unverified"),
            "livemode": bool(pi.livemode),
        },
        "cap_respected": True,
        "verified_against_stripe": True,
        "route": "continue",
    }
