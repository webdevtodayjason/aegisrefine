from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.job import Job
from app.models.spend_ticket import SpendTicket
from app.models.audit_certificate import AuditCertificate
from app.services.job_service import validate_https_url
import stripe
import os

router = APIRouter(prefix="/jobs", tags=["jobs"])

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


class JobRequest(BaseModel):
    dataset_url: str
    email: str


@router.post("/")
async def create_job(req: JobRequest):
    """Start a refinement order: validate the dataset URL and open a Stripe Checkout.
    No Job is created here and no client user_id is accepted — the Job is created by the
    webhook AFTER payment, with identity taken from the Stripe-authenticated session.
    """
    validate_https_url(req.dataset_url)
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Aegis Dataset Refinement"},
                    "unit_amount": 2000,  # $20.00
                },
                "quantity": 1,
            }],
            mode="payment",
            customer_email=req.email,
            success_url="https://aegisrefine.com/jobs?success=true",
            cancel_url="https://aegisrefine.com/new-order?canceled=true",
            metadata={"dataset_url": req.dataset_url, "email": req.email},
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"checkout_url": checkout_session.url}


def _job_brief(j: Job) -> dict:
    return {"id": j.id, "status": j.status, "input": j.input_file_path,
            "complexity_score": j.complexity_score, "estimated_cost": j.estimated_cost,
            "created_at": j.created_at.isoformat() if j.created_at else None}


@router.get("/")
async def list_jobs(limit: int = 50, db: Session = Depends(get_db)):
    """Recent jobs, newest first (Dashboard)."""
    rows = db.query(Job).order_by(Job.id.desc()).limit(max(1, min(limit, 200))).all()
    return [_job_brief(j) for j in rows]


@router.get("/{job_id}")
async def get_job(job_id: int, db: Session = Depends(get_db)):
    """One job + its spend tickets + certificate (OrderDetail / Certificate)."""
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    tickets = db.query(SpendTicket).filter(SpendTicket.job_id == job_id).order_by(SpendTicket.id).all()
    cert = (db.query(AuditCertificate).filter(AuditCertificate.job_id == job_id)
            .order_by(AuditCertificate.id.desc()).first())
    out = _job_brief(j)
    out.update({
        "output": j.output_file_path, "actual_cost": j.actual_cost,
        "spend_tickets": [{"id": t.id, "amount": t.amount, "description": t.description,
                           "status": t.status, "approved_by": t.approved_by} for t in tickets],
        "certificate": ({"id": cert.id, "aar": f"/jobs/{job_id}/aar"} if cert else None),
    })
    return out
