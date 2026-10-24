"""
User and Role Management Router for StockSense Administrators.
Enforces admin-only access, prevents accidental removal of the last active administrator,
and logs all identity mutations to audit logs.
"""
from typing import List, Optional
import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.auth import User, UserSession
from ..services.auth import (
    require_admin,
    hash_password,
    revoke_all_user_sessions,
    record_audit_log,
    admin_count,
)

router = APIRouter(prefix="/api/admin/users", tags=["Admin User Management"])


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: str = Field(default="shopkeeper", description="'admin' or 'shopkeeper'")


class UpdateStatusRequest(BaseModel):
    is_active: bool


class UpdateRoleRequest(BaseModel):
    role: str = Field(description="'admin' or 'shopkeeper'")


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8)


@router.get("")
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all user accounts with their status, role, and last login."""
    users = db.query(User).order_by(User.id.asc()).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "full_name": u.full_name or u.username,
            "role": u.role,
            "is_active": u.is_active,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "failed_login_attempts": u.failed_login_attempts,
            "is_locked": bool(u.locked_until and u.locked_until > datetime.datetime.utcnow()),
        }
        for u in users
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(
    req: CreateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Create a new user account with role assignment."""
    clean_username = req.username.strip().lower()

    # Check unique username
    existing = db.query(User).filter(User.username == clean_username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username '{clean_username}' is already in use.",
        )

    if req.role not in ("admin", "shopkeeper"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be either 'admin' or 'shopkeeper'.",
        )

    new_user = User(
        username=clean_username,
        email=req.email.strip() if req.email else None,
        full_name=req.full_name.strip() if req.full_name else clean_username.title(),
        hashed_password=hash_password(req.password),
        role=req.role,
        is_active=True,
        created_by_id=admin.id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    record_audit_log(
        db,
        action="USER_CREATED",
        entity_type="USER",
        entity_id=str(new_user.id),
        summary=f"Admin '{admin.username}' created user '{clean_username}' with role '{req.role}'.",
        actor_id=admin.id,
        actor_username=admin.username,
    )

    return {
        "status": "success",
        "message": f"User '{clean_username}' created successfully.",
        "user_id": new_user.id,
        "username": new_user.username,
        "role": new_user.role,
    }


@router.patch("/{user_id}/status")
def toggle_user_status(
    user_id: int,
    req: UpdateStatusRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Activate or deactivate a user account. Prevents deactivating the last active admin."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Guard: Do not deactivate the last active administrator
    if user.role == "admin" and not req.is_active:
        if admin_count(db) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Security protection: Cannot deactivate the last active administrator.",
            )

    user.is_active = req.is_active
    if not req.is_active:
        # Revoke all active sessions immediately
        revoke_all_user_sessions(db, user.id)

    db.commit()

    action_label = "ACTIVATED" if req.is_active else "DEACTIVATED"
    record_audit_log(
        db,
        action=f"USER_{action_label}",
        entity_type="USER",
        entity_id=str(user.id),
        summary=f"Admin '{admin.username}' {action_label.lower()} user '{user.username}'.",
        actor_id=admin.id,
        actor_username=admin.username,
    )

    return {
        "status": "success",
        "message": f"User '{user.username}' is now {'active' if req.is_active else 'deactivated'}.",
        "is_active": user.is_active,
    }


@router.patch("/{user_id}/role")
def change_user_role(
    user_id: int,
    req: UpdateRoleRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Change user role. Protects against demoting the last active administrator."""
    if req.role not in ("admin", "shopkeeper"):
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin' or 'shopkeeper'.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Guard: Demoting the last active admin
    if user.role == "admin" and req.role != "admin":
        if admin_count(db) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Security protection: Cannot demote the last active administrator.",
            )

    old_role = user.role
    user.role = req.role
    db.commit()

    record_audit_log(
        db,
        action="USER_ROLE_CHANGED",
        entity_type="USER",
        entity_id=str(user.id),
        summary=f"Admin '{admin.username}' changed role for '{user.username}' from '{old_role}' to '{req.role}'.",
        actor_id=admin.id,
        actor_username=admin.username,
    )

    return {"status": "success", "message": f"Role updated to '{req.role}'.", "role": user.role}


@router.post("/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    req: ResetPasswordRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin-initiated password reset. Revokes all active sessions."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.hashed_password = hash_password(req.new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    revoke_all_user_sessions(db, user.id)
    db.commit()

    record_audit_log(
        db,
        action="USER_PASSWORD_RESET",
        entity_type="USER",
        entity_id=str(user.id),
        summary=f"Admin '{admin.username}' reset the password for '{user.username}'. Sessions revoked.",
        actor_id=admin.id,
        actor_username=admin.username,
    )

    return {"status": "success", "message": f"Password reset for '{user.username}'. Sessions revoked."}


@router.post("/{user_id}/revoke-sessions")
def revoke_user_sessions(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Revoke all active sessions for a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    revoke_all_user_sessions(db, user.id)
    record_audit_log(
        db,
        action="SESSIONS_REVOKED",
        entity_type="USER",
        entity_id=str(user.id),
        summary=f"Admin '{admin.username}' revoked all active sessions for '{user.username}'.",
        actor_id=admin.id,
        actor_username=admin.username,
    )
    return {"status": "success", "message": f"All sessions revoked for '{user.username}'."}
