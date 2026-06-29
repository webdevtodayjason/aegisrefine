from app.models.job import Job
from app.services import job_runner


def test_run_due_jobs_retries_pending_and_queued_jobs(db, user, monkeypatch):
    db.query(Job).filter(Job.status.in_(["pending", "queued"])).update({"status": "failed"})
    db.commit()
    pending = Job(user_id=user.id, status="pending", input_file_path="https://example.com/p.jsonl")
    queued = Job(user_id=user.id, status="queued", input_file_path="https://example.com/a.jsonl")
    processing = Job(user_id=user.id, status="processing", input_file_path="https://example.com/b.jsonl")
    db.add_all([pending, queued, processing])
    db.commit()
    db.refresh(pending)
    db.refresh(queued)
    db.refresh(processing)

    called = []
    monkeypatch.setattr(job_runner, "auto_run_job", lambda job_id: called.append(job_id))

    out = job_runner.run_due_jobs(db, limit=10)

    assert out == {"scanned": 2, "started": [pending.id, queued.id]}
    assert called == [pending.id, queued.id]
