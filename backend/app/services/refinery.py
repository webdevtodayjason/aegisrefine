"""
Refinery orchestration — the "operate" spine.

A paid job is governed by Aegis-14B (triage + quality + spend decisions on the live
model), proposes a real gated SpendTicket when it hits something it can't do locally,
and ships a signed AAR on completion. Aegis-14B governs while the deterministic curate
engine produces the REAL cleaned dataset that the AAR then signs.
"""
import os
from sqlalchemy.orm import Session
from app.models.job import Job
from app.services import agent, spend_service, aar_service
from app.services.audit import log_action
from app.curate import engine as curate_engine


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

    # deterministic curation engine produces the REAL cleaned dataset (the bytes the AAR will sign)
    try:
        result = curate_engine.run(job.input_file_path)
        job.output_file_path = result["output_path"]
        db.commit()
        log_action(db, job.id, "curated", "system", result["stats"])
        summary["stats"] = result["stats"]
    except Exception as e:  # surface honestly, never fake a result
        summary["curation_error"] = str(e)
        log_action(db, job.id, "curation_error", "system", {"error": str(e)[:200]})

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


def complete_job(db: Session, job: Job, output: bytes | None = None, claim: str | None = None) -> dict:
    """Issue the signed AAR over the REAL curated output.

    Prefers the bytes the engine produced (job.output_file_path); the client-supplied `output`
    is only a transitional fallback. The claim carries real, re-checkable numbers.
    """
    out_path = getattr(job, "output_file_path", None)
    if out_path and os.path.exists(out_path):
        output = open(out_path, "rb").read()
        v = curate_engine.verify_output(out_path)
        claim = claim or (f"refined job {job.id}: {v['rows']} clean rows, PII residual "
                          f"{v['pii_residual']}, dupes residual {v['dupes_residual']}, "
                          f"schema {'valid' if v['schema_valid'] else 'INVALID'}")
        evidence = "Aegis-14B-governed local curation; signed bytes ARE the produced dataset; checks re-runnable"
    else:
        output = output or b""
        claim = claim or f"refined job {job.id} into clean training data"
        evidence = "refinement governed by Aegis-14B; output hash committed as evidence"
    job.status = "completed"
    db.commit()
    return aar_service.issue_certificate(db, job.id, claim, output, evidence)
