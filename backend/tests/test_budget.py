from app.models.job import Job
from app.services import budget_service as bs


def test_cap_gate_autonomous_then_overrun(db, user):
    job = Job(user_id=user.id, status="processing", quote_amount=250.0, approved_cap=250.0, target_margin_pct=0.65)
    db.add(job); db.commit(); db.refresh(job)

    L = bs.ledger(db, job)
    assert float(L["cap"]) == 250.0 and float(L["committed"]) == 0.0 and float(L["soft_line"]) == 87.5

    s, t = bs.request_spend(db, job, provider="gpt_4o_mini", units=4.0, reason="ambiguous rows")
    assert s == "authorized" and t.kind == "autonomous" and t.approved_by.startswith("quote_pre_authorization")

    s, _ = bs.request_spend(db, job, provider="textract_expense", units=20000, reason="ocr")  # $200
    assert s == "authorized" and float(bs.ledger(db, job)["committed"]) == 204.0

    s, t = bs.request_spend(db, job, provider="gpt_4o_mini", units=60.0, reason="would breach")  # 264 > 250
    assert s == "gated" and t.gate_reason == "overrun:cap_exceeded" and job.status == "awaiting_approval"
    assert float(bs.ledger(db, job)["committed"]) == 204.0  # gated proposal not counted
