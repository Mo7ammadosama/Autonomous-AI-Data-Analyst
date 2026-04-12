"""
Notifications router — in-app notification management.

Endpoints:
  GET    /api/notifications/           list notifications (unread first)
  POST   /api/notifications/mark-read  mark notifications as read
  DELETE /api/notifications/{id}       delete a notification
  GET    /api/notifications/count      unread count
"""

import uuid
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, Notification, AuditLog
from security.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


def create_notification(
    db: Session,
    user_id: str,
    type: str,
    title: str,
    message: Optional[str] = None,
    link: Optional[str] = None,
):
    """Helper to create a notification from anywhere in the codebase."""
    notif = Notification(
        id=str(uuid.uuid4()),
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        link=link,
    )
    db.add(notif)
    db.commit()
    return notif


def log_activity(
    db: Session,
    user_id: str,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Helper to write an audit log entry."""
    entry = AuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
    return entry


class MarkReadRequest(BaseModel):
    ids: Optional[List[str]] = None   # None = mark all


@router.get("/count")
async def unread_count(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = db.query(Notification).filter(
        Notification.user_id == current_user["sub"],
        Notification.is_read == False,
    ).count()
    return {"unread": count}


@router.get("/")
async def list_notifications(
    limit: int = Query(50, le=200),
    unread_only: bool = Query(False),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Notification).filter(Notification.user_id == current_user["sub"])
    if unread_only:
        q = q.filter(Notification.is_read == False)
    notifications = q.order_by(Notification.created_at.desc()).limit(limit).all()
    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "link": n.link,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifications
    ]


@router.post("/mark-read")
async def mark_read(
    req: MarkReadRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Notification).filter(
        Notification.user_id == current_user["sub"],
        Notification.is_read == False,
    )
    if req.ids:
        q = q.filter(Notification.id.in_(req.ids))
    updated = q.update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"marked_read": updated}


@router.delete("/{notif_id}", status_code=204)
async def delete_notification(
    notif_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notif = db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.user_id == current_user["sub"],
    ).first()
    if notif:
        db.delete(notif)
        db.commit()


@router.get("/activity")
async def activity_feed(
    limit: int = Query(50, le=200),
    resource_type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return recent audit log entries for the current user."""
    q = db.query(AuditLog).filter(AuditLog.user_id == current_user["sub"])
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    entries = q.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "action": e.action,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "details": e.details,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]
