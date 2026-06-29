"""Run a synthesis job end-to-end: generate -> write labeled-synthetic JSONL -> meter the real
spend on the ledger -> sign a provenance certificate. Reuses the curation cert path (the synth
output is ShareGPT JSONL, so verify_output re-checks PII/dupes/schema too)."""
import os

from app.synth.loop import synthesize
from app.curate.format import write_jsonl
from app.services import budget_service, spend_service, quote_service
from app.services.audit import log_action
from app.services.refinery import complete_job

OUT_DIR = os.environ.get("SYNTH_OUT_DIR", "/tmp/aegis-synth")


SYNTH_DEMO_CAP = int(os.environ.get("SYNTH_DEMO_CAP", "8"))  # bound rows so a job finishes in minutes


def run_synth_job(db, job, *, topic, target_kept=10, reference="", roles=None,
                  real_rows=0, _call=None):
    """`reference` empty -> generate-from-seed; non-empty -> augment (ground in a curated set).
    `real_rows` is the curated-input count for augment mode (0 for from-seed)."""
    target_kept = min(int(target_kept or SYNTH_DEMO_CAP), SYNTH_DEMO_CAP)
    job.status = "processing"  # surface that work has started (else the UI shows 'pending')
    db.commit()
    cap = float(budget_service.ledger(db, job)["cap"]) if job.quote_amount else 1.0
    reference_text = reference or ""
    if reference:
        try:
            features = quote_service._sample_features(reference)
            reference_text = features["sample_text"]
            real_rows = real_rows or int(features["n_records"] or 0)
        except Exception:
            # Keep the job moving, but provenance will show zero real rows if the reference
            # could not be read at run time.
            reference_text = reference
    res = synthesize(topic=topic, target_kept=target_kept, reference=reference_text,
                     roles=roles, cap_usd=cap * 0.8, _call=_call)  # buffer keeps cap_respected true
    if int(res.get("kept_count") or 0) <= 0:
        job.status = "failed"
        db.commit()
        log_action(db, job.id, "synthesis_failed", "system",
                   {"reason": "no synthetic rows kept", "candidates": res.get("candidates_generated", 0)})
        raise RuntimeError("synthesis produced zero kept rows")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"synth-job-{job.id}.jsonl")
    write_jsonl(res["kept"], out_path)
    job.output_file_path = out_path

    # meter the real spend on the ledger — one ticket; per-model detail lives in the provenance
    if res["spent_usd"] > 0:
        models_used = ",".join(sorted(set(res["models"].values())))
        t = spend_service.create_spend_ticket(db, job.id, res["spent_usd"], f"synthesis: {models_used}")
        t.provider = f"synthesis({models_used})"
        t.kind = "synthesis"
        db.commit()
        spend_service.authorize_within_cap(db, t.id, job)   # autonomous, pre-authorized by the accepted quote
        spend_service.execute_spend_ticket(db, t.id, actual_amount=res["spent_usd"])

    provenance = {
        "method": "AutoData Δ-filter: keep strong-solves ∧ weak-fails",
        "mode": "augment" if reference else "from-seed",
        "candidates_generated": res["candidates_generated"],
        "kept_synthetic": res["kept_count"],
        "yield_pct": res["yield_pct"],
        "models": res["models"],
        "by_model_usd": res["by_model_usd"],
        "spent_usd": res["spent_usd"],
        "real_rows": real_rows,
        "synthetic_rows": res["kept_count"],
        "labeled_synthetic": True,
    }
    claim = (f"synthesized job {job.id}: {res['kept_count']} high-value synthetic rows kept from "
             f"{res['candidates_generated']} candidates ({res['yield_pct']}% yield), spend "
             f"${res['spent_usd']}, all rows labeled synthetic")
    return complete_job(db, job, claim=claim, provenance=provenance)
