from sqlalchemy import Column, Integer, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database.database import Base
from datetime import datetime

class UserNotificationSettings(Base):
    __tablename__ = "user_notification_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    email_enabled = Column(Boolean, default=True)
    broken_links = Column(Boolean, default=True)
    status_changes = Column(Boolean, default=True)
    weekly_report = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="notification_settings")

class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    total_links = Column(Integer)
    healthy_links = Column(Integer)
    broken_links = Column(Integer)
    new_issues = Column(Integer)
    sent_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="weekly_reports")