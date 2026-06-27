from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.job_service import create_paid_job
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
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
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
        meta = session.get("metadata") or {}
        dataset_url = meta.get("dataset_url")
        email = meta.get("email") or (session.get("customer_details") or {}).get("email")
        if not dataset_url or not email:
            raise HTTPException(status_code=400, detail="missing dataset_url/email in checkout session")
        job = create_paid_job(db, dataset_url, email)
        return {"received": True, "job_id": job.id}

    return {"received": True}
