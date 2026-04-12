"""
NL2SQL Router — Natural Language to SQL query execution.

Endpoints:
  POST /api/nl2sql/{dataset_id}/query     Natural language → SQL → result + chart
  GET  /api/nl2sql/{dataset_id}/history   Past queries for this dataset
  POST /api/nl2sql/{dataset_id}/feedback  Submit feedback (thumbs up/down) on a query
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import logging

from models.database import get_db, Dataset, NL2SQLQuery
from security.auth import get_current_user
from services.data_processor import load_dataset
from services.nl2sql import NL2SQLService
from services.llm_service import LLMService

logger = logging.getLogger(__name__)
router = APIRouter()

_llm = LLMService()
_nl2sql = NL2SQLService(_llm)


class NLQueryRequest(BaseModel):
    question: str


class FeedbackRequest(BaseModel):
    query_id: str
    feedback: int  # 1 = positive, -1 = negative


@router.post("/{dataset_id}/query")
async def nl_to_sql_query(
    dataset_id: str,
    payload: NLQueryRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Convert a natural language question to SQL, execute it, and return results.
    """
    if not payload.question or len(payload.question.strip()) < 3:
        raise HTTPException(status_code=400, detail="Question is too short.")

    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.owner_id == current_user["sub"],
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    if dataset.status != "ready":
        raise HTTPException(status_code=400, detail="Dataset is not ready for querying.")

    try:
        df = load_dataset(dataset.file_path, dataset.file_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load dataset: {e}")

    # Phase 10: inject governed metric context into NL2SQL
    from services.semantic_layer import build_metric_context_for_nl2sql
    workspace_id = getattr(current_user, "workspace_id", None)
    metric_context = build_metric_context_for_nl2sql(db, dataset_id, workspace_id)
    if metric_context:
        _nl2sql.metric_context = metric_context

    # Phase 11: build thinking trace
    import time
    from services.ai_transparency import ThinkingTrace, score_confidence, enrich_response_with_trace
    trace = ThinkingTrace()
    t0 = time.monotonic()

    result = _nl2sql.run(payload.question, df, dataset.name)

    trace.total_ms = int((time.monotonic() - t0) * 1000)
    trace.sql_generated = result.get("sql")
    trace.tables_used = [dataset.name]
    trace.grounding_sources = ["schema", "sample_values"] + (["semantic_layer"] if metric_context else [])
    trace.model_used = "llm_router"
    trace.confidence_score, trace.confidence_reason = score_confidence(
        sql_generated=result.get("sql"),
        semantic_layer_used=bool(metric_context),
        answer_length=len(str(result.get("data", []))),
    )

    # Persist to audit log
    log = NL2SQLQuery(
        user_id=current_user["sub"],
        dataset_id=dataset_id,
        question=payload.question,
        generated_sql=result.get("sql"),
        result_data=result.get("data", [])[:100],   # Store first 100 rows
        charts=result.get("chart"),
        execution_time_ms=result.get("execution_time_ms"),
        success=result.get("error") is None,
        error_message=result.get("error"),
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    response = {
        **result,
        "query_id": log.id,
        "dataset_name": dataset.name,
        "reasoning": f"Generated SQL using schema + {'governed metrics + ' if metric_context else ''}sample values from {dataset.name}.",
    }
    return enrich_response_with_trace(response, trace)


@router.get("/{dataset_id}/history")
async def get_query_history(
    dataset_id: str,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the NL2SQL query history for a dataset."""
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.owner_id == current_user["sub"],
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found.")

    queries = (
        db.query(NL2SQLQuery)
        .filter(NL2SQLQuery.dataset_id == dataset_id)
        .order_by(NL2SQLQuery.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": q.id,
            "question": q.question,
            "sql": q.generated_sql,
            "row_count": len(q.result_data) if q.result_data else 0,
            "execution_time_ms": q.execution_time_ms,
            "success": q.success,
            "feedback": q.feedback,
            "created_at": q.created_at.isoformat() if q.created_at else None,
        }
        for q in queries
    ]


@router.post("/feedback")
async def submit_feedback(
    payload: FeedbackRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record user feedback on an NL2SQL result."""
    if payload.feedback not in (1, -1):
        raise HTTPException(status_code=400, detail="Feedback must be 1 (positive) or -1 (negative).")

    query = db.query(NL2SQLQuery).filter(
        NL2SQLQuery.id == payload.query_id,
        NL2SQLQuery.user_id == current_user["sub"],
    ).first()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found.")

    query.feedback = payload.feedback
    db.commit()
    return {"status": "ok", "query_id": payload.query_id, "feedback": payload.feedback}
