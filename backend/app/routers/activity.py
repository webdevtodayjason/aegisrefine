from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.audit_log import AuditLog

router = APIRouter(tags=["activity"])

# Public feed MUST NOT leak raw data — whitelist safe detail keys only.
# Never expose: dataset_url, email, file paths, PANs, raw row content.
SAFE_KEYS = {"amount", "model", "ticket_id", "certificate_id", "response_sha256", "real_money"}

# Human-readable one-liners for the live ticker.
SUMMARY = {
    "job_created": "Job paid — refinement queued",
    "spend_proposed": "Agent proposed a gated spend",
    "spend_approved": "Operator approved the spend",
    "spend_rejected": "Operator denied the spend — no money moved",
    "spend_executed": "Spend executed",
    "aar_issued": "Signed certificate issued ✓",
}


def _mask(v):
    # approver handle, not a full email
    return v.split("@", 1)[0] + "@…" if isinstance(v, str) and "@" in v else v


def _public_details(details: dict) -> dict:
    details = details or {}
    out = {k: details[k] for k in SAFE_KEYS if k in details}
    for who in ("approved_by", "rejected_by"):
        if who in details:
            out[who] = _mask(details[who])
    return out


@router.get("/activity")
async def activity(limit: int = 50, db: Session = Depends(get_db)):
    """Public live audit feed — watch the agent earn, spend (gated), and prove, in real time.
    Redacted: action/actor/amount/model/cert only; never dataset contents, paths, emails, or PANs."""
    limit = max(1, min(limit, 200))
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return [{
        "at": r.created_at.isoformat() if r.created_at else None,
        "action": r.action,
        "actor": r.actor,
        "job_id": r.job_id,
        "summary": SUMMARY.get(r.action, r.action),
        "details": _public_details(r.details),
    } for r in rows]
