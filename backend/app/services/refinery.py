"""
Refinery orchestration — the "operate" spine.

A paid job is governed by Aegis-14B (triage + quality + spend decisions on the live
model), proposes a real gated SpendTicket when it hits something it can't do locally,
and ships a signed AAR on completion. Aegis-14B governs while the deterministic curate
engine produces the REAL cleaned dataset that the AAR then signs.
"""
import os
import json
from sqlalchemy.orm import Session
from app.models.job import Job
from app.services import agent, spend_service, aar_service, budget_service, escalation, storage, hermes_operator
from app.services.audit import log_action
from app.curate import engine as curate_engine


def _persist_outputs_to_r2(db: Session, job: Job, dataset_bytes: bytes, cert: dict) -> None:
    """R2 is the durable home for produced outputs too. Best-effort: the in-DB blob
    (job.output_data) and the signed AuditCertificate row stay the source of truth, so an R2
    hiccup never fails a job that already completed + signed. No-op when R2 isn't configured."""
    if not storage.enabled():
        return
    try:
        storage.put_bytes(storage.job_key(job.user_id, job.id, "dataset.jsonl"),
                          dataset_bytes, "application/x-ndjson")
        storage.put_bytes(storage.job_key(job.user_id, job.id, "certificate.aar.json"),
                          json.dumps(cert).encode("utf-8"), "application/json")
        log_action(db, job.id, "outputs_persisted_r2", "system", {"dataset_bytes": len(dataset_bytes)})
    except Exception as e:  # never crash a completed, signed job on a storage hiccup
        try:
            log_action(db, job.id, "r2_persist_error", "system", {"error": str(e)[:160]})
        except Exception:
            pass


def _triage_task(job: Job, sample: str) -> str:
    return (f"Job {job.id}: refine the dataset at {job.input_file_path} into clean "
            f"ShareGPT/ChatML training data. Sample:\n{sample}\n"
            f"Estimate complexity, risk, token count, noise, local processing steps, "
            f"and whether it can run locally.")


def _quality_task(sample: str) -> str:
    return (f"Assess this raw data sample for fine-tuning fitness. Score quality, "
            f"identify issues, estimate noise and clean row count, recommend output "
            f"format, and decide whether local processing is sufficient:\n{sample}")


def _spend_task(job: Job, hard_doc: str) -> str:
    return (f"Mid-job edge case for job {job.id}: {hard_doc}. "
            f"Decide whether to call an external paid tool, estimate cost, expected gain, "
            f"approval recommendation, and rationale.")


def _required_decide(db: Session, job: Job, kind: str, task: str) -> dict:
    """Aegis-14B governance is mandatory.

    If the DGX Spark model is unavailable, park the job in a truthful queued state.
    No heuristic substitute is allowed to make governance decisions for a paid job.
    """
    try:
        return agent.decide(kind, task)
    except Exception as e:
        job.status = "queued"
        db.commit()
        log_action(db, job.id, "aegis_temporarily_queued", "system",
                   {"stage": kind, "error": str(e)[:160]})
        raise agent.AegisTemporarilyQueued(
            f"Aegis-14B is temporarily queued during {kind}; job is waiting for DGX Spark governance"
        ) from e


def process_job(db: Session, job: Job, sample: str, hard_doc: str | None = None) -> dict:
    """Run Aegis-14B governance over a job. On an approved spend decision, arm the gate."""
    summary: dict = {}

    triage = _required_decide(db, job, "triage", _triage_task(job, sample))
    log_action(db, job.id, "triage", "agent",
               {"complexity": triage.get("complexity"), "risk": triage.get("risk"),
                "can_run_locally": triage.get("can_run_locally")})
    try:
        job.complexity_score = float(triage.get("complexity") or 0)
    except (TypeError, ValueError):
        pass
    summary["triage"] = triage

    quality = _required_decide(db, job, "quality", _quality_task(sample))
    log_action(db, job.id, "quality", "agent",
               {"quality_score": quality.get("quality_score"), "noise_level": quality.get("noise_level")})
    summary["quality"] = quality

    # real paid escalation — agent reaches off free local Aegis-14B ONLY when it flags a hard
    # evaluation AND a provider key exists AND there's a cap to spend against. No key -> stays local.
    try:
        qs = float(quality.get("quality_score") or 1)
        qs = qs / 10 if qs > 1 else qs
        hard = (not triage.get("can_run_locally", True)) or qs < 0.6
        model = escalation.pick_model("hard/reasoning") if (hard and job.approved_cap) else None
        if model:
            decision, ticket = budget_service.request_spend(
                db, job, provider=model, units=escalation.estimate_cost(model),
                reason="hard evaluation: escalate to a more capable model",
                capability="inference", source=escalation.source(model))
            if decision != "gated":
                res = escalation.escalate([{"role": "user", "content": _quality_task(sample)}], model=model)
                if res:
                    spend_service.execute_spend_ticket(db, ticket.id, actual_amount=res["cost_usd"])
                    log_action(db, job.id, "escalated_inference", "agent",
                               {"provider": res["provider"], "model": res["model"], "cost_usd": res["cost_usd"]})
                    summary["escalation"] = {"provider": res["provider"], "cost_usd": res["cost_usd"]}
    except Exception as e:  # a provider hiccup must never crash the job
        summary["escalation_error"] = str(e)[:200]

    job.status = "processing"
    db.commit()

    # deterministic curation engine produces the REAL cleaned dataset (the bytes the AAR will sign)
    try:
        result = curate_engine.run(job.input_file_path)
        job.output_file_path = result["output_path"]
        db.commit()
        log_action(db, job.id, "curated", "system", result["stats"])
        summary["stats"] = result["stats"]
        if int(result["stats"].get("rows_out") or 0) <= 0:
            reason = "no usable records produced"
            if result.get("needs_ocr"):
                reason = "source needs OCR before curation"
            summary["curation_error"] = reason
            job.status = "failed"
            db.commit()
            log_action(db, job.id, "curation_error", "system", {"error": reason})
    except Exception as e:  # surface honestly, never fake a result
        summary["curation_error"] = str(e)
        log_action(db, job.id, "curation_error", "system", {"error": str(e)[:200]})
        job.status = "failed"
        db.commit()

    if hard_doc:
        spend = _required_decide(db, job, "spend", _spend_task(job, hard_doc))
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


def complete_job(db: Session, job: Job, output: bytes | None = None, claim: str | None = None,
                 provenance: dict | None = None) -> dict:
    """Issue the signed AAR over the REAL produced output (curated OR synthesized).

    Prefers the bytes the engine produced (job.output_file_path); the client-supplied `output`
    is only a transitional fallback. `provenance` (synthesis stats) is merged into the cert's
    guarantees. The claim carries real, re-checkable numbers.
    """
    from app.services import budget_service
    out_path = getattr(job, "output_file_path", None)
    guarantees = None
    if out_path and os.path.exists(out_path):
        output = open(out_path, "rb").read()
        v = curate_engine.verify_output(out_path)
        claim = claim or (f"refined job {job.id}: {v['rows']} clean rows, PII residual "
                          f"{v['pii_residual']}, dupes residual {v['dupes_residual']}, "
                          f"schema {'valid' if v['schema_valid'] else 'INVALID'}")
        evidence = "Aegis-14B-governed local curation; signed bytes ARE the produced dataset; checks re-runnable"
        guarantees = {"rows": v["rows"], "pii_residual": v["pii_residual"],
                      "dupes_residual": v["dupes_residual"], "schema_valid": v["schema_valid"],
                      "output_format": "sharegpt"}
    else:
        output = output or b""
        claim = claim or f"refined job {job.id} into clean training data"
        evidence = "refinement governed by Aegis-14B; output hash committed as evidence"

    # persist the produced dataset IN-DB so download + re-verify survive container redeploys
    job.output_data = (output or b"").decode("utf-8", "replace")

    # the agent's audited books for this job (the leaderboard's per-job P&L)
    economics = None
    if job.quote_amount is not None:
        from app.models.spend_ticket import SpendTicket
        L = budget_service.ledger(db, job)
        spent = float(L["executed"]) or float(L["committed"])
        cap = float(L["cap"])
        fee = round(job.quote_amount * 0.029 + 0.30, 2)
        margin = round(job.quote_amount - spent - fee, 2)
        tickets = db.query(SpendTicket).filter(
            SpendTicket.job_id == job.id, SpendTicket.status.in_(["approved", "executed"])).all()
        providers = [{"name": t.provider,
                      "cost_usd": round(float(t.actual_amount if t.actual_amount is not None else t.amount), 6),
                      "kind": t.kind, "source": t.cost_source} for t in tickets if t.provider]
        economics = {
            "currency": "usd", "quoted_usd": job.quote_amount, "cap_usd": cap,
            "revenue_collected_usd": job.revenue_collected or job.quote_amount,
            "spent_usd": round(spent, 6), "stripe_fee_usd": fee, "margin_usd": margin,
            "realized_margin_pct": round(100 * margin / job.quote_amount, 1) if job.quote_amount else 0.0,
            "target_margin_pct": round((job.target_margin_pct or 0.65) * 100, 1),
            "cap_respected": spent <= cap + 0.005,
            "providers": providers,
        }
        job.actual_cost = round(spent, 6)

    if provenance:
        guarantees = {**(guarantees or {}), "synthesis": provenance}

    job.status = "completed"
    db.commit()
    cert = aar_service.issue_certificate(db, job.id, claim, output, evidence,
                                         economics=economics, guarantees=guarantees)
    # push the produced dataset + signed cert to R2 too (durable beyond the container fs / DB blob).
    # Covers BOTH refine and synthesis — the synth runner completes through this same path.
    _persist_outputs_to_r2(db, job, output or b"", cert)
    try:
        from app.models.audit_log import AuditLog
        already_sent = False
        rows = db.query(AuditLog).filter(
            AuditLog.job_id == job.id,
            AuditLog.action == "hermes_operator_decision",
        ).all()
        for row in rows:
            details = row.details or {}
            if details.get("phase") == "completed" and details.get("telegram_sent") is True:
                already_sent = True
                break
        if already_sent:
            return cert
        hermes_operator.dispatch_job(
            db,
            job,
            phase="completed",
            receipt={"certificate_id": cert.get("id"), "aar": f"/jobs/{job.id}/aar"},
        )
    except Exception:
        pass
    return cert
