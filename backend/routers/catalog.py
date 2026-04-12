"""
Data Catalog Router

Endpoints (static paths BEFORE /{id}):
  GET  /api/catalog/search        Full-text search across catalog entries
  GET  /api/catalog/popular       Most-accessed entries
  GET  /api/catalog/tags          All distinct tags
  GET  /api/catalog/              List all entries
  POST /api/catalog/              Create entry (admin)
  GET  /api/catalog/{id}         Get single entry
  PATCH /api/catalog/{id}        Update metadata
  POST  /api/catalog/{id}/certify  Mark entry as certified (admin)
"""

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, CatalogEntry
from security.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────

class CatalogEntryCreate(BaseModel):
    resource_type: str
    resource_id: str
    name: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    sensitivity: Optional[str] = None


class CatalogEntryUpdate(BaseModel):
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    sensitivity: Optional[str] = None


# ── Serializer ────────────────────────────────────────────────────

def _entry_dict(e: CatalogEntry) -> dict:
    return {
        "id": e.id,
        "resource_type": e.resource_type,
        "resource_id": e.resource_id,
        "name": e.name,
        "description": e.description,
        "tags": e.tags or [],
        "owner_id": e.owner_id,
        "is_certified": e.is_certified,
        "sensitivity": e.sensitivity,
        "lineage": e.lineage or {},
        "usage_count": e.usage_count or 0,
        "last_accessed": e.last_accessed.isoformat() if e.last_accessed else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


# ── Static endpoints (MUST be before /{id}) ───────────────────────

@router.get("/search")
async def search_catalog(
    q: str,
    resource_type: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Full-text search on name and description."""
    query = db.query(CatalogEntry).filter(
        CatalogEntry.name.ilike(f"%{q}%") |
        CatalogEntry.description.ilike(f"%{q}%")
    )
    if resource_type:
        query = query.filter(CatalogEntry.resource_type == resource_type)
    entries = query.order_by(CatalogEntry.usage_count.desc()).limit(limit).all()

    # Optional tag filter (post-query, since tags stored as JSON)
    if tag:
        entries = [e for e in entries if tag in (e.tags or [])]

    return [_entry_dict(e) for e in entries]


@router.get("/popular")
async def popular_entries(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return most-accessed catalog entries."""
    entries = (
        db.query(CatalogEntry)
        .order_by(CatalogEntry.usage_count.desc())
        .limit(limit)
        .all()
    )
    return [_entry_dict(e) for e in entries]


@router.get("/tags")
async def list_tags(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return all distinct tags used across catalog entries."""
    all_entries = db.query(CatalogEntry).all()
    tags: set = set()
    for e in all_entries:
        for tag in (e.tags or []):
            tags.add(tag)
    return sorted(tags)


# ── Collection ────────────────────────────────────────────────────

@router.get("/")
async def list_catalog(
    resource_type: Optional[str] = None,
    is_certified: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = db.query(CatalogEntry)
    if resource_type:
        query = query.filter(CatalogEntry.resource_type == resource_type)
    if is_certified is not None:
        query = query.filter(CatalogEntry.is_certified == is_certified)
    entries = (
        query
        .order_by(CatalogEntry.usage_count.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = query.count()
    return {"total": total, "entries": [_entry_dict(e) for e in entries]}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_catalog_entry(
    payload: CatalogEntryCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    entry = CatalogEntry(
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        name=payload.name,
        description=payload.description,
        tags=payload.tags or [],
        owner_id=current_user["sub"],
        sensitivity=payload.sensitivity,
        lineage={},
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _entry_dict(entry)


# ── Single entry ──────────────────────────────────────────────────

@router.get("/{entry_id}")
async def get_catalog_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from services.catalog_service import catalog_service
    entry = db.query(CatalogEntry).filter(CatalogEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Catalog entry not found")
    catalog_service.record_access(entry.resource_type, entry.resource_id, db)
    return _entry_dict(entry)


@router.patch("/{entry_id}")
async def update_catalog_entry(
    entry_id: str,
    payload: CatalogEntryUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    entry = db.query(CatalogEntry).filter(CatalogEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Catalog entry not found")
    if entry.owner_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Cannot edit another user's catalog entry")
    if payload.description is not None:
        entry.description = payload.description
    if payload.tags is not None:
        entry.tags = payload.tags
    if payload.sensitivity is not None:
        entry.sensitivity = payload.sensitivity
    db.commit()
    db.refresh(entry)
    return _entry_dict(entry)


@router.post("/{entry_id}/certify")
async def certify_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Toggle certification status (admin action)."""
    entry = db.query(CatalogEntry).filter(CatalogEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Catalog entry not found")
    entry.is_certified = not entry.is_certified
    entry.steward_id = current_user["sub"]
    db.commit()
    return {"id": entry.id, "is_certified": entry.is_certified}
