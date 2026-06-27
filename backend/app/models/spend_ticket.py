from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.sql import func
from ..database import Base

class SpendTicket(Base):
    __tablename__ = "spend_tickets"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String)
    status = Column(String, default="proposed")  # proposed, approved, rejected, executed
    stripe_payment_intent_id = Column(String)
    approved_by = Column(String)   # identity of the human who approved — the core audit claim
    rejected_by = Column(String)
    proposed_at = Column(DateTime(timezone=True), server_default=func.now())
    decided_at = Column(DateTime(timezone=True))
    executed_at = Column(DateTime(timezone=True))