"""
Workspaces router — multi-tenant workspace management.

Endpoints:
  GET    /api/workspaces/              list workspaces the user belongs to
  POST   /api/workspaces/              create a new workspace
  GET    /api/workspaces/current       get the user's active workspace
  GET    /api/workspaces/{id}          get workspace details
  PUT    /api/workspaces/{id}          update workspace
  DELETE /api/workspaces/{id}          delete workspace (owner only)
  GET    /api/workspaces/{id}/members  list members
  POST   /api/workspaces/{id}/invite   invite a user by email
  DELETE /api/workspaces/{id}/members/{user_id}  remove member
  POST   /api/workspaces/switch/{id}   switch active workspace
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from models.database import (
    get_db, User, Workspace, WorkspaceMember, WorkspaceInvite, Dataset, Dashboard
)
from security.auth import get_current_user, create_access_token

router = APIRouter()
logger = logging.getLogger(__name__)


class WorkspaceCreate(BaseModel):
    name: str
    description: Optional[str] = None
    plan: Optional[str] = "free"


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class InviteRequest(BaseModel):
    email: EmailStr
    role: Optional[str] = "member"


def _get_workspace_or_403(workspace_id: str, user_id: str, db: Session, require_admin: bool = False):
    member = db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == user_id,
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    if require_admin and member.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws, member


def _workspace_dict(ws: Workspace, member_count: int) -> dict:
    return {
        "id": ws.id,
        "name": ws.name,
        "description": ws.description,
        "plan": ws.plan,
        "member_count": member_count,
        "created_at": ws.created_at.isoformat(),
    }


@router.get("/")
async def list_workspaces(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all workspaces the current user belongs to."""
    memberships = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user["sub"]
    ).all()
    result = []
    for m in memberships:
        ws = db.query(Workspace).filter(Workspace.id == m.workspace_id).first()
        if not ws:
            continue
        count = db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == ws.id).count()
        d = _workspace_dict(ws, count)
        d["your_role"] = m.role
        result.append(d)
    return result


@router.post("/", status_code=201)
async def create_workspace(
    req: WorkspaceCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new workspace. The creator becomes the owner."""
    ws = Workspace(
        id=str(uuid.uuid4()),
        name=req.name,
        description=req.description,
        plan=req.plan or "free",
    )
    db.add(ws)
    db.flush()
    # Add creator as owner
    member = WorkspaceMember(
        id=str(uuid.uuid4()),
        workspace_id=ws.id,
        user_id=current_user["sub"],
        role="owner",
    )
    db.add(member)
    db.commit()
    db.refresh(ws)
    return {**_workspace_dict(ws, 1), "your_role": "owner"}


@router.get("/current")
async def get_current_workspace(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the user's currently active workspace."""
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user or not user.workspace_id:
        raise HTTPException(status_code=404, detail="No active workspace")
    ws = db.query(Workspace).filter(Workspace.id == user.workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    count = db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == ws.id).count()
    member = db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == ws.id,
        WorkspaceMember.user_id == user.id,
    ).first()
    d = _workspace_dict(ws, count)
    d["your_role"] = member.role if member else "unknown"
    return d


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws, member = _get_workspace_or_403(workspace_id, current_user["sub"], db)
    count = db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == ws.id).count()
    d = _workspace_dict(ws, count)
    d["your_role"] = member.role
    return d


@router.put("/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    req: WorkspaceUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws, _ = _get_workspace_or_403(workspace_id, current_user["sub"], db, require_admin=True)
    if req.name:
        ws.name = req.name
    if req.description is not None:
        ws.description = req.description
    db.commit()
    return {"message": "Workspace updated", "id": ws.id}


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws, member = _get_workspace_or_403(workspace_id, current_user["sub"], db)
    if member.role != "owner":
        raise HTTPException(status_code=403, detail="Only the workspace owner can delete it")
    # Remove all memberships and invites first
    db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace_id).delete()
    db.query(WorkspaceInvite).filter(WorkspaceInvite.workspace_id == workspace_id).delete()
    db.delete(ws)
    db.commit()
    return {"message": "Workspace deleted"}


@router.get("/{workspace_id}/members")
async def list_members(
    workspace_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_workspace_or_403(workspace_id, current_user["sub"], db)
    members = db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace_id).all()
    result = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        result.append({
            "user_id": m.user_id,
            "username": user.username if user else "unknown",
            "email": user.email if user else "unknown",
            "role": m.role,
            "joined_at": m.joined_at.isoformat(),
        })
    return result


@router.post("/{workspace_id}/invite", status_code=201)
async def invite_member(
    workspace_id: str,
    req: InviteRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_workspace_or_403(workspace_id, current_user["sub"], db, require_admin=True)
    # Check if already invited
    existing = db.query(WorkspaceInvite).filter(
        WorkspaceInvite.workspace_id == workspace_id,
        WorkspaceInvite.email == req.email,
        WorkspaceInvite.accepted == False,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Invite already pending for this email")
    # If user already exists, add directly
    target_user = db.query(User).filter(User.email == req.email).first()
    if target_user:
        existing_member = db.query(WorkspaceMember).filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == target_user.id,
        ).first()
        if existing_member:
            raise HTTPException(status_code=400, detail="User is already a member")
        member = WorkspaceMember(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            user_id=target_user.id,
            role=req.role,
            invited_by=current_user["sub"],
        )
        db.add(member)
        db.commit()
        return {"message": f"User {req.email} added directly", "status": "added"}
    # Create pending invite
    token = str(uuid.uuid4()).replace("-", "")
    invite = WorkspaceInvite(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        invited_by=current_user["sub"],
        email=req.email,
        role=req.role,
        token=token,
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.add(invite)
    db.commit()
    return {"message": f"Invite sent to {req.email}", "status": "invited", "token": token}


@router.delete("/{workspace_id}/members/{user_id}")
async def remove_member(
    workspace_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws, requester = _get_workspace_or_403(workspace_id, current_user["sub"], db)
    # Can remove self, or admin/owner can remove others
    if user_id != current_user["sub"] and requester.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient privileges")
    target = db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == user_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")
    if target.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove the workspace owner")
    db.delete(target)
    db.commit()
    return {"message": "Member removed"}


@router.post("/switch/{workspace_id}")
async def switch_workspace(
    workspace_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Switch the user's active workspace. Returns a new JWT with updated workspace context."""
    _get_workspace_or_403(workspace_id, current_user["sub"], db)
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.workspace_id = workspace_id
    db.commit()
    # Issue new token with updated workspace_id
    new_token = create_access_token({
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "username": user.username,
        "workspace_id": workspace_id,
    })
    return {"access_token": new_token, "workspace_id": workspace_id, "message": "Workspace switched"}
