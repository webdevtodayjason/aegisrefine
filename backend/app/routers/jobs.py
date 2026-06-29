from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Request, BackgroundTasks
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.job import Job
from app.models.spend_ticket import SpendTicket
from app.models.audit_certificate import AuditCertificate
from app.services.job_service import (
    validate_https_url,
    is_upload_handle,
    validate_upload_handle,
    create_paid_job_from_checkout_session,
    checkout_session_to_dict,
)
from app.services.auth import require_user
from app.services import quote_service, storage
from app.models.user import User
import stripe
import os
import time
import tempfile

router = APIRouter(prefix="/jobs", tags=["jobs"])

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # ~25MB cap; bigger -> 413 (and route a human quote)


class QuoteRequest(BaseModel):
    dataset_url: str | None = None      # an https dataset URL ...
    upload_handle: str | None = None    # ... OR a handle from POST /jobs/upload (R2 key / temp path)
    email: str | None = None


class JobRequest(BaseModel):
    quote_token: str


class CheckoutSyncRequest(BaseModel):
    session_id: str


class SynthQuoteRequest(BaseModel):
    topic: str
    target_kept: int = 100
    reference: str | None = None   # augment: an https dataset URL to ground generation in; empty = from-seed
    upload_handle: str | None = None


def _checkout_return_urls(request: Request) -> tuple[str, str]:
    """Build return URLs for the browser surface that started Stripe Checkout."""
    configured = os.getenv("CHECKOUT_RETURN_BASE_URL") or os.getenv("APP_BASE_URL")
    origin = request.headers.get("origin")
    base = (configured or origin or "https://aegisrefine.com").rstrip("/")
    local_next = base.startswith("http://localhost:") or base.startswith("http://127.0.0.1:")
    dashboard = os.getenv("CHECKOUT_SUCCESS_PATH") or ("/dashboard" if local_next else "/dashboard.html")
    new_order = os.getenv("CHECKOUT_CANCEL_PATH") or ("/new-order" if local_next else "/new-order.html")
    success_url = f"{base}{dashboard}?paid=1&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{base}{new_order}?canceled=1"
    return success_url, cancel_url


@router.post("/upload")
async def upload(file: UploadFile = File(...), user: User = Depends(require_user)):
    """Stash a customer-supplied dataset file and return a HANDLE the client passes to /quote
    (as an alternative to a dataset_url). The handle is the R2 key when storage is configured
    (durable across redeploys) or a local temp path in dev. The bytes never live only on a
    non-durable container path in prod. Cap ~25MB -> 413 (those route to a human quote)."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)   # read at most cap+1 so we bound memory
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large (25MB max)")
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    filename = file.filename or "dataset"
    content_type = file.content_type or "application/octet-stream"
    if storage.enabled():
        handle = storage.upload_key(user.id, filename)
        storage.put_bytes(handle, data, content_type)
    else:  # local/dev fallback — a temp path used as the handle
        safe = "".join(c for c in filename if c.isalnum() or c in "._-")[:60] or "dataset"
        fd, handle = tempfile.mkstemp(prefix="aegis-upload-", suffix="-" + safe)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    return {"handle": handle, "filename": filename, "size": len(data), "content_type": content_type}


@router.post("/quote")
async def quote(req: QuoteRequest, user: User = Depends(require_user)):
    """Aegis-14B prices the dataset into a flat, CAPPED quote. No Job, no charge yet.
    The private cost estimate is NEVER returned — only the capped price the customer pays.
    Source is EITHER an uploaded-file handle OR a validated https URL (handle takes precedence)."""
    if req.upload_handle:
        source = validate_upload_handle(req.upload_handle, user.id)
    elif req.dataset_url:
        source = validate_https_url(req.dataset_url)
    else:
        raise HTTPException(status_code=400, detail="provide a dataset_url or an upload_handle")
    try:
        q = quote_service.quote_job(source, req.email or user.email, int(time.time()))
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
    reference = (req.upload_handle or req.reference or "").strip()
    if reference:
        if is_upload_handle(reference):
            reference = validate_upload_handle(reference, user.id)
        else:
            validate_https_url(reference)
    q = quote_service.quote_synth(tk)
    token = quote_service.sign_synth_token(q, req.topic.strip(), tk, reference, user.email, int(time.time()))
    return {"quote_usd": q["quote_usd"], "target_kept": tk, "target_margin_pct": q["target_margin_pct"],
            "service": "synthesis", "mode": "augment" if reference else "from-seed", "token": token}


@router.post("/")
async def create_job(req: JobRequest, request: Request, user: User = Depends(require_user)):
    """Accept a signed quote (refine OR synthesis) and open a Stripe Checkout for EXACTLY the
    capped amount. No Job is created here — the webhook creates it AFTER payment (identity from Stripe)."""
    payload = quote_service.verify_quote_token(req.quote_token, int(time.time()))
    if not payload:
        raise HTTPException(status_code=400, detail="quote expired or invalid — please re-quote")
    quoted = float(payload["q"])
    email = payload["email"]
    if email.lower() != user.email.lower() and not user.is_admin:
        raise HTTPException(status_code=403, detail="quote belongs to a different user")
    if payload.get("service") == "synthesis":
        product = "Aegis Dataset Synthesis"
        meta = {"service": "synthesis", "email": email, "quoted_usd": f"{quoted:.2f}",
                "target_margin_pct": "0.65", "topic": (payload.get("topic") or "")[:480],
                "target_kept": str(payload.get("target_kept") or 0),
                "reference": (payload.get("reference") or "")[:480]}
    else:
        # the signed token binds the source under "url" — an https URL OR an upload handle
        # (R2 key / temp path). The HMAC already guarantees integrity, so only re-validate URLs
        # (the gate exists to stop client-supplied path injection, which can't apply to a handle
        # the server itself minted). The source is short either way — well within Stripe's metadata cap.
        source = payload["url"]
        if not is_upload_handle(source):
            validate_https_url(source)
        else:
            validate_upload_handle(source, user.id)
        product = "Aegis Dataset Refinement"
        meta = {"service": "refine", "dataset_url": source, "email": email,
                "quoted_usd": f"{quoted:.2f}", "target_margin_pct": "0.65"}
    success_url, cancel_url = _checkout_return_urls(request)
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price_data": {"currency": "usd",
                                        "product_data": {"name": product},
                                        "unit_amount": int(round(quoted * 100))},  # the HARD cap
                         "quantity": 1}],
            mode="payment",
            customer_email=email,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=meta,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"checkout_url": checkout_session.url}


@router.post("/checkout/sync")
async def sync_checkout(req: CheckoutSyncRequest, background: BackgroundTasks,
                        db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Local/browser return-page reconciliation for a real Stripe Checkout payment.

    Stripe webhooks remain the production source of truth. Locally, when the Stripe CLI is
    not forwarding events to localhost, this verifies the hosted Checkout Session directly
    with Stripe before creating the same paid Job the webhook would create.
    """
    sid = (req.session_id or "").strip()
    if not sid.startswith("cs_"):
        raise HTTPException(status_code=400, detail="invalid checkout session id")
    try:
        session = stripe.checkout.Session.retrieve(sid)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"could not verify checkout session: {e}")
    session = checkout_session_to_dict(session)
    if session.get("payment_status") != "paid":
        raise HTTPException(status_code=402, detail="checkout session is not paid")
    meta = session.get("metadata") or {}
    email = (meta.get("email") or (session.get("customer_details") or {}).get("email") or "").lower()
    if email != user.email.lower() and not user.is_admin:
        raise HTTPException(status_code=403, detail="checkout session belongs to a different user")
    job, created = create_paid_job_from_checkout_session(db, session)
    if created:
        from app.services.job_runner import auto_run_job
        background.add_task(auto_run_job, job.id)
    return {"job_id": job.id, "created": created, "status": job.status}


def _job_brief(j: Job) -> dict:
    return {"id": j.id, "status": j.status, "input": j.input_file_path,
            "complexity_score": j.complexity_score, "estimated_cost": j.estimated_cost,
            "quote_amount": j.quote_amount, "revenue_collected": j.revenue_collected,
            "actual_cost": j.actual_cost, "service": getattr(j, "service", "refine"),
            "synth_topic": getattr(j, "synth_topic", None),
            "created_at": j.created_at.isoformat() if j.created_at else None}


@router.get("/")
async def list_jobs(limit: int = 50, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Recent jobs, newest first (Dashboard) — scoped to the signed-in account (admins see all)."""
    q = db.query(Job)
    if not user.is_admin:
        q = q.filter(Job.user_id == user.id)
    rows = q.order_by(Job.id.desc()).limit(max(1, min(limit, 200))).all()
    return [_job_brief(j) for j in rows]


@router.get("/{job_id}")
async def get_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """One job + its spend tickets + certificate (OrderDetail / Certificate)."""
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j or (not user.is_admin and j.user_id != user.id):
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
    if j and not user.is_admin and j.user_id != user.id:
        raise HTTPException(status_code=404, detail="no dataset output yet")
    headers = {"Content-Disposition": f'attachment; filename="aegis-dataset-{job_id}.jsonl"'}
    if j and j.output_data:                          # DB copy survives redeploys
        data = j.output_data.encode("utf-8")
        if data.strip():
            return Response(content=data, media_type="application/x-ndjson", headers=headers)
    if j and j.output_file_path and os.path.exists(j.output_file_path):
        with open(j.output_file_path, "rb") as f:
            if not f.read().strip():
                raise HTTPException(status_code=404, detail="no dataset output yet")
        return FileResponse(j.output_file_path, media_type="application/x-ndjson",
                            filename=f"aegis-dataset-{job_id}.jsonl")
    raise HTTPException(status_code=404, detail="no dataset output yet")
