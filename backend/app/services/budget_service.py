"""Budget ledger + cap-gated spend (QUOTE_ENGINE.md §4).

The accepted quote is a HARD cap. The agent spends autonomously within it (quote-acceptance
pre-authorized that money); the existing human SpendTicket gate fires ONLY on a proposed spend
that would breach the cap. Decimal math so cap checks don't drift (money columns are Float —
integer-cents migration is owned v2).
"""
from decimal import Decimal as D

from sqlalchemy.orm import Session

from app.models.spend_ticket import SpendTicket
from app.services import spend_service, provider_catalog as pc
from app.services.audit import log_action

EPS = D("0.005")


def _d(x) -> D:
    return D(str(x or 0))


def ledger(db: Session, job) -> dict:
    rows = db.query(SpendTicket).filter(SpendTicket.job_id == job.id).all()
    committed = sum((_d(t.actual_amount if t.actual_amount is not None else t.amount)
                     for t in rows if t.status in ("approved", "executed")), D(0))
    executed = sum((_d(t.actual_amount if t.actual_amount is not None else t.amount)
                    for t in rows if t.status == "executed"), D(0))
    cap = _d(job.approved_cap if job.approved_cap is not None else job.quote_amount)
    return {"cap": cap, "committed": committed, "executed": executed,
            "remaining": cap - committed,
            "soft_line": _d(job.quote_amount) * (D(1) - _d(job.target_margin_pct))}


def request_spend(db: Session, job, *, provider: str, units: float, reason: str,
                  capability: str | None = None, source: str | None = None):
    """Returns ('authorized'|'rerouted', ticket) → caller may execute the provider call,
    or ('gated', ticket) → job paused; a human must re-quote / approve-overrun / reject.

    The cap is the ONLY thing that arms a human. Crossing the soft margin line only logs a
    warning (and is where a cheaper-reroute would slot in v2)."""
    amount = _d(pc.cost(provider, units))
    L = ledger(db, job)
    projected = L["committed"] + amount

    if projected > L["cap"] + EPS:
        over = projected - L["cap"]
        t = spend_service.create_spend_ticket(
            db, job.id, float(amount),
            f"OVERRUN: {provider} {reason}. Would reach ${projected:.2f} vs cap ${L['cap']:.2f} "
            f"(over ${over:.2f}). Options: re-quote +${over:.2f}, operator-absorb, or reject.")
        t.kind = "gated"; t.gate_reason = "overrun:cap_exceeded"
        t.provider = provider; t.units = units; t.cost_source = source
        job.status = "awaiting_approval"
        db.commit()
        log_action(db, job.id, "spend_overrun_gated", "agent",
                   {"ticket_id": t.id, "projected": float(projected), "cap": float(L["cap"])})
        return ("gated", t)

    if projected > L["soft_line"]:
        log_action(db, job.id, "margin_warning", "agent",
                   {"soft_line": float(L["soft_line"]), "projected": float(projected), "provider": provider})

    t = spend_service.create_spend_ticket(db, job.id, float(amount), f"{provider}: {reason}")
    t.kind = "autonomous"; t.provider = provider; t.units = units; t.cost_source = source
    db.commit()
    spend_service.authorize_within_cap(db, t.id, job)
    return ("authorized", t)
