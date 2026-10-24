"""
Auth, user, role, and enhanced audit models for StockSense.
Extends the existing SQLAlchemy models without breaking existing tables.
"""
import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey,
    Text, Index, Enum
)
from sqlalchemy.orm import relationship
from ..database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(200), unique=True, nullable=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=True)
    role = Column(String(50), nullable=False, default="shopkeeper")
    # Roles: 'admin', 'shopkeeper'
    is_active = Column(Boolean, default=True, nullable=False)
    is_first_login = Column(Boolean, default=True)
    last_login_at = Column(DateTime, nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLogV2", back_populates="actor", foreign_keys="AuditLogV2.actor_id")

    __table_args__ = (
        Index("ix_users_role", "role"),
    )


class UserSession(Base):
    """Active session tokens for token revocation support."""
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    jti = Column(String(100), unique=True, nullable=False, index=True)  # JWT Token ID
    issued_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)

    user = relationship("User", back_populates="sessions")


class AuditLogV2(Base):
    """Enhanced audit log with actor tracking."""
    __tablename__ = "audit_logs_v2"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # None = system
    actor_username = Column(String(100), nullable=True)  # Denormalized for log integrity
    action = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(String(200), nullable=True)
    summary = Column(Text, nullable=True)  # Human-readable summary
    ip_address = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    actor = relationship("User", back_populates="audit_logs", foreign_keys=[actor_id])

    __table_args__ = (
        Index("ix_audit_v2_timestamp", "timestamp"),
        Index("ix_audit_v2_action", "action"),
    )


class OfflineSyncQueue(Base):
    """Queue for offline transactions waiting to be synced to SQLite."""
    __tablename__ = "offline_sync_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_id = Column(String(100), unique=True, nullable=False, index=True)  # Client-generated UUID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    operation_type = Column(String(50), nullable=False)
    # 'RECORD_SALE', 'STOCK_IN', 'STOCK_ADJUSTMENT', 'ADD_PRODUCT'
    payload = Column(Text, nullable=False)  # JSON
    status = Column(String(20), default="PENDING", index=True)
    # PENDING, SYNCED, FAILED, DUPLICATE
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    synced_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_sync_status", "status"),
    )


class NotebookImport(Base):
    """Track OCR/manual notebook import sessions."""
    __tablename__ = "notebook_imports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    source_type = Column(String(50), nullable=False)  # 'PHOTO', 'PDF', 'MANUAL'
    original_filename = Column(String(255), nullable=True)
    status = Column(String(50), default="PENDING")
    # PENDING, EXTRACTED, CONFIRMED, CANCELLED, FAILED
    extracted_rows = Column(Text, nullable=True)  # JSON: raw extraction
    confirmed_rows = Column(Text, nullable=True)  # JSON: user-confirmed rows
    rows_committed = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_notebook_status", "status"),
    )


class StockCount(Base):
    """Physical stock count sessions and their adjustments."""
    __tablename__ = "stock_counts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    count_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    product_id = Column(String(50), ForeignKey("products.product_id"), nullable=False, index=True)
    system_stock = Column(Float, nullable=False)
    counted_stock = Column(Float, nullable=False)
    difference = Column(Float, nullable=False)  # counted - system
    reason = Column(String(255), nullable=True)
    status = Column(String(20), default="PENDING")
    # PENDING, CONFIRMED, CANCELLED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)

    product = relationship("Product")
