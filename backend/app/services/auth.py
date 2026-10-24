"""
Authentication & authorization service for StockSense.
Uses bcrypt for password hashing and short-lived JWT access tokens.
Enforces role-based access control, session tracking, and security audit logs.
"""
import datetime
import uuid
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.auth import User, UserSession, AuditLogV2
from ..models import AuditLog
from ..config import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_ACCESS_TOKEN_EXPIRE_MINUTES

import bcrypt

security_bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    pwd_bytes = plain.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    try:
        pwd_bytes = plain.encode('utf-8')[:72]
        hashed_bytes = hashed.encode('utf-8')
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
    except Exception:
        return False


# --- JWT Token Handling ---
def create_access_token(user: User) -> dict:
    """Return {'access_token': ..., 'jti': ..., 'expires_at': ...}"""
    jti = str(uuid.uuid4())
    now = datetime.datetime.utcnow()
    expire = now + datetime.timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "jti": jti,
        "iat": now,
        "exp": expire,
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return {
        "access_token": token,
        "token_type": "bearer",
        "jti": jti,
        "expires_at": expire.isoformat(),
        "role": user.role,
        "username": user.username,
        "full_name": user.full_name or user.username,
    }


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify token. Returns payload dict or None."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


# --- Session Management ---
def create_session(
    db: Session,
    user: User,
    jti: str,
    expires_at: datetime.datetime,
    ip: Optional[str] = None,
    ua: Optional[str] = None,
) -> UserSession:
    session = UserSession(
        user_id=user.id,
        jti=jti,
        expires_at=expires_at,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(session)
    db.commit()
    return session


def revoke_session(db: Session, jti: str) -> bool:
    session = db.query(UserSession).filter(UserSession.jti == jti).first()
    if session and not session.revoked_at:
        session.revoked_at = datetime.datetime.utcnow()
        db.commit()
        return True
    return False


def revoke_all_user_sessions(db: Session, user_id: int):
    now = datetime.datetime.utcnow()
    db.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.revoked_at == None  # noqa
    ).update({"revoked_at": now})
    db.commit()


def is_session_valid(db: Session, jti: str) -> bool:
    session = db.query(UserSession).filter(UserSession.jti == jti).first()
    if not session:
        return False
    if session.revoked_at is not None:
        return False
    if session.expires_at < datetime.datetime.utcnow():
        return False
    return True


# --- User Helpers ---
def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def authenticate_user(db: Session, username: str, password: str, ip: Optional[str] = None) -> Optional[User]:
    """
    Validate credentials with brute-force lockout handling.
    """
    user = get_user_by_username(db, username)
    if not user:
        record_audit_log(
            db,
            action="LOGIN_FAILED",
            entity_type="AUTH",
            entity_id=username,
            summary=f"Failed login attempt for nonexistent user '{username}'",
            ip_address=ip,
        )
        return None

    # Check if locked out
    if user.locked_until and user.locked_until > datetime.datetime.utcnow():
        record_audit_log(
            db,
            action="LOGIN_BLOCKED",
            entity_type="AUTH",
            entity_id=str(user.id),
            summary=f"Login attempt blocked for locked account '{username}'",
            actor_id=user.id,
            actor_username=user.username,
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is temporarily locked due to excessive failed attempts. Please try again in 15 minutes.",
        )

    if not verify_password(password, user.hashed_password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        is_locked_now = False
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
            lock_msg = "Account locked for 15 minutes after 5 failed attempts."
            is_locked_now = True
        else:
            lock_msg = f"Failed attempt {user.failed_login_attempts} of 5."

        db.commit()
        record_audit_log(
            db,
            action="LOGIN_FAILED",
            entity_type="AUTH",
            entity_id=str(user.id),
            summary=f"Invalid password for '{username}'. {lock_msg}",
            actor_id=user.id,
            actor_username=user.username,
            ip_address=ip,
        )
        if is_locked_now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is temporarily locked due to excessive failed attempts. Please try again in 15 minutes.",
            )
        return None

    if not user.is_active:
        record_audit_log(
            db,
            action="LOGIN_DEACTIVATED",
            entity_type="AUTH",
            entity_id=str(user.id),
            summary=f"Deactivated account '{username}' attempted login.",
            actor_id=user.id,
            actor_username=user.username,
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive or disabled. Please contact an administrator.",
        )

    # Reset counter on success
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.datetime.utcnow()
    db.commit()

    record_audit_log(
        db,
        action="LOGIN_SUCCESS",
        entity_type="AUTH",
        entity_id=str(user.id),
        summary=f"User '{username}' logged in successfully.",
        actor_id=user.id,
        actor_username=user.username,
        ip_address=ip,
    )
    return user


def admin_count(db: Session) -> int:
    return db.query(User).filter(User.role == "admin", User.is_active == True).count()  # noqa


def ensure_initial_admin(db: Session):
    """Create default initial administrator if no admin exists."""
    existing_admin = db.query(User).filter(User.role == "admin").first()
    if not existing_admin:
        admin_user = User(
            username="admin",
            email="admin@stocksense.local",
            hashed_password=hash_password("Admin@StockSense2026"),
            full_name="Lead System Administrator",
            role="admin",
            is_active=True,
            is_first_login=False,
        )
        db.add(admin_user)

        # Also add default shopkeeper demo account
        shopkeeper = User(
            username="shopkeeper",
            email="shopkeeper@stocksense.local",
            hashed_password=hash_password("Shop@StockSense2026"),
            full_name="Ramesh Kirana Store Manager",
            role="shopkeeper",
            is_active=True,
            is_first_login=False,
        )
        db.add(shopkeeper)
        db.commit()
        print("[Auth] Created initial admin ('admin') and shopkeeper ('shopkeeper') accounts.")


# --- Audit Logging Service ---
def record_audit_log(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    summary: Optional[str] = None,
    actor_id: Optional[int] = None,
    actor_username: Optional[str] = None,
    ip_address: Optional[str] = None,
):
    try:
        # 1. Enhanced audit log
        log_v2 = AuditLogV2(
            actor_id=actor_id,
            actor_username=actor_username or "System",
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            summary=summary,
            ip_address=ip_address,
            timestamp=datetime.datetime.utcnow(),
        )
        db.add(log_v2)

        # 2. Legacy table sync for backwards compatibility
        legacy_log = AuditLog(
            action=action,
            entity=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            details=f"[{actor_username or 'System'}] {summary or ''}",
            timestamp=datetime.datetime.utcnow(),
        )
        db.add(legacy_log)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[Audit Warning] Failed to persist audit log: {e}")


# --- FastAPI Dependency Injection for Auth ---
def get_token_from_request(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> Optional[str]:
    # Check Authorization header first
    if bearer and bearer.credentials:
        return bearer.credentials
    # Fallback to HttpOnly cookie
    token_cookie = request.cookies.get("stocksense_access_token")
    if token_cookie:
        return token_cookie
    return None


def get_current_user(
    token: Optional[str] = Depends(get_token_from_request),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jti = payload.get("jti")
    if jti and not is_session_valid(db, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token payload.")

    user = get_user_by_id(db, int(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account no longer exists.")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated.")

    return user


def get_optional_current_user(
    token: Optional[str] = Depends(get_token_from_request),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not token:
        return None
    try:
        return get_current_user(token=token, db=db)
    except HTTPException:
        return None


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required to access this resource.",
        )
    return current_user


def require_shopkeeper_or_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("admin", "shopkeeper"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions.",
        )
    return current_user
