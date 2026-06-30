import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.spend_service import approve_spend_ticket, reject_spend_ticket, execute_spend_ticket
from app.services.auth import require_admin
from app.services import hermes_operator, stripe_spend
from app.models.audit_certificate import AuditCertificate
from app.models.audit_log import AuditLog
from app.models.job import Job
from app.models.spend_ticket import SpendTicket
from app.models.user import User

router = APIRouter(prefix="/admin/gate", tags=["admin"])
receipts_router = APIRouter(prefix="/admin/jobs", tags=["admin"])


@router.get("/tickets")
async def list_pending_tickets(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Proposed spend tickets awaiting a human decision (admin session required)."""
    return db.query(SpendTicket).filter(SpendTicket.status == "proposed").all()


@router.post("/{ticket_id}/approve")
async def approve_ticket(ticket_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    ticket = approve_spend_ticket(db, ticket_id, approved_by=admin.email)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or already decided")
    return {"status": "approved", "ticket_id": ticket.id, "approved_by": ticket.approved_by}


@router.post("/{ticket_id}/reject")
async def reject_ticket(ticket_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    ticket = reject_spend_ticket(db, ticket_id, rejected_by=admin.email)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or already decided")
    return {"status": "rejected", "ticket_id": ticket.id, "rejected_by": ticket.rejected_by}


@router.post("/{ticket_id}/execute")
async def execute_ticket(ticket_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    ticket = db.query(SpendTicket).filter(SpendTicket.id == ticket_id).first()
    if not ticket or ticket.status != "approved":
        raise HTTPException(status_code=404, detail="Ticket not found or not approved")
    job = db.query(Job).filter(Job.id == ticket.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    op = hermes_operator.dispatch_job(
        db,
        job,
        phase="spend_approved",
        receipt={
            "ticket_id": ticket.id,
            "approved_spend_cents": int(round(float(ticket.amount or 0) * 100)),
            "service": ticket.provider or "ainode_compute",
            "purpose": ticket.description or "agent spend",
        },
        require_config=True,
    )
    result = ((op or {}).get("result") or (op or {}).get("details") or {})
    spend = result.get("spend") if isinstance(result.get("spend"), dict) else {}
    executed = spend.get("executed") if isinstance(spend.get("executed"), dict) else {}
    transfer_id = (
        executed.get("stripe_transfer_id")
        or executed.get("transfer")
        or spend.get("stripe_transfer_id")
        or result.get("stripe_transfer_id")
    )
    payment_id = (
        executed.get("stripe_payment_id")
        or executed.get("payment_intent")
        or spend.get("stripe_payment_id")
        or result.get("stripe_payment_id")
    )
    cap_cents = int(round(float(ticket.amount or 0) * 100))
    expected_destination = (os.getenv("STRIPE_AGENT_SPEND_VENDOR_ACCOUNT") or "").strip()
    if transfer_id and not expected_destination:
        verified = {"executed": None, "status": "missing_vendor_account", "route": "temporarily_queue"}
    elif transfer_id:
        verified = stripe_spend.verify_agent_transfer(transfer_id, cap_cents, expected_destination)
    elif os.getenv("ALLOW_AGENT_PAYMENT_INTENT_SPEND", "").lower() in {"1", "true", "yes"}:
        verified = stripe_spend.verify_agent_spend(payment_id or "", cap_cents)
    else:
        verified = {"executed": None, "status": "missing_transfer", "route": "temporarily_queue"}
    if not verified.get("executed"):
        ticket.stripe_spend_status = verified.get("status") or "unverified"
        ticket.stripe_spend_error = verified.get("error")
        db.commit()
        raise HTTPException(status_code=503, detail={
            "message": "agent spend was not verified by Stripe",
            "verification": verified,
        })

    v = verified["executed"]
    ticket = execute_spend_ticket(
        db,
        ticket_id,
        actual_amount=float(v["amount_cents"]) / 100,
        stripe_payment_intent_id=v.get("stripe_payment_id"),
        stripe_transfer_id=v.get("stripe_transfer_id"),
        stripe_spend_status=v.get("status") or "verified",
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or not approved")
    return {"status": "executed", "ticket_id": ticket.id, "stripe_spend": verified}


@receipts_router.get("/{job_id}/receipt")
async def job_receipt(job_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Admin proof bundle for one customer job: quote, Stripe, spend, audit, certificate."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    tickets = db.query(SpendTicket).filter(SpendTicket.job_id == job_id).order_by(SpendTicket.id).all()
    events = db.query(AuditLog).filter(AuditLog.job_id == job_id).order_by(AuditLog.id).all()
    cert = (
        db.query(AuditCertificate)
        .filter(AuditCertificate.job_id == job_id)
        .order_by(AuditCertificate.id.desc())
        .first()
    )
    return {
        "job": {
            "id": job.id,
            "status": job.status,
            "service": job.service,
            "source": job.input_file_path,
            "stripe_checkout_session_id": job.stripe_checkout_session_id,
            "quote_amount": job.quote_amount,
            "revenue_collected": job.revenue_collected,
            "actual_cost": job.actual_cost,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        },
        "quote": job.quote_breakdown or {},
        "spend_tickets": [{
            "id": t.id,
            "amount": t.amount,
            "actual_amount": t.actual_amount,
            "status": t.status,
            "kind": t.kind,
            "provider": t.provider,
            "units": t.units,
            "cost_source": t.cost_source,
            "stripe_payment_intent_id": t.stripe_payment_intent_id,
            "stripe_transfer_id": t.stripe_transfer_id,
            "stripe_spend_status": t.stripe_spend_status,
            "description": t.description,
        } for t in tickets],
        "audit_events": [{
            "id": e.id,
            "at": e.created_at.isoformat() if e.created_at else None,
            "action": e.action,
            "actor": e.actor,
            "details": e.details or {},
        } for e in events],
        "certificate": ({"id": cert.id, "aar": f"/jobs/{job_id}/aar"} if cert else None),
    }
