"""
Audit trail helper. Every meaningful action writes one immutable AuditLog row.
This is both the internal audit trail and the data source for the public
"watch the agent work" feed on the site.
"""

from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog

def log_action(db: Session, job_id: int | None, action: str, actor: str, details: dict | None = None):
    entry = AuditLog(job_id=job_id, action=action, actor=actor, details=details or {})
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
