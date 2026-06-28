from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse, Response
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


class SynthQuoteRequest(BaseModel):
    topic: str
    target_kept: int = 100
    reference: str | None = None   # augment: an https dataset URL to ground generation in; empty = from-seed


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


@router.post("/synth-quote")
async def synth_quote(req: SynthQuoteRequest, user: User = Depends(require_user)):
    """Price a synthesize/augment job into a flat CAPPED quote. The private COGS estimate is
    NEVER returned — only the capped price. A reference URL (if given) makes it an augment job."""
    if not (req.topic or "").strip():
        raise HTTPException(status_code=400, detail="a topic/domain is required")
    tk = max(1, min(int(req.target_kept or 100), 5000))
    reference = (req.reference or "").strip()
    if reference:
        validate_https_url(reference)
    q = quote_service.quote_synth(tk)
    token = quote_service.sign_synth_token(q, req.topic.strip(), tk, reference, user.email, int(time.time()))
    return {"quote_usd": q["quote_usd"], "target_kept": tk, "target_margin_pct": q["target_margin_pct"],
            "service": "synthesis", "mode": "augment" if reference else "from-seed", "token": token}


@router.post("/")
async def create_job(req: JobRequest, user: User = Depends(require_user)):
    """Accept a signed quote (refine OR synthesis) and open a Stripe Checkout for EXACTLY the
    capped amount. No Job is created here — the webhook creates it AFTER payment (identity from Stripe)."""
    payload = quote_service.verify_quote_token(req.quote_token, int(time.time()))
    if not payload:
        raise HTTPException(status_code=400, detail="quote expired or invalid — please re-quote")
    quoted = float(payload["q"])
    email = payload["email"]
    if payload.get("service") == "synthesis":
        product = "Aegis Dataset Synthesis"
        meta = {"service": "synthesis", "email": email, "quoted_usd": f"{quoted:.2f}",
                "target_margin_pct": "0.65", "topic": (payload.get("topic") or "")[:480],
                "target_kept": str(payload.get("target_kept") or 0),
                "reference": (payload.get("reference") or "")[:480]}
    else:
        dataset_url = payload["url"]
        validate_https_url(dataset_url)
        product = "Aegis Dataset Refinement"
        meta = {"service": "refine", "dataset_url": dataset_url, "email": email,
                "quoted_usd": f"{quoted:.2f}", "target_margin_pct": "0.65"}
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price_data": {"currency": "usd",
                                        "product_data": {"name": product},
                                        "unit_amount": int(round(quoted * 100))},  # the HARD cap
                         "quantity": 1}],
            mode="payment",
            customer_email=email,
            success_url="https://aegisrefine.com/dashboard.html?paid=1",
            cancel_url="https://aegisrefine.com/new-order.html?canceled=1",
            metadata=meta,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"checkout_url": checkout_session.url}


def _job_brief(j: Job) -> dict:
    return {"id": j.id, "status": j.status, "input": j.input_file_path,
            "complexity_score": j.complexity_score, "estimated_cost": j.estimated_cost,
            "quote_amount": j.quote_amount, "revenue_collected": j.revenue_collected,
            "actual_cost": j.actual_cost, "service": getattr(j, "service", "refine"),
            "synth_topic": getattr(j, "synth_topic", None),
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
        "service": getattr(j, "service", "refine"),
    })
    return out


@router.get("/{job_id}/download")
async def download_dataset(job_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Download the produced dataset JSONL (refined OR synthesized) — from the in-DB copy."""
    j = db.query(Job).filter(Job.id == job_id).first()
    headers = {"Content-Disposition": f'attachment; filename="aegis-dataset-{job_id}.jsonl"'}
    if j and j.output_data:                          # DB copy survives redeploys
        return Response(content=j.output_data, media_type="application/x-ndjson", headers=headers)
    if j and j.output_file_path and os.path.exists(j.output_file_path):
        return FileResponse(j.output_file_path, media_type="application/x-ndjson",
                            filename=f"aegis-dataset-{job_id}.jsonl")
    raise HTTPException(status_code=404, detail="no dataset output yet")
