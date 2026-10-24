"""
Audit Logging & Security Audit Router for StockSense.
Provides protected querying and filtering of administrative and security events.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models.auth import AuditLogV2, User
from ..services.auth import require_admin

router = APIRouter(prefix="/api/admin/audit", tags=["Security & Audit Logs"])


@router.get("/logs")
def get_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    actor_username: Optional[str] = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Retrieve audit logs with optional filtering by action, entity, or actor."""
    query = db.query(AuditLogV2)

    if action:
        query = query.filter(AuditLogV2.action.ilike(f"%{action}%"))
    if entity_type:
        query = query.filter(AuditLogV2.entity_type.ilike(f"%{entity_type}%"))
    if actor_username:
        query = query.filter(AuditLogV2.actor_username.ilike(f"%{actor_username}%"))

    total = query.count()
    logs = query.order_by(AuditLogV2.id.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": [
            {
                "id": l.id,
                "timestamp": l.timestamp.isoformat() if l.timestamp else None,
                "actor_id": l.actor_id,
                "actor_username": l.actor_username or "System",
                "action": l.action,
                "entity_type": l.entity_type,
                "entity_id": l.entity_id,
                "summary": l.summary,
                "ip_address": l.ip_address,
            }
            for l in logs
        ]
    }


@router.get("/summary")
def get_audit_summary(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Summarize recent security and administrative activities."""
    total_logs = db.query(AuditLogV2).count()

    # Top actions
    top_actions = db.query(
        AuditLogV2.action, func.count(AuditLogV2.id)
    ).group_by(AuditLogV2.action).order_by(func.count(AuditLogV2.id).desc()).limit(8).all()

    # Recent security alerts (failed logins, blocked attempts)
    security_events = db.query(AuditLogV2).filter(
        AuditLogV2.action.in_(["LOGIN_FAILED", "LOGIN_BLOCKED", "LOGIN_DEACTIVATED"])
    ).order_by(AuditLogV2.id.desc()).limit(10).all()

    return {
        "total_audit_events": total_logs,
        "top_actions": [{"action": act, "count": cnt} for act, cnt in top_actions],
        "recent_security_events": [
            {
                "id": e.id,
                "action": e.action,
                "actor_username": e.actor_username,
                "summary": e.summary,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "ip_address": e.ip_address,
            }
            for e in security_events
        ]
    }
