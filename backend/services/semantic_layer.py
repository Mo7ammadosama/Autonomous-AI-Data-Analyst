"""
Semantic Layer Service — ThoughtSpot / Looker LookML style governed metric catalog.

Provides a single source of truth for business KPI definitions.
All AI services (NL2SQL, Chat, Alerts) can query this layer to ensure
consistent metric interpretation — no hallucinated definitions.
"""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from models.database import MetricDefinition, Dataset

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  Metric CRUD
# ═══════════════════════════════════════════════════════════════

def create_metric(
    db: Session,
    owner_id: str,
    name: str,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    sql_expression: Optional[str] = None,
    dataset_id: Optional[str] = None,
    source_columns: Optional[List[str]] = None,
    approved_dimensions: Optional[List[str]] = None,
    unit: Optional[str] = None,
    direction: str = "higher_is_better",
    tags: Optional[List[str]] = None,
    workspace_id: Optional[str] = None,
) -> MetricDefinition:
    metric = MetricDefinition(
        owner_id=owner_id,
        workspace_id=workspace_id,
        name=name,
        display_name=display_name or name,
        description=description,
        category=category,
        sql_expression=sql_expression,
        dataset_id=dataset_id,
        source_columns=source_columns or [],
        approved_dimensions=approved_dimensions or [],
        unit=unit,
        direction=direction,
        tags=tags or [],
    )
    db.add(metric)
    db.commit()
    db.refresh(metric)
    logger.info(f"Created metric definition: {name} ({metric.id})")
    return metric


def get_metric(db: Session, metric_id: str) -> Optional[MetricDefinition]:
    return db.query(MetricDefinition).filter(MetricDefinition.id == metric_id).first()


def list_metrics(
    db: Session,
    workspace_id: Optional[str] = None,
    category: Optional[str] = None,
    certified_only: bool = False,
    active_only: bool = True,
) -> List[MetricDefinition]:
    q = db.query(MetricDefinition)
    if workspace_id:
        q = q.filter(MetricDefinition.workspace_id == workspace_id)
    if category:
        q = q.filter(MetricDefinition.category == category)
    if certified_only:
        q = q.filter(MetricDefinition.is_certified == True)
    if active_only:
        q = q.filter(MetricDefinition.is_active == True)
    return q.order_by(MetricDefinition.is_certified.desc(), MetricDefinition.name).all()


def search_metrics(db: Session, query: str, workspace_id: Optional[str] = None) -> List[MetricDefinition]:
    q = db.query(MetricDefinition).filter(MetricDefinition.is_active == True)
    if workspace_id:
        q = q.filter(MetricDefinition.workspace_id == workspace_id)
    term = f"%{query.lower()}%"
    from sqlalchemy import or_, func
    q = q.filter(
        or_(
            func.lower(MetricDefinition.name).like(term),
            func.lower(MetricDefinition.display_name).like(term),
            func.lower(MetricDefinition.description).like(term),
        )
    )
    return q.limit(20).all()


def certify_metric(db: Session, metric_id: str, certified_by: str) -> MetricDefinition:
    from datetime import datetime
    metric = get_metric(db, metric_id)
    if not metric:
        raise ValueError(f"Metric {metric_id} not found")
    metric.is_certified = True
    metric.certified_by = certified_by
    metric.certified_at = datetime.utcnow()
    db.commit()
    db.refresh(metric)
    return metric


def update_metric(db: Session, metric_id: str, updates: Dict[str, Any]) -> MetricDefinition:
    from datetime import datetime
    metric = get_metric(db, metric_id)
    if not metric:
        raise ValueError(f"Metric {metric_id} not found")
    for k, v in updates.items():
        if hasattr(metric, k):
            setattr(metric, k, v)
    metric.updated_at = datetime.utcnow()
    # Any edit revokes certification (data integrity)
    if any(k in updates for k in ("sql_expression", "source_columns", "dataset_id")):
        metric.is_certified = False
        metric.certified_by = None
        metric.certified_at = None
    db.commit()
    db.refresh(metric)
    return metric


def delete_metric(db: Session, metric_id: str) -> bool:
    metric = get_metric(db, metric_id)
    if not metric:
        return False
    metric.is_active = False  # soft delete
    db.commit()
    return True


# ═══════════════════════════════════════════════════════════════
#  Lineage
# ═══════════════════════════════════════════════════════════════

def get_lineage(db: Session, metric_id: str) -> Dict[str, Any]:
    """
    Return the lineage graph for a metric:
    dataset → source columns → sql_expression → metric
    """
    metric = get_metric(db, metric_id)
    if not metric:
        return {}

    lineage: Dict[str, Any] = {
        "metric_id": metric.id,
        "metric_name": metric.name,
        "nodes": [],
        "edges": [],
    }

    # Dataset node
    if metric.dataset_id:
        dataset = db.query(Dataset).filter(Dataset.id == metric.dataset_id).first()
        if dataset:
            lineage["nodes"].append({"id": dataset.id, "type": "dataset", "name": dataset.name})
            # Source columns
            for col in (metric.source_columns or []):
                col_id = f"{dataset.id}:{col}"
                lineage["nodes"].append({"id": col_id, "type": "column", "name": col})
                lineage["edges"].append({"from": dataset.id, "to": col_id})
                lineage["edges"].append({"from": col_id, "to": metric.id})

    # Metric node
    lineage["nodes"].append({
        "id": metric.id,
        "type": "metric",
        "name": metric.name,
        "is_certified": metric.is_certified,
        "sql": metric.sql_expression,
    })

    # Stored lineage extras
    if metric.lineage:
        lineage["extras"] = metric.lineage

    return lineage


# ═══════════════════════════════════════════════════════════════
#  NL2SQL Context Injection
# ═══════════════════════════════════════════════════════════════

def build_metric_context_for_nl2sql(
    db: Session,
    dataset_id: str,
    workspace_id: Optional[str] = None,
) -> str:
    """
    Returns a string to inject into NL2SQL prompts containing governed
    metric definitions, so the AI uses the approved SQL expressions.
    """
    metrics = list_metrics(db, workspace_id=workspace_id, active_only=True)
    # Filter to metrics relevant to this dataset
    relevant = [m for m in metrics if not m.dataset_id or m.dataset_id == dataset_id]
    if not relevant:
        return ""

    lines = ["# Governed Business Metric Definitions (use these SQL expressions):"]
    for m in relevant[:15]:  # max 15 to keep prompt size reasonable
        cert = " [CERTIFIED]" if m.is_certified else ""
        lines.append(f"- **{m.name}**{cert}: {m.sql_expression or 'No SQL defined'}")
        if m.description:
            lines.append(f"  Description: {m.description}")
        if m.approved_dimensions:
            lines.append(f"  Approved dimensions: {', '.join(m.approved_dimensions)}")
        if m.unit:
            lines.append(f"  Unit: {m.unit}")
    lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Auto-discovery: suggest metrics from dataset columns
# ═══════════════════════════════════════════════════════════════

def suggest_metrics_from_dataset(
    db: Session,
    dataset_id: str,
    owner_id: str,
) -> List[Dict[str, Any]]:
    """
    Heuristically suggest metric definitions based on column names.
    Returns suggestions (not yet saved) for the user to review.
    """
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset or not dataset.columns_meta:
        return []

    suggestions = []
    numeric_keywords = {
        "revenue": ("Revenue", "SUM(revenue)", "revenue | finance", "$"),
        "sales": ("Total Sales", "SUM(sales)", "revenue | sales", "$"),
        "amount": ("Total Amount", "SUM(amount)", "finance", "$"),
        "price": ("Average Price", "AVG(price)", "pricing", "$"),
        "count": ("Count", "COUNT(*)", "volume", ""),
        "quantity": ("Total Quantity", "SUM(quantity)", "inventory", "units"),
        "users": ("Active Users", "COUNT(DISTINCT users)", "engagement", "users"),
        "sessions": ("Sessions", "COUNT(sessions)", "engagement", "sessions"),
        "conversion": ("Conversion Rate", "AVG(conversion)", "marketing", "%"),
        "churn": ("Churn Rate", "AVG(churn)", "retention", "%"),
        "profit": ("Profit", "SUM(profit)", "finance", "$"),
        "cost": ("Total Cost", "SUM(cost)", "finance", "$"),
    }

    cols = dataset.columns_meta if isinstance(dataset.columns_meta, list) else []
    for col_meta in cols:
        col_name = (col_meta.get("name") or "").lower() if isinstance(col_meta, dict) else str(col_meta).lower()
        for keyword, (display, sql_expr, category, unit) in numeric_keywords.items():
            if keyword in col_name:
                suggestions.append({
                    "name": display,
                    "display_name": display,
                    "sql_expression": sql_expr.replace(keyword, col_name),
                    "category": category,
                    "unit": unit,
                    "source_columns": [col_name],
                    "dataset_id": dataset_id,
                    "direction": "lower_is_better" if keyword in ("churn", "cost") else "higher_is_better",
                })
                break

    return suggestions[:10]
