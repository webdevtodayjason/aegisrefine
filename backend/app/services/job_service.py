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


def get_or_create_user(db: Session, email: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user
    user = User(email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_paid_job(db: Session, dataset_url: str, email: str) -> Job:
    """Create the Job for a completed payment and record it on the audit trail.
    Identity comes from the Stripe-authenticated session (email), never the client.
    """
    user = get_or_create_user(db, email)
    job = Job(user_id=user.id, status="pending", input_file_path=dataset_url)
    db.add(job)
    db.commit()
    db.refresh(job)
    log_action(db, job.id, "job_created", "system", {"dataset_url": dataset_url, "email": email})
    return job
