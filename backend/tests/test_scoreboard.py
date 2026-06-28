from starlette.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.job import Job


def test_scoreboard_aggregates_pnl_and_record():
    db = SessionLocal()
    u = User(email="sb@test.com")
    db.add(u); db.commit(); db.refresh(u)
    db.add(Job(user_id=u.id, status="completed", quote_amount=100.0, actual_cost=0.0, target_margin_pct=0.65))   # win
    db.add(Job(user_id=u.id, status="completed", quote_amount=100.0, actual_cost=200.0, target_margin_pct=0.65))  # loss
    db.commit()

    d = TestClient(app).get("/agent/scoreboard").json()
    assert d["jobs"] >= 2
    assert d["record"]["wins"] >= 1 and d["record"]["losses"] >= 1
    assert d["revenue_usd"] >= 200
    # the win job: 100 - 0 - 3.30 fee = 96.70 (>= 65% target) -> win; the loss job nets negative
    outcomes = {r["outcome"] for r in d["recent"]}
    assert "win" in outcomes and "loss" in outcomes
