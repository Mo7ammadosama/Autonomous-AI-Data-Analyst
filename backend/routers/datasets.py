"""
Datasets router: upload, list, delete, profile
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
import os
import shutil
import logging
import io

from models.database import get_db, Dataset
from services.data_processor import load_dataset, profile_dataset, clean_dataset
from services.llm_service import LLMService
from services.export_service import export_dataset, compare_datasets
from security.auth import get_current_user, get_workspace_scope
from sqlalchemy import or_

router = APIRouter()
logger = logging.getLogger(__name__)

_llm = LLMService()


def _trigger_pipeline(dataset_id: str):
    """Background pipeline trigger with its own DB session."""
    from models.database import SessionLocal
    from services.auto_pipeline import run_pipeline
    db = SessionLocal()
    try:
        run_pipeline(dataset_id, db, llm_service=_llm)
    except Exception as e:
        logger.error(f"Background pipeline error for {dataset_id}: {e}")
    finally:
        db.close()


def _sync_catalog(dataset_id: str):
    """Background task: auto-index dataset into the Data Catalog."""
    from models.database import SessionLocal
    from services.catalog_service import catalog_service
    db = SessionLocal()
    try:
        catalog_service.sync_dataset(dataset_id, db)
    except Exception as e:
        logger.error(f"Catalog sync error for {dataset_id}: {e}")
    finally:
        db.close()


def _build_rag_index(dataset_id: str, file_path: str, file_type: str, dataset_name: str):
    """Background task: build RAG vector index for the dataset."""
    try:
        from services.data_processor import load_dataset as _load
        from services.rag_service import build_index
        df = _load(file_path, file_type)
        build_index(df, dataset_id, dataset_name)
        logger.info(f"RAG index built for dataset {dataset_id}")
    except Exception as e:
        logger.warning(f"RAG index build failed for {dataset_id}: {e}")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_dataset(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Upload a dataset file"""
    allowed_types = ["text/csv", "application/json", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel"]
    allowed_extensions = [".csv", ".json", ".xlsx", ".xls", ".parquet", ".tsv"]

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}")

    dataset_id = str(uuid.uuid4())
    filename = f"{dataset_id}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_size = os.path.getsize(file_path)
    display_name = name or os.path.splitext(file.filename)[0]
    file_type = ext.lstrip(".")

    try:
        df = load_dataset(file_path, file_type)
        profile = profile_dataset(df)
        columns_meta = [
            {"name": col, "type": info["semantic_type"], "dtype": info["dtype"], "missing_pct": info["missing_pct"]}
            for col, info in profile["columns"].items()
        ]

        dataset = Dataset(
            id=dataset_id,
            name=display_name,
            filename=file.filename,
            file_path=file_path,
            file_size=file_size,
            file_type=file_type,
            row_count=profile["shape"]["rows"],
            column_count=profile["shape"]["columns"],
            columns_meta=columns_meta,
            status="ready",
            owner_id=current_user["sub"],
            description=description,
        )
    except Exception as e:
        logger.error(f"Dataset processing error: {e}")
        dataset = Dataset(
            id=dataset_id, name=display_name, filename=file.filename,
            file_path=file_path, file_size=file_size, file_type=file_type,
            status="error", owner_id=current_user["sub"],
        )

    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    # Kick off full auto-analysis pipeline + RAG index in background (non-blocking)
    if dataset.status == "ready":
        background_tasks.add_task(_trigger_pipeline, dataset.id)
        background_tasks.add_task(
            _build_rag_index, dataset.id, file_path, file_type, display_name
        )
        background_tasks.add_task(_sync_catalog, dataset.id)
        logger.info(f"Auto-pipeline, RAG index, and catalog sync queued for dataset {dataset.id}")

    return {
        "id": dataset.id, "name": dataset.name, "status": dataset.status,
        "row_count": dataset.row_count, "column_count": dataset.column_count,
        "file_size": dataset.file_size, "columns_meta": dataset.columns_meta,
        "pipeline_queued": dataset.status == "ready",
    }


@router.get("/")
async def list_datasets(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    scope = get_workspace_scope(current_user)
    if scope["is_superadmin"]:
        q = db.query(Dataset)
    elif scope["workspace_id"]:
        q = db.query(Dataset).filter(or_(
            Dataset.owner_id == scope["user_id"],
            Dataset.workspace_id == scope["workspace_id"],
        ))
    else:
        q = db.query(Dataset).filter(Dataset.owner_id == scope["user_id"])
    datasets = q.order_by(Dataset.created_at.desc()).all()
    return [
        {
            "id": d.id, "name": d.name, "filename": d.filename,
            "file_type": d.file_type, "file_size": d.file_size,
            "row_count": d.row_count, "column_count": d.column_count,
            "status": d.status, "created_at": d.created_at.isoformat() if d.created_at else None,
            "description": d.description, "columns_meta": d.columns_meta,
        }
        for d in datasets
    ]


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    scope = get_workspace_scope(current_user)
    if scope["is_superadmin"]:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    elif scope["workspace_id"]:
        dataset = db.query(Dataset).filter(
            Dataset.id == dataset_id,
            or_(Dataset.owner_id == scope["user_id"], Dataset.workspace_id == scope["workspace_id"]),
        ).first()
    else:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.owner_id == scope["user_id"]).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {
        "id": dataset.id, "name": dataset.name, "filename": dataset.filename,
        "file_type": dataset.file_type, "file_size": dataset.file_size,
        "row_count": dataset.row_count, "column_count": dataset.column_count,
        "status": dataset.status, "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
        "description": dataset.description, "columns_meta": dataset.columns_meta,
    }


@router.get("/{dataset_id}/profile")
async def profile_dataset_endpoint(dataset_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    scope = get_workspace_scope(current_user)
    if scope["is_superadmin"]:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    elif scope["workspace_id"]:
        dataset = db.query(Dataset).filter(
            Dataset.id == dataset_id,
            or_(Dataset.owner_id == scope["user_id"], Dataset.workspace_id == scope["workspace_id"]),
        ).first()
    else:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.owner_id == scope["user_id"]).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        df = load_dataset(dataset.file_path, dataset.file_type)
        profile = profile_dataset(df)
        return profile
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Profiling failed: {str(e)}")


@router.get("/{dataset_id}/preview")
async def preview_dataset(dataset_id: str, rows: int = 20, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.owner_id == current_user["sub"]).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        df = load_dataset(dataset.file_path, dataset.file_type)
        preview = df.head(rows).fillna("").astype(str)
        return {"columns": preview.columns.tolist(), "rows": preview.to_dict("records"), "total_rows": len(df)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CleanOptions(BaseModel):
    missing_strategy: Optional[str] = "median"   # median | mean | mode | drop
    remove_outliers: Optional[bool] = False
    outlier_threshold: Optional[float] = 3.0      # z-score threshold
    column_renames: Optional[Dict[str, str]] = None  # {old: new}
    drop_columns: Optional[List[str]] = None


@router.post("/{dataset_id}/clean")
async def clean_dataset_endpoint(
    dataset_id: str,
    opts: Optional[CleanOptions] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.owner_id == current_user["sub"]).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        import numpy as np
        df = load_dataset(dataset.file_path, dataset.file_type)
        report_ops: list = []
        rows_before = len(df)

        # 1. Drop selected columns
        if opts and opts.drop_columns:
            valid = [c for c in opts.drop_columns if c in df.columns]
            if valid:
                df = df.drop(columns=valid)
                report_ops.append(f"Dropped columns: {', '.join(valid)}")

        # 2. Rename columns
        if opts and opts.column_renames:
            valid_renames = {k: v for k, v in opts.column_renames.items() if k in df.columns and v.strip()}
            if valid_renames:
                df = df.rename(columns=valid_renames)
                report_ops.append(f"Renamed {len(valid_renames)} column(s)")

        # 3. Remove duplicates
        dupes = df.duplicated().sum()
        if dupes > 0:
            df = df.drop_duplicates()
            report_ops.append(f"Removed {dupes} duplicate rows")

        # 4. Handle missing values
        strategy = (opts.missing_strategy if opts else None) or "median"
        for col in df.columns:
            missing = int(df[col].isna().sum())
            if missing == 0:
                continue
            dtype = str(df[col].dtype)
            if strategy == "drop":
                df = df.dropna(subset=[col])
                report_ops.append(f"Dropped {missing} rows with missing '{col}'")
            elif "int" in dtype or "float" in dtype:
                if strategy == "mean":
                    df[col] = df[col].fillna(df[col].mean())
                elif strategy == "mode":
                    mv = df[col].mode()
                    df[col] = df[col].fillna(mv[0] if not mv.empty else 0)
                else:  # median (default)
                    df[col] = df[col].fillna(df[col].median())
                report_ops.append(f"Filled {missing} missing in '{col}' ({strategy})")
            elif "object" in dtype:
                mv = df[col].mode()
                df[col] = df[col].fillna(mv[0] if not mv.empty else "")
                report_ops.append(f"Filled {missing} missing in '{col}' (mode)")

        # 5. Remove outliers (numeric cols only, z-score)
        if opts and opts.remove_outliers:
            threshold = opts.outlier_threshold or 3.0
            num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            outlier_rows = 0
            for col in num_cols:
                z = (df[col] - df[col].mean()) / (df[col].std() + 1e-9)
                outliers = (z.abs() > threshold).sum()
                if outliers > 0:
                    df = df[z.abs() <= threshold]
                    outlier_rows += outliers
            if outlier_rows > 0:
                report_ops.append(f"Removed {outlier_rows} outlier rows (z>{threshold})")

        # Save cleaned CSV
        cleaned_path = dataset.file_path.replace(f".{dataset.file_type}", f"_cleaned.csv")
        df.to_csv(cleaned_path, index=False)

        # Update dataset metadata with cleaned file
        dataset.file_path = cleaned_path
        dataset.file_type = "csv"
        dataset.row_count = len(df)
        dataset.column_count = len(df.columns)
        db.commit()

        report = {
            "operations": report_ops,
            "rows_before": rows_before,
            "rows_after": len(df),
            "cols_before": rows_before,
            "cols_after": len(df.columns),
            "preview_columns": df.columns.tolist()[:20],
        }
        return {"report": report, "cleaned_path": cleaned_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dataset_id}/export")
async def export_dataset_endpoint(
    dataset_id: str,
    fmt: str = Query("csv", description="Export format: csv, excel, json, parquet, tsv"),
    columns: Optional[str] = Query(None, description="Comma-separated column names to include"),
    max_rows: Optional[int] = Query(None, description="Maximum rows to export"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Export dataset in various formats (CSV, Excel, JSON, Parquet, TSV)."""
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.owner_id == current_user["sub"]).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        df = load_dataset(dataset.file_path, dataset.file_type)
        col_list = [c.strip() for c in columns.split(",")] if columns else None
        data, media_type, ext = export_dataset(df, fmt=fmt, columns=col_list, max_rows=max_rows)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in dataset.name)
        filename = f"{safe_name}{ext}"
        return StreamingResponse(
            io.BytesIO(data),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CompareRequest(BaseModel):
    dataset_id_b: str


@router.post("/{dataset_id}/compare")
async def compare_datasets_endpoint(
    dataset_id: str,
    body: CompareRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Compare two datasets statistically."""
    ds_a = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.owner_id == current_user["sub"]).first()
    ds_b = db.query(Dataset).filter(Dataset.id == body.dataset_id_b, Dataset.owner_id == current_user["sub"]).first()
    if not ds_a:
        raise HTTPException(status_code=404, detail="Dataset A not found")
    if not ds_b:
        raise HTTPException(status_code=404, detail="Dataset B not found")
    try:
        df_a = load_dataset(ds_a.file_path, ds_a.file_type)
        df_b = load_dataset(ds_b.file_path, ds_b.file_type)
        result = compare_datasets(df_a, df_b, name1=ds_a.name, name2=ds_b.name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.owner_id == current_user["sub"]).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        if os.path.exists(dataset.file_path):
            os.remove(dataset.file_path)
    except Exception:
        pass
    db.delete(dataset)
    db.commit()
    return {"message": "Dataset deleted successfully"}
