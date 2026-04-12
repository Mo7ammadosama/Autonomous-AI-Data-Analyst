"""
Data Connections Router — CRUD + test + query for external database connections.

Endpoints:
  POST   /api/connections/               Create connection
  GET    /api/connections/               List user's connections
  GET    /api/connections/{id}           Get connection details
  PUT    /api/connections/{id}           Update connection
  DELETE /api/connections/{id}           Delete connection
  POST   /api/connections/{id}/test      Test connectivity
  GET    /api/connections/{id}/tables    List tables
  GET    /api/connections/{id}/schema/{table}  Get table columns
  POST   /api/connections/{id}/query     Run SELECT query
  POST   /api/connections/{id}/import    Import query result as Dataset
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, DataConnection, Dataset
from security.auth import get_current_user, get_workspace_scope
from sqlalchemy import or_
from services.data_connection import (
    connection_service, encrypt_credential, decrypt_credential
)
from services.data_processor import profile_dataset, load_dataset

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
SUPPORTED_TYPES = {
    "postgresql", "mysql", "sqlite",          # SQL
    "google_sheets", "mongodb", "rest_api",   # Cloud
    "s3", "bigquery",                         # Cloud storage / warehouse
}


# ── Pydantic schemas ─────────────────────────────────────────────

class ConnectionCreate(BaseModel):
    name: str
    connection_type: str          # postgresql | mysql | sqlite | google_sheets | mongodb | rest_api | s3 | bigquery
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    schema_name: Optional[str] = None
    extra_config: Optional[Dict] = None


class ConnectionUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    schema_name: Optional[str] = None
    extra_config: Optional[Dict] = None


class QueryRequest(BaseModel):
    sql: str
    max_rows: int = 1000


class ImportRequest(BaseModel):
    sql: str
    dataset_name: str


def _serialize(conn: DataConnection, include_password: bool = False) -> dict:
    extra = conn.extra_config or {}
    schema_name = extra.get("schema_name")
    return {
        "id": conn.id,
        "name": conn.name,
        "connection_type": conn.connection_type,
        "host": conn.host,
        "port": conn.port,
        "database": conn.database,
        "username": conn.username,
        "schema_name": schema_name,
        "is_active": conn.is_active,
        "last_synced": conn.last_synced.isoformat() if conn.last_synced else None,
        "created_at": conn.created_at.isoformat() if conn.created_at else None,
    }


def _get_conn_or_404(conn_id: str, user_id: str, db: Session) -> DataConnection:
    conn = db.query(DataConnection).filter(
        DataConnection.id == conn_id,
        DataConnection.user_id == user_id,
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn


def _extract_creds(conn: DataConnection):
    """Return decrypted connection credentials."""
    extra = conn.extra_config or {}
    return {
        "connection_type": conn.connection_type,
        "host": conn.host or "",
        "port": conn.port,
        "database": conn.database,
        "username": conn.username or "",
        "password": decrypt_credential(conn.credentials_ref or ""),
        "schema": extra.get("schema_name"),
        "extra_config": extra,
    }


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: ConnectionCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.connection_type not in SUPPORTED_TYPES:
        raise HTTPException(status_code=400, detail=f"Supported types: {SUPPORTED_TYPES}")

    extra = payload.extra_config or {}
    if payload.schema_name:
        extra["schema_name"] = payload.schema_name

    conn = DataConnection(
        user_id=current_user["sub"],
        name=payload.name,
        connection_type=payload.connection_type,
        host=payload.host,
        port=payload.port,
        database=payload.database or "",
        username=payload.username,
        credentials_ref=encrypt_credential(payload.password or ""),
        extra_config=extra,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return _serialize(conn)


@router.get("/")
async def list_connections(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = get_workspace_scope(current_user)
    if scope["is_superadmin"]:
        q = db.query(DataConnection)
    elif scope["workspace_id"]:
        q = db.query(DataConnection).filter(or_(
            DataConnection.user_id == scope["user_id"],
            DataConnection.workspace_id == scope["workspace_id"],
        ))
    else:
        q = db.query(DataConnection).filter(DataConnection.user_id == scope["user_id"])
    conns = q.order_by(DataConnection.created_at.desc()).all()
    return [_serialize(c) for c in conns]


@router.get("/{conn_id}")
async def get_connection(
    conn_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _serialize(_get_conn_or_404(conn_id, current_user["sub"], db))


@router.put("/{conn_id}")
async def update_connection(
    conn_id: str,
    payload: ConnectionUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = _get_conn_or_404(conn_id, current_user["sub"], db)
    for field in ("name", "host", "port", "database", "username", "extra_config"):
        val = getattr(payload, field)
        if val is not None:
            setattr(conn, field, val)
    if payload.password is not None:
        conn.credentials_ref = encrypt_credential(payload.password)
    db.commit()
    db.refresh(conn)
    return _serialize(conn)


@router.delete("/{conn_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    conn_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = _get_conn_or_404(conn_id, current_user["sub"], db)
    db.delete(conn)
    db.commit()


@router.post("/{conn_id}/test")
async def test_connection(
    conn_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = _get_conn_or_404(conn_id, current_user["sub"], db)
    creds = _extract_creds(conn)
    result = connection_service.test_connection(**{k: v for k, v in creds.items() if k != "schema"})
    if result["success"]:
        conn.last_synced = datetime.utcnow()
        db.commit()
    return result


@router.get("/{conn_id}/tables")
async def list_tables(
    conn_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = _get_conn_or_404(conn_id, current_user["sub"], db)
    creds = _extract_creds(conn)
    try:
        tables = connection_service.list_tables(
            creds["connection_type"], creds["host"], creds["port"],
            creds["database"], creds["username"], creds["password"],
            schema=creds["schema"], extra_config=creds["extra_config"],
        )
        return {"tables": tables, "count": len(tables)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{conn_id}/schema/{table_name}")
async def get_table_schema(
    conn_id: str,
    table_name: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = _get_conn_or_404(conn_id, current_user["sub"], db)
    creds = _extract_creds(conn)
    try:
        columns = connection_service.get_table_schema(
            creds["connection_type"], creds["host"], creds["port"],
            creds["database"], creds["username"], creds["password"],
            table_name=table_name, schema=creds["schema"],
        )
        return {"table": table_name, "columns": columns}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{conn_id}/query")
async def run_query(
    conn_id: str,
    payload: QueryRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.sql.strip():
        raise HTTPException(status_code=400, detail="SQL query is required")
    conn = _get_conn_or_404(conn_id, current_user["sub"], db)
    creds = _extract_creds(conn)
    result = connection_service.run_query(
        creds["connection_type"], creds["host"], creds["port"],
        creds["database"], creds["username"], creds["password"],
        sql=payload.sql, max_rows=min(payload.max_rows, 5000),
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/{conn_id}/import")
async def import_as_dataset(
    conn_id: str,
    payload: ImportRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import the result of a SQL query as a new Dataset."""
    if not payload.sql.strip():
        raise HTTPException(status_code=400, detail="SQL query is required")
    if not payload.dataset_name.strip():
        raise HTTPException(status_code=400, detail="Dataset name is required")

    conn = _get_conn_or_404(conn_id, current_user["sub"], db)
    creds = _extract_creds(conn)

    success, message, file_path = connection_service.import_as_dataset(
        creds["connection_type"], creds["host"], creds["port"],
        creds["database"], creds["username"], creds["password"],
        sql=payload.sql, dataset_name=payload.dataset_name, upload_dir=UPLOAD_DIR,
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)

    # Create Dataset record
    import uuid
    from services.data_processor import profile_dataset, load_dataset as _load
    dataset_id = str(uuid.uuid4())
    try:
        df = _load(file_path, "csv")
        profile = profile_dataset(df)
        columns_meta = [
            {"name": col, "type": info["semantic_type"], "dtype": info["dtype"], "missing_pct": info["missing_pct"]}
            for col, info in profile["columns"].items()
        ]
        dataset = Dataset(
            id=dataset_id, name=payload.dataset_name, filename=f"{dataset_id}.csv",
            file_path=file_path, file_size=os.path.getsize(file_path),
            file_type="csv", row_count=profile["shape"]["rows"],
            column_count=profile["shape"]["columns"],
            columns_meta=columns_meta, status="ready",
            owner_id=current_user["sub"],
            description=f"Imported from {conn.name} via SQL",
        )
    except Exception:
        dataset = Dataset(
            id=dataset_id, name=payload.dataset_name, filename=f"{dataset_id}.csv",
            file_path=file_path, file_size=os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            file_type="csv", status="ready", owner_id=current_user["sub"],
        )

    db.add(dataset)
    conn.last_synced = datetime.utcnow()
    db.commit()

    # Trigger pipeline
    def _run_pipeline():
        from models.database import SessionLocal
        from services.auto_pipeline import run_pipeline
        from services.llm_service import LLMService
        _db = SessionLocal()
        try:
            run_pipeline(dataset_id, _db, LLMService())
        finally:
            _db.close()

    background_tasks.add_task(_run_pipeline)

    return {
        "dataset_id": dataset_id,
        "dataset_name": payload.dataset_name,
        "row_count": dataset.row_count,
        "message": message,
        "pipeline_queued": True,
    }
