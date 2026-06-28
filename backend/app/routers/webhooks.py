from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.job_service import create_paid_job
import stripe
import json
import os


def _auto_run_job(job_id: int):
    """Payment kicks off the whole pipeline by itself — the autonomous business: the agent
    curates the dataset and signs its certificate without a human in the loop."""
    from app.database import SessionLocal
    from app.models.job import Job
    from app.services import refinery
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return
        if getattr(job, "service", "refine") == "synthesis":
            from app.synth.runner import run_synth_job
            run_synth_job(db, job, topic=job.synth_topic or "",
                          target_kept=int(job.synth_target_kept or 50),
                          reference=job.synth_reference or "")
        else:
            refinery.process_job(db, job, sample="auto-run on payment")
            refinery.complete_job(db, job)
        # honest "we'll email you" — best-effort, after the deliverable is signed
        try:
            from app.services.notify import email_job_done
            from app.models.user import User
            u = db.query(User).filter(User.id == job.user_id).first()
            if u:
                email_job_done(u.email, job.id, getattr(job, "service", "refine"))
        except Exception:
            pass
    except Exception:
        pass  # the job stays at its last good state; governance/curation log the reason
    finally:
        db.close()

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
        meta = session.get("metadata") or {}
        service = meta.get("service") or "refine"
        email = meta.get("email") or (session.get("customer_details") or {}).get("email")
        quoted = float(meta.get("quoted_usd") or 0) or None
        # defense in depth: Stripe must have charged EXACTLY the quoted cap
        amount_total = session.get("amount_total")
        if quoted is not None and amount_total is not None and int(amount_total) != int(round(quoted * 100)):
            raise HTTPException(status_code=400, detail="amount_total does not match the quoted cap")
        margin = float(meta.get("target_margin_pct") or 0.65)
        if service == "synthesis":
            if not email or not meta.get("topic"):
                raise HTTPException(status_code=400, detail="missing topic/email in synthesis session")
            job = create_paid_job(db, None, email, quote_amount=quoted, target_margin_pct=margin,
                                  service="synthesis",
                                  synth={"topic": meta.get("topic"), "target_kept": meta.get("target_kept"),
                                         "reference": meta.get("reference")})
        else:
            # the SOURCE — an https URL OR an upload handle (R2 key / temp path); short either way,
            # so it fits Stripe's ~500-char metadata limit. It becomes job.input_file_path verbatim.
            dataset_url = meta.get("dataset_url")
            if not dataset_url or not email:
                raise HTTPException(status_code=400, detail="missing dataset_url/email in checkout session")
            job = create_paid_job(db, dataset_url, email, quote_amount=quoted, target_margin_pct=margin)
        background.add_task(_auto_run_job, job.id)   # pay -> the agent runs the pipeline itself
        return {"received": True, "job_id": job.id}

    return {"received": True}
