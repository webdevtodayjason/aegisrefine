"""The agent's leaderboard — its audited books across every quoted job.

Public + aggregate (no per-customer PII): jobs played, revenue, spend, profit, realized-vs-target
margin, and a win/thin/loss record. This is the 'fully automated company with a P&L you can audit'
view — the agent playing its own business as a measurable game.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.job import Job

router = APIRouter(prefix="/agent", tags=["scoreboard"])


def _stripe_fee(quote: float) -> float:
    return round(quote * 0.029 + 0.30, 2)


def _job_pnl(j: Job) -> dict:
    quote = float(j.quote_amount or 0)
    spent = float(j.actual_cost or 0)
    fee = _stripe_fee(quote)
    margin = round(quote - spent - fee, 2)
    margin_pct = round(100 * margin / quote, 1) if quote else 0.0
    target = (j.target_margin_pct or 0.65) * 100
    outcome = "loss" if margin < 0 else ("win" if margin_pct >= target else "thin")
    return {"job_id": j.id, "status": j.status, "quoted_usd": round(quote, 2), "spent_usd": round(spent, 2),
            "stripe_fee_usd": fee, "margin_usd": margin, "margin_pct": margin_pct,
            "target_margin_pct": round(target, 1), "outcome": outcome}


@router.get("/scoreboard")
async def scoreboard(db: Session = Depends(get_db), limit: int = 20):
    jobs = db.query(Job).filter(Job.quote_amount.isnot(None)).order_by(Job.id.desc()).all()
    rows = [_job_pnl(j) for j in jobs]
    n = len(rows)
    rev = round(sum(r["quoted_usd"] for r in rows), 2)
    spend = round(sum(r["spent_usd"] for r in rows), 2)
    fees = round(sum(r["stripe_fee_usd"] for r in rows), 2)
    profit = round(rev - spend - fees, 2)
    wins = sum(1 for r in rows if r["outcome"] == "win")
    thin = sum(1 for r in rows if r["outcome"] == "thin")
    loss = sum(1 for r in rows if r["outcome"] == "loss")
    avg_margin = round(sum(r["margin_pct"] for r in rows) / n, 1) if n else 0.0
    return {
        "jobs": n,
        "revenue_usd": rev, "spend_usd": spend, "fees_usd": fees, "profit_usd": profit,
        "avg_margin_pct": avg_margin,
        "record": {"wins": wins, "thin": thin, "losses": loss},
        "win_rate_pct": round(100 * wins / n, 1) if n else 0.0,
        "recent": rows[:max(1, min(limit, 100))],
    }
