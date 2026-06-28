from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean, JSON
from sqlalchemy.sql import func
from ..database import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="pending")  # pending, processing, completed, failed
    input_file_path = Column(String)
    output_file_path = Column(String)
    complexity_score = Column(Float)
    estimated_cost = Column(Float)   # projected COGS at quote time
    actual_cost = Column(Float)      # executed ledger total on settle
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # --- quote / economics (QUOTE_ENGINE.md) ---
    quote_amount = Column(Float)                 # accepted flat cap = Stripe charge = revenue
    approved_cap = Column(Float)                 # hard ceiling the gate checks; starts = quote_amount
    quote_status = Column(String, default="draft")  # draft|sent|accepted|declined|change_requested|expired
    quote_breakdown = Column(JSON)
    target_margin_pct = Column(Float, default=0.65)
    margin_floor_pct = Column(Float, default=0.55)
    revenue_collected = Column(Float)
    requires_human_quote = Column(Boolean, default=False)
    quote_accepted_at = Column(DateTime(timezone=True))