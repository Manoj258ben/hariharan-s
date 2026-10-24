"""
Authentication and session management router for StockSense.
Supports JWT tokens in Authorization header and HttpOnly cookies.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.auth import User
from ..services.auth import (
    authenticate_user,
    create_access_token,
    create_session,
    revoke_session,
    get_current_user,
    ensure_initial_admin,
    hash_password,
    record_audit_log,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserProfileResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    full_name: Optional[str]
    role: str
    is_active: bool


@router.post("/login")
def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Authenticate user and issue JWT access token.
    Sets HttpOnly cookie for web security and returns token for API/mobile clients.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    user = authenticate_user(db, req.username.strip(), req.password, ip=client_ip)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = create_access_token(user)

    # Persist session for revocation
    from datetime import datetime
    expires_dt = datetime.fromisoformat(token_data["expires_at"])
    create_session(
        db,
        user=user,
        jti=token_data["jti"],
        expires_at=expires_dt,
        ip=client_ip,
        ua=request.headers.get("user-agent"),
    )

    # Set secure HttpOnly cookie
    response.set_cookie(
        key="stocksense_access_token",
        value=token_data["access_token"],
        httponly=True,
        samesite="lax",
        secure=False,  # Set to True when served over HTTPS
        max_age=8 * 3600,
    )

    return {
        "status": "success",
        "message": f"Welcome back, {user.full_name or user.username}!",
        "access_token": token_data["access_token"],
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name or user.username,
            "role": user.role,
            "email": user.email,
        }
    }


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Revokes the current session and clears the auth cookie.
    """
    token_str = request.cookies.get("stocksense_access_token")
    if not token_str:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token_str = auth_header[7:].strip()

    if token_str:
        from ..services.auth import decode_access_token
        payload = decode_access_token(token_str)
        if payload and payload.get("jti"):
            revoke_session(db, payload["jti"])

    response.delete_cookie("stocksense_access_token")
    record_audit_log(
        db,
        action="LOGOUT",
        entity_type="AUTH",
        entity_id=str(current_user.id),
        summary=f"User '{current_user.username}' logged out.",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )
    return {"status": "success", "message": "Successfully logged out."}


@router.get("/me")
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently logged in user."""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name or current_user.username,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "last_login_at": current_user.last_login_at.isoformat() if current_user.last_login_at else None,
    }


@router.post("/bootstrap-admin")
def bootstrap_admin(db: Session = Depends(get_db)):
    """
    Creates the initial administrator and shopkeeper accounts if no administrator exists.
    Rejects creation if an admin already exists to prevent takeover.
    """
    admin_exists = db.query(User).filter(User.role == "admin").first()
    if admin_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrator already initialized. Please log in.",
        )

    ensure_initial_admin(db)
    return {"status": "success", "message": "Initial administrator account initialized successfully."}
