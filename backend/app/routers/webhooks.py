from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.job_runner import auto_run_job
from app.services.job_service import create_paid_job_from_checkout_session
import stripe
import json
import os


try:
    from stripe import SignatureVerificationError
except ImportError:  # older stripe-python
    from stripe.error import SignatureVerificationError

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


@router.post("/stripe")
async def stripe_webhook(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Stripe-authenticated entry point. A verified checkout.session.completed is the
    ONLY thing that creates a Job — payment, not the client, drives job creation."""
    payload = await request.body()
    sig = request.headers.get("Stripe-Signature")
    try:
        stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
    except (ValueError, SignatureVerificationError):
        raise HTTPException(status_code=400, detail="signature verification failed")

    # Read fields from the now-verified raw payload (plain dict, version-robust).
    event = json.loads(payload)
    if event.get("type") == "checkout.session.completed":
        session = event["data"]["object"]
        job, created = create_paid_job_from_checkout_session(db, session)
        if created:
            background.add_task(auto_run_job, job.id)   # pay -> the agent runs the pipeline itself
        return {"received": True, "job_id": job.id}

    return {"received": True}
