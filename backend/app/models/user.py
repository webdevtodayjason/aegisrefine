from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from ..database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    stripe_customer_id = Column(String, unique=True, index=True)
    password_hash = Column(String)            # pbkdf2$... (null = no password / legacy)
    is_admin = Column(Boolean, default=False, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
