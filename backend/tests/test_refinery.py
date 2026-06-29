from app.models.job import Job
from app.services import refinery, agent


def test_job_queues_when_model_unreachable(db, user, tmp_path, write_jsonl, monkeypatch):
    """Aegis-14B is mandatory governance; no heuristic fallback may sign a paid job."""
    def boom(*a, **k):
        raise RuntimeError("AINODE unreachable")
    monkeypatch.setattr(agent, "decide", boom)

    src = write_jsonl(tmp_path, [{"prompt": "hi a@b.com", "completion": "ok 555-123-4567"},
                                 {"question": "x", "answer": "y"}])
    job = Job(user_id=user.id, status="processing", input_file_path=src, quote_amount=100.0,
              approved_cap=100.0, revenue_collected=100.0, target_margin_pct=0.65)
    db.add(job); db.commit(); db.refresh(job)

    try:
        refinery.process_job(db, job, sample="sample text")
        raise AssertionError("expected Aegis-14B outage to queue the job")
    except agent.AegisTemporarilyQueued as e:
        assert "temporarily queued" in str(e)
    assert job.status == "queued"
    assert not job.output_file_path


def test_curation_error_marks_job_failed(db, user, monkeypatch):
    monkeypatch.setattr(agent, "decide", lambda *a, **k: {
        "complexity": 0.1,
        "risk": "low",
        "est_tokens": 100,
        "noise_level": 0,
        "steps": ["parse"],
        "can_run_locally": True,
    })
    job = Job(user_id=user.id, status="processing", input_file_path="/tmp/does-not-exist.jsonl",
              quote_amount=55.0, approved_cap=55.0, revenue_collected=55.0, target_margin_pct=0.65)
    db.add(job); db.commit(); db.refresh(job)

    summary = refinery.process_job(db, job, sample="sample text")

    assert "curation_error" in summary
    assert job.status == "failed"
    assert not job.output_file_path


def test_zero_usable_rows_marks_job_failed(db, user, tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "decide", lambda *a, **k: {
        "complexity": 0.1,
        "risk": "low",
        "est_tokens": 100,
        "noise_level": 0,
        "steps": ["parse"],
        "can_run_locally": True,
    })
    src = tmp_path / "unmapped.csv"
    src.write_text("name,email\nAda,ada@example.com\n")
    job = Job(user_id=user.id, status="processing", input_file_path=str(src),
              quote_amount=55.0, approved_cap=55.0, revenue_collected=55.0, target_margin_pct=0.65)
    db.add(job); db.commit(); db.refresh(job)

    summary = refinery.process_job(db, job, sample="sample text")

    assert summary["stats"]["rows_out"] == 0
    assert summary["curation_error"] == "no usable records produced"
    assert job.status == "failed"
