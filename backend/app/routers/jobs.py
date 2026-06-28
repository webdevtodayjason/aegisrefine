from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.job import Job
from app.models.spend_ticket import SpendTicket
from app.models.audit_certificate import AuditCertificate
from app.services.job_service import validate_https_url
from app.services.auth import require_user
from app.services import quote_service
from app.models.user import User
import stripe
import os
import time

router = APIRouter(prefix="/jobs", tags=["jobs"])

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


class QuoteRequest(BaseModel):
    dataset_url: str
    email: str | None = None


class JobRequest(BaseModel):
    quote_token: str


@router.post("/quote")
async def quote(req: QuoteRequest, user: User = Depends(require_user)):
    """Aegis-14B prices the dataset into a flat, CAPPED quote. No Job, no charge yet.
    The private cost estimate is NEVER returned — only the capped price the customer pays."""
    validate_https_url(req.dataset_url)
    try:
        q = quote_service.quote_job(req.dataset_url, req.email or user.email, int(time.time()))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"could not read that dataset: {e}")
    pub = {k: q[k] for k in ("quoted_usd", "cap_usd", "n_records", "data_type", "complexity",
                             "complexity_scored_by", "target_margin_pct", "requires_human_quote")}
    if not q["requires_human_quote"]:
        pub["token"] = q["token"]
    return pub


@router.post("/")
async def create_job(req: JobRequest, user: User = Depends(require_user)):
    """Accept a signed quote and open a Stripe Checkout for EXACTLY the capped amount.
    No Job is created here — the webhook creates it AFTER payment (identity from Stripe)."""
    payload = quote_service.verify_quote_token(req.quote_token, int(time.time()))
    if not payload:
        raise HTTPException(status_code=400, detail="quote expired or invalid — please re-quote")
    quoted = float(payload["q"])
    dataset_url, email = payload["url"], payload["email"]
    validate_https_url(dataset_url)
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price_data": {"currency": "usd",
                                        "product_data": {"name": "Aegis Dataset Refinement"},
                                        "unit_amount": int(round(quoted * 100))},  # the HARD cap
                         "quantity": 1}],
            mode="payment",
            customer_email=email,
            success_url="https://aegisrefine.com/dashboard.html?paid=1",
            cancel_url="https://aegisrefine.com/new-order.html?canceled=1",
            metadata={"dataset_url": dataset_url, "email": email,
                      "quoted_usd": f"{quoted:.2f}", "target_margin_pct": "0.65"},
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"checkout_url": checkout_session.url}


def _job_brief(j: Job) -> dict:
    return {"id": j.id, "status": j.status, "input": j.input_file_path,
            "complexity_score": j.complexity_score, "estimated_cost": j.estimated_cost,
            "created_at": j.created_at.isoformat() if j.created_at else None}


@router.get("/")
async def list_jobs(limit: int = 50, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Recent jobs, newest first (Dashboard)."""
    rows = db.query(Job).order_by(Job.id.desc()).limit(max(1, min(limit, 200))).all()
    return [_job_brief(j) for j in rows]


@router.get("/{job_id}")
async def get_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
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
