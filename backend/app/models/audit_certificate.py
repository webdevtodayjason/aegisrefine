from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from ..database import Base

class AuditCertificate(Base):
    __tablename__ = "audit_certificates"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False, index=True)
    json_path = Column(String)
    pdf_path = Column(String)
    signature = Column(String)   # detached signature over the AAR (hex/base64)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
