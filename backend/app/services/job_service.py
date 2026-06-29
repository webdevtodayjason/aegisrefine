"""
Job lifecycle helpers.

Jobs are created only AFTER a paid Stripe Checkout (via the webhook), never from an
unpaid client call — that's what closes the IDOR (client no longer supplies user_id)
and the path-injection hole (dataset input is a validated https URL, not a raw path).
"""

from urllib.parse import urlparse
import os
import tempfile
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.job import Job
from app.services.audit import log_action


def validate_https_url(url: str) -> str:
    """Dataset input must be an https URL — no raw filesystem paths, no other schemes."""
    parsed = urlparse(url or "")
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(status_code=400, detail="dataset_url must be an https:// URL")
    return url


def is_upload_handle(source: str) -> bool:
    """A job source can be an uploaded-file HANDLE instead of an https URL.

    Handles are deliberately narrow: either an R2 upload key (`users/{id}/uploads/...`)
    or a local temp file minted by POST /jobs/upload (`/tmp/.../aegis-upload-*`).
    """
    s = source or ""
    if s.startswith("users/") and "/uploads/" in s:
        return True
    if os.path.isabs(s):
        tmp = os.path.realpath(tempfile.gettempdir())
        real = os.path.realpath(s)
        return real.startswith(tmp + os.sep) and os.path.basename(real).startswith("aegis-upload-")
    return False


def validate_upload_handle(source: str, user_id: int) -> str:
    """Ensure a client-supplied upload handle was minted by this app and belongs to this user."""
    s = source or ""
    if not is_upload_handle(s):
        raise HTTPException(status_code=400, detail="invalid upload handle")
    if s.startswith("users/"):
        prefix = f"users/{user_id}/uploads/"
        if not s.startswith(prefix):
            raise HTTPException(status_code=400, detail="upload handle does not belong to this user")
    return s


def get_or_create_user(db: Session, email: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user
    user = User(email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_paid_job(db: Session, dataset_url: str, email: str,
                    quote_amount: float | None = None, target_margin_pct: float = 0.65,
                    service: str = "refine", synth: dict | None = None,
                    stripe_checkout_session_id: str | None = None) -> Job:
    """Create the Job for a completed payment and record it on the audit trail.
    Identity comes from the Stripe-authenticated session (email), never the client.
    When a quote was accepted, the cap becomes the job's hard spend ceiling.
    `service`='synthesis' carries the generate/augment params in `synth`.
    `dataset_url` is the job SOURCE — an https URL OR an upload handle (R2 key / temp path);
    either way it lands in job.input_file_path, which engine.run knows how to read.
    """
    if stripe_checkout_session_id:
        existing = db.query(Job).filter(Job.stripe_checkout_session_id == stripe_checkout_session_id).first()
        if existing:
            return existing

    user = get_or_create_user(db, email)
    job = Job(user_id=user.id, status="pending", input_file_path=dataset_url or "(synthesis)")
    job.stripe_checkout_session_id = stripe_checkout_session_id
    job.service = service
    if synth:
        job.synth_topic = synth.get("topic")
        job.synth_target_kept = int(synth.get("target_kept") or 0) or None
        job.synth_reference = synth.get("reference") or ""
    if quote_amount is not None:
        from datetime import datetime, timezone
        job.quote_amount = quote_amount
        job.approved_cap = quote_amount
        job.revenue_collected = quote_amount
        job.quote_status = "accepted"
        job.target_margin_pct = target_margin_pct
        job.quote_accepted_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()
    db.refresh(job)
    log_action(db, job.id, "job_created", "system",
               {"dataset_url": dataset_url, "email": email, "quote_amount": quote_amount})
    return job


def checkout_session_to_dict(session) -> dict:
    """Normalize stripe-python objects and test doubles into plain dictionaries."""
    if isinstance(session, dict):
        return session
    for method in ("to_dict_recursive", "to_dict"):
        try:
            fn = object.__getattribute__(session, method)
            return fn()
        except Exception:
            pass
    try:
        return dict(session)
    except Exception:
        pass
    return {
        "id": getattr(session, "id", None),
        "payment_status": getattr(session, "payment_status", None),
        "amount_total": getattr(session, "amount_total", None),
        "metadata": getattr(session, "metadata", None) or {},
        "customer_details": getattr(session, "customer_details", None) or {},
    }


def create_paid_job_from_checkout_session(db: Session, session) -> tuple[Job, bool]:
    """Create exactly one paid Job from a Stripe Checkout Session-like object.

    Used by both the signed webhook and the local browser return-page sync. The caller is
    responsible for verifying the session came from Stripe; this helper enforces amount
    consistency and idempotency.
    """
    session = checkout_session_to_dict(session)
    session_id = session.get("id")
    if session_id:
        existing = db.query(Job).filter(Job.stripe_checkout_session_id == session_id).first()
        if existing:
            return existing, False

    meta = session.get("metadata") or {}
    service = meta.get("service") or "refine"
    email = meta.get("email") or (session.get("customer_details") or {}).get("email")
    quoted = float(meta.get("quoted_usd") or 0) or None
    amount_total = session.get("amount_total")
    if quoted is not None and amount_total is not None and int(amount_total) != int(round(quoted * 100)):
        raise HTTPException(status_code=400, detail="amount_total does not match the quoted cap")
    margin = float(meta.get("target_margin_pct") or 0.65)

    if service == "synthesis":
        if not email or not meta.get("topic"):
            raise HTTPException(status_code=400, detail="missing topic/email in synthesis session")
        job = create_paid_job(
            db, None, email, quote_amount=quoted, target_margin_pct=margin,
            service="synthesis",
            synth={"topic": meta.get("topic"), "target_kept": meta.get("target_kept"),
                   "reference": meta.get("reference")},
            stripe_checkout_session_id=session_id,
        )
    else:
        dataset_url = meta.get("dataset_url")
        if not dataset_url or not email:
            raise HTTPException(status_code=400, detail="missing dataset_url/email in checkout session")
        job = create_paid_job(
            db, dataset_url, email, quote_amount=quoted, target_margin_pct=margin,
            stripe_checkout_session_id=session_id,
        )
    return job, True
