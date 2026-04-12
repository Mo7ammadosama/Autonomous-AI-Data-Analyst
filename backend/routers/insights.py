"""
Insights router: auto-generate AI insights (v2 statistical engine + AI agent).
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import uuid
import logging

from models.database import get_db, Dataset, Insight
from services.data_processor import load_dataset
from services.ai_agent import AIDataAnalystAgent
from services.auto_insights_v2 import generate_insights_v2
from services.cache_service import cache
from security.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)
agent = AIDataAnalystAgent()


def _insight_to_dict(i: Insight) -> dict:
    return {
        "id": i.id,
        "title": i.title,
        "content": i.content,
        "type": i.insight_type,
        "severity": i.severity,
        "metric_value": i.metric_value,
        "metric_change": i.metric_change,
        "dataset_id": i.dataset_id,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }


@router.get("/{dataset_id}")
async def get_insights(
    dataset_id: str,
    refresh: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.owner_id == current_user["sub"],
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Return cached insights unless refresh requested
    if not refresh:
        existing = (
            db.query(Insight)
            .filter(Insight.dataset_id == dataset_id)
            .order_by(Insight.created_at.desc())
            .limit(20)
            .all()
        )
        if existing:
            return [_insight_to_dict(i) for i in existing]

    try:
        df = load_dataset(dataset.file_path, dataset.file_type)

        # v2: statistical engine (always runs, fast)
        v2_insights = generate_insights_v2(df, dataset.name)

        # AI agent: richer narrative insights (runs if LLM available)
        try:
            agent_insights = agent.generate_insights(df, dataset.name)
        except Exception as e:
            logger.debug(f"AI agent insights failed: {e}")
            agent_insights = []

        # Merge: v2 first (statistical), then AI narrative (deduped by title)
        seen_titles = set()
        merged = []
        for ins in v2_insights + agent_insights:
            title = ins.get("title", "")
            if title in seen_titles:
                continue
            seen_titles.add(title)
            merged.append(ins)

        # Clear old insights
        db.query(Insight).filter(Insight.dataset_id == dataset_id).delete()

        saved = []
        for ins in merged[:20]:
            insight = Insight(
                id=str(uuid.uuid4()),
                dataset_id=dataset_id,
                title=ins.get("title", "Insight"),
                content=ins.get("content", ""),
                insight_type=ins.get("insight_type") or ins.get("type", "general"),
                severity=ins.get("severity", "info"),
                metric_value=str(ins.get("metric_value", "")) if ins.get("metric_value") is not None else None,
                metric_change=float(ins.get("metric_change")) if ins.get("metric_change") is not None else None,
            )
            db.add(insight)
            saved.append(_insight_to_dict(insight))

        db.commit()

        # Invalidate analytics cache for this dataset
        cache.invalidate_prefix(f"analytics:{dataset_id}")

        return saved

    except Exception as e:
        logger.error(f"Insights generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_all_insights(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List insights across all datasets owned by user."""
    user_datasets = db.query(Dataset).filter(Dataset.owner_id == current_user["sub"]).all()
    dataset_ids = [d.id for d in user_datasets]
    if not dataset_ids:
        return []
    insights = (
        db.query(Insight)
        .filter(Insight.dataset_id.in_(dataset_ids))
        .order_by(Insight.created_at.desc())
        .limit(50)
        .all()
    )
    return [_insight_to_dict(i) for i in insights]
