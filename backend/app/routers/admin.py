from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.spend_service import approve_spend_ticket, reject_spend_ticket, execute_spend_ticket
from app.models.spend_ticket import SpendTicket
import os

router = APIRouter(prefix="/admin/gate", tags=["admin"])

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

def require_admin(x_admin_key: str = Header(None)):
    """Gate the human-gate. Real money rides on this — no key, no entry."""
    if not ADMIN_API_KEY or x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing admin key")
    return True

@router.get("/tickets")
async def list_pending_tickets(db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    """List all proposed spend tickets waiting for human decision."""
    tickets = db.query(SpendTicket).filter(SpendTicket.status == "proposed").all()
    return tickets

@router.post("/{ticket_id}/approve")
async def approve_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin),
    x_admin_user: str = Header("admin"),
):
    """Human approves a spend ticket. x_admin_user is recorded as the approver."""
    ticket = approve_spend_ticket(db, ticket_id, approved_by=x_admin_user)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or already decided")
    return {"status": "approved", "ticket_id": ticket.id, "approved_by": ticket.approved_by}

@router.post("/{ticket_id}/reject")
async def reject_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin),
    x_admin_user: str = Header("admin"),
):
    """Human rejects a spend ticket."""
    ticket = reject_spend_ticket(db, ticket_id, rejected_by=x_admin_user)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or already decided")
    return {"status": "rejected", "ticket_id": ticket.id, "rejected_by": ticket.rejected_by}

@router.post("/{ticket_id}/execute")
async def execute_ticket(ticket_id: int, db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    """Execute an approved spend ticket via Stripe Skills."""
    ticket = execute_spend_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or not approved")
    return {"status": "executed", "ticket_id": ticket.id}
