from app.models.job import Job
from app.services import refinery, agent


def test_job_completes_when_model_unreachable(db, user, tmp_path, write_jsonl, monkeypatch):
    """The deployed container can't reach Aegis-14B — governance degrades, but the deterministic
    curation + signed cert must still ship."""
    def boom(*a, **k):
        raise RuntimeError("AINODE unreachable")
    monkeypatch.setattr(agent, "decide", boom)

    src = write_jsonl(tmp_path, [{"prompt": "hi a@b.com", "completion": "ok 555-123-4567"},
                                 {"question": "x", "answer": "y"}])
    job = Job(user_id=user.id, status="processing", input_file_path=src, quote_amount=100.0,
              approved_cap=100.0, revenue_collected=100.0, target_margin_pct=0.65)
    db.add(job); db.commit(); db.refresh(job)

    summary = refinery.process_job(db, job, sample="sample text")
    assert summary["stats"]["rows_in"] == 2           # curation ran despite the model being down
    assert job.output_file_path                        # real bytes produced

    cert = refinery.complete_job(db, job)
    assert cert["economics"]["cap_respected"] is True
    assert cert["guarantees"]["pii_residual"] == 0
