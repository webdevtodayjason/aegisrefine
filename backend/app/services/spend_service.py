"""
Gated Spend Service
Handles the full propose → human gate → execute flow for Aegis.
Every transition writes an AuditLog row so the trail can prove WHO did WHAT WHEN.
"""

from sqlalchemy.orm import Session
from app.models.spend_ticket import SpendTicket
from app.services.audit import log_action
from datetime import datetime

def create_spend_ticket(db: Session, job_id: int, amount: float, description: str):
    """Agent proposes a spend. Creates a pending ticket."""
    ticket = SpendTicket(
        job_id=job_id,
        amount=amount,
        description=description,
        status="proposed"
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    log_action(db, job_id, "spend_proposed", "agent",
               {"ticket_id": ticket.id, "amount": amount, "description": description})
    return ticket

def approve_spend_ticket(db: Session, ticket_id: int, approved_by: str = "admin"):
    """Human approves the spend ticket."""
    ticket = db.query(SpendTicket).filter(SpendTicket.id == ticket_id).first()
    if not ticket or ticket.status != "proposed":
        return None

    ticket.status = "approved"
    ticket.approved_by = approved_by
    ticket.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)
    log_action(db, ticket.job_id, "spend_approved", "human",
               {"ticket_id": ticket.id, "amount": ticket.amount, "approved_by": approved_by})
    return ticket

def reject_spend_ticket(db: Session, ticket_id: int, rejected_by: str = "admin"):
    """Human rejects the spend ticket."""
    ticket = db.query(SpendTicket).filter(SpendTicket.id == ticket_id).first()
    if not ticket or ticket.status != "proposed":
        return None

    ticket.status = "rejected"
    ticket.rejected_by = rejected_by
    ticket.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)
    log_action(db, ticket.job_id, "spend_rejected", "human",
               {"ticket_id": ticket.id, "amount": ticket.amount, "rejected_by": rejected_by})
    return ticket

def execute_spend_ticket(db: Session, ticket_id: int, actual_amount: float | None = None,
                         stripe_payment_intent_id: str | None = None,
                         stripe_transfer_id: str | None = None,
                         stripe_spend_status: str | None = None,
                         stripe_spend_error: str | None = None):
    """Execute the approved spend. `actual_amount` settles the ledger with the real metered cost
    (pay-per-success); until a real provider adapter is wired it equals the reserved amount.

    The admin route must pass a Stripe-verified payment or transfer id before
    using this for real outbound spend execution.
    """
    ticket = db.query(SpendTicket).filter(SpendTicket.id == ticket_id).first()
    if not ticket or ticket.status != "approved":
        return None

    ticket.status = "executed"
    ticket.executed_at = datetime.utcnow()
    if actual_amount is not None:
        ticket.actual_amount = actual_amount
    if stripe_payment_intent_id:
        ticket.stripe_payment_intent_id = stripe_payment_intent_id
        ticket.stripe_spend_status = stripe_spend_status or "verified"
    if stripe_transfer_id:
        ticket.stripe_transfer_id = stripe_transfer_id
        ticket.stripe_spend_status = stripe_spend_status or "verified"
    elif stripe_spend_status:
        ticket.stripe_spend_status = stripe_spend_status
    if stripe_spend_error:
        ticket.stripe_spend_error = stripe_spend_error[:240]
    db.commit()
    db.refresh(ticket)
    details = {
        "ticket_id": ticket.id,
        "amount": ticket.actual_amount or ticket.amount,
        "real_money": bool(stripe_payment_intent_id or stripe_transfer_id),
        "stripe_payment_intent_id": stripe_payment_intent_id,
        "stripe_transfer_id": stripe_transfer_id,
        "stripe_spend_status": ticket.stripe_spend_status,
    }
    log_action(db, ticket.job_id, "spend_executed", "system", details)
    return ticket


def authorize_within_cap(db: Session, ticket_id: int, job):
    """Autonomous spend that the ACCEPTED QUOTE pre-authorized (projected ≤ cap).

    HONEST: actor='agent', action='spend_preauthorized' — this NEVER routes through
    approve_spend_ticket and so never writes a human-approver audit row for a machine decision.
    """
    t = db.query(SpendTicket).filter(SpendTicket.id == ticket_id, SpendTicket.status == "proposed").first()
    if not t:
        return None
    cap = job.approved_cap if job.approved_cap is not None else job.quote_amount
    t.status = "approved"
    t.approved_by = f"quote_pre_authorization#job:{job.id}#cap:${(cap or 0):.2f}"
    t.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(t)
    log_action(db, t.job_id, "spend_preauthorized", "agent", {"ticket_id": t.id, "amount": t.amount})
    return t


def approve_overrun(db: Session, ticket_id: int, job, *, mode: str, approved_by: str,
                    recharge_payment_intent: str | None = None):
    """Human decision on a gated cap overrun. mode in {'absorb','recharge'} — either way the
    cap rises to admit this ticket (recharge also adds new revenue from a re-quote Checkout)."""
    from app.services import budget_service
    t = approve_spend_ticket(db, ticket_id, approved_by=approved_by)  # truthful human audit row
    if not t:
        return None
    job.approved_cap = float(budget_service.ledger(db, job)["committed"])
    if mode == "recharge":
        job.revenue_collected = (job.revenue_collected or job.quote_amount or 0) + t.amount
        t.stripe_payment_intent_id = recharge_payment_intent
    job.status = "processing"
    db.commit()
    log_action(db, job.id, "cap_raised", "human",
               {"mode": mode, "new_cap": job.approved_cap, "by": approved_by})
    return t
