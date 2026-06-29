"""Background execution for paid jobs."""


def run_due_jobs(db, *, limit: int = 5) -> dict:
    """Retry paid jobs that still need the worker.

    Aegis-14B outages park jobs as `queued`, while deploy restarts can leave newly
    paid jobs in `pending`. This function is safe for a scheduler/worker to call
    repeatedly without relying on browser clicks.
    """
    from app.models.job import Job

    rows = (
        db.query(Job)
        .filter(Job.status.in_(["pending", "queued"]))
        .order_by(Job.id)
        .limit(max(1, min(int(limit or 5), 25)))
        .all()
    )
    started = []
    for job in rows:
        started.append(job.id)
        auto_run_job(job.id)
    return {"scanned": len(rows), "started": started}


def auto_run_job(job_id: int):
    """Payment kicks off the pipeline by itself.

    Kept outside the webhook router so the signed webhook and the verified local
    Checkout-session sync can share the same behavior.
    """
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

            run_synth_job(
                db,
                job,
                topic=job.synth_topic or "",
                target_kept=int(job.synth_target_kept or 50),
                reference=job.synth_reference or "",
            )
        else:
            summary = refinery.process_job(db, job, sample="auto-run on payment")
            if summary.get("curation_error") or not job.output_file_path:
                return
            refinery.complete_job(db, job)
        try:
            from app.models.user import User
            from app.services.notify import email_job_done

            u = db.query(User).filter(User.id == job.user_id).first()
            if u:
                email_job_done(u.email, job.id, getattr(job, "service", "refine"))
        except Exception:
            pass
    except Exception:
        pass
    finally:
        db.close()
