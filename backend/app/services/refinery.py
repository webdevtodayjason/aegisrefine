"""
Refinery orchestration — the "operate" spine.

A paid job is governed by Aegis-14B (triage + quality + spend decisions on the live
model), proposes a real gated SpendTicket when it hits something it can't do locally,
and ships a signed AAR on completion. This GLUES the verified services together; it is
governance + proposal, not an ETL — actual data transformation is out of scope here.
"""
from sqlalchemy.orm import Session
from app.models.job import Job
from app.services import agent, spend_service, aar_service
from app.services.audit import log_action


def _triage_task(job: Job, sample: str) -> str:
    return (f"Job {job.id}: refine the dataset at {job.input_file_path} into clean "
            f"ShareGPT/ChatML training data. Sample:\n{sample}\nScore it.")


def _quality_task(sample: str) -> str:
    return f"Assess this raw data sample for fine-tuning fitness:\n{sample}"


def _spend_task(job: Job, hard_doc: str) -> str:
    return (f"Mid-job edge case for job {job.id}: {hard_doc}. "
            f"Decide whether to call an external paid tool.")


def process_job(db: Session, job: Job, sample: str, hard_doc: str | None = None) -> dict:
    """Run Aegis-14B governance over a job. On an approved spend decision, arm the gate."""
    summary: dict = {}

    triage = agent.decide("triage", _triage_task(job, sample))
    log_action(db, job.id, "triage", "agent",
               {"complexity": triage.get("complexity"), "risk": triage.get("risk"),
                "can_run_locally": triage.get("can_run_locally")})
    try:
        job.complexity_score = float(triage.get("complexity") or 0)
    except (TypeError, ValueError):
        pass
    summary["triage"] = triage

    quality = agent.decide("quality", _quality_task(sample))
    log_action(db, job.id, "quality", "agent",
               {"quality_score": quality.get("quality_score"), "noise_level": quality.get("noise_level")})
    summary["quality"] = quality

    job.status = "processing"
    db.commit()

    if hard_doc:
        spend = agent.decide("spend", _spend_task(job, hard_doc))
        log_action(db, job.id, "spend_decision", "agent",
                   {"recommendation": spend.get("recommendation"), "tool": spend.get("tool"),
                    "est_cost_usd": spend.get("est_cost_usd")})
        summary["spend"] = spend
        if str(spend.get("recommendation", "")).lower().startswith("approve"):
            ticket = spend_service.create_spend_ticket(
                db, job.id, float(spend["est_cost_usd"]),
                f"{spend.get('tool', 'external tool')}: {spend.get('reason', '')}")
            job.status = "awaiting_approval"
            db.commit()
            summary["spend_ticket_id"] = ticket.id

    return summary


def complete_job(db: Session, job: Job, output: bytes, claim: str | None = None) -> dict:
    """Mark the job complete and issue its signed AAR certificate over the real output."""
    job.status = "completed"
    db.commit()
    claim = claim or f"refined job {job.id} into clean training data"
    return aar_service.issue_certificate(
        db, job.id, claim, output, "refinement governed by Aegis-14B; output hash committed as evidence")
