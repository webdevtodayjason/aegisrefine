from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.spend_service import approve_spend_ticket, reject_spend_ticket, execute_spend_ticket
from app.services.auth import require_admin
from app.models.spend_ticket import SpendTicket
from app.models.user import User

router = APIRouter(prefix="/admin/gate", tags=["admin"])


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
