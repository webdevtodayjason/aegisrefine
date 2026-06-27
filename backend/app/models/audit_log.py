from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from ..database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), index=True)
    action = Column(String, nullable=False)   # triage, spend_proposed, spend_approved, spend_rejected, spend_executed, inference, aar_issued
    actor = Column(String, nullable=False)     # system | human | agent
    details = Column(JSON)                      # structured payload: cost, model, approver, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
