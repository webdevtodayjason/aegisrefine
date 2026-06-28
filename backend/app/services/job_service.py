"""
Job lifecycle helpers.

Jobs are created only AFTER a paid Stripe Checkout (via the webhook), never from an
unpaid client call — that's what closes the IDOR (client no longer supplies user_id)
and the path-injection hole (dataset input is a validated https URL, not a raw path).
"""

from urllib.parse import urlparse
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
    """A job source can be an uploaded-file HANDLE instead of an https URL: an R2 key
    (prefix 'users/') or, in local/dev where R2 is off, an absolute temp path. Both are
    server-generated and travel inside the HMAC-signed quote token, so they bypass the
    https-URL gate (which exists only to stop client-supplied path injection)."""
    s = source or ""
    return s.startswith("users/") or s.startswith("/")


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
                    service: str = "refine", synth: dict | None = None) -> Job:
    """Create the Job for a completed payment and record it on the audit trail.
    Identity comes from the Stripe-authenticated session (email), never the client.
    When a quote was accepted, the cap becomes the job's hard spend ceiling.
    `service`='synthesis' carries the generate/augment params in `synth`.
    `dataset_url` is the job SOURCE — an https URL OR an upload handle (R2 key / temp path);
    either way it lands in job.input_file_path, which engine.run knows how to read.
    """
    user = get_or_create_user(db, email)
    job = Job(user_id=user.id, status="pending", input_file_path=dataset_url or "(synthesis)")
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
