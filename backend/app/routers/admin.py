from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.spend_service import approve_spend_ticket, reject_spend_ticket, execute_spend_ticket
from app.services.auth import require_admin
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
    ticket = execute_spend_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or not approved")
    return {"status": "executed", "ticket_id": ticket.id}


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
