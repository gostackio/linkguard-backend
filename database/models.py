from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base
from .notification_models import UserNotificationSettings  # Import from notification_models

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String, nullable=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_premium = Column(Boolean, default=False)
    # Security / account state
    failed_login_attempts = Column(Integer, default=0)
    last_failed_login = Column(DateTime, nullable=True)
    is_locked = Column(Boolean, default=False)
    locked_until = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    links = relationship("Link", back_populates="owner")
    alerts = relationship("Alert", back_populates="user")
    notification_settings = relationship("UserNotificationSettings", back_populates="user", uselist=False)
    weekly_reports = relationship("WeeklyReport", back_populates="user")

class Link(Base):
    __tablename__ = "links"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, index=True)
    name = Column(String)
    description = Column(Text, nullable=True)
    check_frequency = Column(Integer)  # in minutes
    last_checked = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"))

    # Relationships
    owner = relationship("User", back_populates="links")
    alerts = relationship("Alert", back_populates="link")
    status_history = relationship("LinkStatus", back_populates="link")

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    link_id = Column(Integer, ForeignKey("links.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(String)  # e.g., "down", "changed", "performance"
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_read = Column(Boolean, default=False)

    # Relationships
    link = relationship("Link", back_populates="alerts")
    user = relationship("User", back_populates="alerts")

class LinkStatus(Base):
    __tablename__ = "link_status"

    id = Column(Integer, primary_key=True, index=True)
    link_id = Column(Integer, ForeignKey("links.id"))
    status_code = Column(Integer)
    response_time = Column(Integer)  # in milliseconds
    is_available = Column(Boolean)
    content_type = Column(String, nullable=True)
    final_url = Column(String, nullable=True)
    redirect_count = Column(Integer, default=0)
    error_message = Column(String, nullable=True)
    checked_at = Column(DateTime, default=datetime.utcnow)
    check_method = Column(String, default='HEAD')  # HEAD or GET

    # Relationships
    link = relationship("Link", back_populates="status_history")

