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

def execute_spend_ticket(db: Session, ticket_id: int):
    """Execute the approved spend via Stripe Skills.

    ponytail: real Stripe Skills outbound call (Hermes @stripe/link-cli spend-request,
    non-zero exit = denied = no money moves) lands in Phase 2 — this records the
    state transition + audit row so the gate is honest today. It does NOT yet move money.
    """
    ticket = db.query(SpendTicket).filter(SpendTicket.id == ticket_id).first()
    if not ticket or ticket.status != "approved":
        return None

    # TODO(phase2): subprocess @stripe/link-cli spend-request --request-approval;
    # returncode 0 => mark executed + store stripe_payment_intent_id; non-zero => do NOT execute.
    ticket.status = "executed"
    ticket.executed_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)
    log_action(db, ticket.job_id, "spend_executed", "system",
               {"ticket_id": ticket.id, "amount": ticket.amount, "real_money": False})
    return ticket
