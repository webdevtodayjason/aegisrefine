import pytest
from app.models.job import Job
from app.models.spend_ticket import SpendTicket
from app.curate import engine
from app.services import refinery


def test_cert_records_pnl_and_guarantees(db, user, tmp_path, write_jsonl):
    src = write_jsonl(tmp_path, [{"prompt": "hi a@b.com", "completion": "ok 555-123-4567"},
                                 {"question": "x", "answer": "y"}])
    job = Job(user_id=user.id, status="processing", input_file_path=src, quote_amount=250.0,
              approved_cap=250.0, revenue_collected=250.0, target_margin_pct=0.65)
    db.add(job); db.commit(); db.refresh(job)
    job.output_file_path = engine.run(src, out_dir=str(tmp_path))["output_path"]; db.commit()

    cert = refinery.complete_job(db, job)
    e = cert["economics"]
    assert e["quoted_usd"] == 250.0 and e["spent_usd"] == 0.0 and e["cap_respected"] is True
    assert e["margin_usd"] == 242.45 and e["realized_margin_pct"] == 97.0
    assert cert["guarantees"]["pii_residual"] == 0 and cert["guarantees"]["schema_valid"] is True
    assert cert["sig"]["alg"] == "Ed25519"


def test_refuses_to_sign_when_overspent(db, user, tmp_path, write_jsonl):
    src = write_jsonl(tmp_path, [{"prompt": "hi", "completion": "hello"}, {"question": "x", "answer": "y"}])
    job = Job(user_id=user.id, status="processing", input_file_path=src, quote_amount=100.0,
              approved_cap=100.0, revenue_collected=100.0, target_margin_pct=0.65)
    db.add(job); db.commit(); db.refresh(job)
    job.output_file_path = engine.run(src, out_dir=str(tmp_path))["output_path"]; db.commit()
    db.add(SpendTicket(job_id=job.id, amount=300.0, status="executed", actual_amount=300.0)); db.commit()

    with pytest.raises(ValueError):
        refinery.complete_job(db, job)
