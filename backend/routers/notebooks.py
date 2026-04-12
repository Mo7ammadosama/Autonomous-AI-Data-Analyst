"""
Notebooks router — Julius-style collaborative analysis notebooks.

Routes (specific before parameterized):
  GET    /api/notebooks
  POST   /api/notebooks
  GET    /api/notebooks/templates
  POST   /api/notebooks/templates/{template_id}/use
  GET    /api/notebooks/{id}
  PUT    /api/notebooks/{id}
  DELETE /api/notebooks/{id}
  POST   /api/notebooks/{id}/run
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, Notebook, NotebookCell, Dataset
from security.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notebooks", tags=["Notebooks"])


# ─────────────────────────────────────────────────────────────────────────────
#  Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────

class CellIn(BaseModel):
    cell_type: str          # markdown | data | ai_prompt | code | chart
    content: Optional[str] = ""
    position: int = 0
    cell_metadata: dict = {}


class NotebookCreate(BaseModel):
    title: str = "Untitled Notebook"
    description: Optional[str] = None
    domain: Optional[str] = None
    dataset_id: Optional[str] = None
    cells: list[CellIn] = []


class NotebookUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    domain: Optional[str] = None
    dataset_id: Optional[str] = None


class CellUpdate(BaseModel):
    cells: list[CellIn]


def _notebook_dict(nb: Notebook) -> dict:
    return {
        "id": nb.id,
        "title": nb.title,
        "description": nb.description,
        "user_id": nb.user_id,
        "dataset_id": nb.dataset_id,
        "domain": nb.domain,
        "tags": nb.tags or [],
        "is_template": nb.is_template,
        "template_name": nb.template_name,
        "run_count": nb.run_count,
        "is_public": nb.is_public,
        "created_at": nb.created_at.isoformat(),
        "updated_at": nb.updated_at.isoformat(),
        "cells": [_cell_dict(c) for c in (nb.cells or [])],
    }


def _cell_dict(c: NotebookCell) -> dict:
    return {
        "id": c.id,
        "notebook_id": c.notebook_id,
        "cell_type": c.cell_type,
        "position": c.position,
        "content": c.content or "",
        "output": c.output,
        "output_type": c.output_type,
        "cell_metadata": c.cell_metadata or {},
        "is_executed": c.is_executed,
        "executed_at": c.executed_at.isoformat() if c.executed_at else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Built-in templates (served from memory, not DB)
# ─────────────────────────────────────────────────────────────────────────────

BUILTIN_TEMPLATES = [
    {
        "id": "finance-pl",
        "name": "P&L Analysis",
        "domain": "Finance",
        "description": "Analyze gross margin, EBITDA, and YoY variance with executive summary.",
        "run_count": 3842,
        "cells": [
            {"cell_type": "markdown", "content": "# P&L Analysis\nUpload your income statement data and run this notebook to get a full P&L analysis with executive insights.", "position": 0},
            {"cell_type": "data",      "content": "Upload your P&L CSV (columns: date, revenue, cogs, opex, ebitda)", "position": 1},
            {"cell_type": "ai_prompt", "content": "Calculate gross margin, EBITDA margin, and YoY variance for each period. Highlight any periods with margin compression.", "position": 2},
            {"cell_type": "code",      "content": "import pandas as pd\n# df is pre-loaded from the data cell\ndf['gross_margin_pct'] = (df['revenue'] - df['cogs']) / df['revenue'] * 100\ndf['ebitda_margin_pct'] = df['ebitda'] / df['revenue'] * 100\nprint(df[['date','gross_margin_pct','ebitda_margin_pct']].to_string())", "position": 3},
            {"cell_type": "chart",     "content": "Render a dual-axis line chart showing gross margin % and EBITDA % over time", "position": 4},
            {"cell_type": "ai_prompt", "content": "Write a 3-paragraph executive summary with: (1) headline KPIs, (2) key risks, (3) 3 specific recommendations for improving margins.", "position": 5},
        ],
    },
    {
        "id": "finance-cashflow",
        "name": "Cash Flow Analysis",
        "domain": "Finance",
        "description": "Operating, investing, and financing cash flow breakdown with burn rate analysis.",
        "run_count": 2156,
        "cells": [
            {"cell_type": "markdown", "content": "# Cash Flow Analysis\nAnalyze cash flow from operating, investing, and financing activities.", "position": 0},
            {"cell_type": "data",     "content": "Upload cash flow statement CSV", "position": 1},
            {"cell_type": "ai_prompt","content": "Calculate net cash position, burn rate, and runway in months. Flag any months with negative free cash flow.", "position": 2},
            {"cell_type": "chart",    "content": "Waterfall chart showing cash flow components by quarter", "position": 3},
            {"cell_type": "ai_prompt","content": "Give executive summary with runway analysis and top 3 cash optimization actions.", "position": 4},
        ],
    },
    {
        "id": "finance-budget-vs-actual",
        "name": "Budget vs Actual",
        "domain": "Finance",
        "description": "Variance analysis between planned budget and actual performance.",
        "run_count": 4291,
        "cells": [
            {"cell_type": "markdown", "content": "# Budget vs Actual Analysis\nTrack variance between budget and actuals across all departments.", "position": 0},
            {"cell_type": "data",     "content": "Upload budget vs actual CSV (columns: department, budget, actual, period)", "position": 1},
            {"cell_type": "ai_prompt","content": "Calculate absolute and percentage variance per department. Identify top 3 over-budget areas and top 3 under-budget areas.", "position": 2},
            {"cell_type": "chart",    "content": "Grouped bar chart: budget vs actual by department", "position": 3},
            {"cell_type": "ai_prompt","content": "Executive summary: which departments need corrective action and recommended budget reallocation.", "position": 4},
        ],
    },
    {
        "id": "finance-kpi-dashboard",
        "name": "Financial KPI Dashboard",
        "domain": "Finance",
        "description": "Comprehensive financial KPI scorecard with trend analysis.",
        "run_count": 1987,
        "cells": [
            {"cell_type": "markdown", "content": "# Financial KPI Dashboard\nGenerate a complete financial KPI scorecard.", "position": 0},
            {"cell_type": "data",     "content": "Upload financial data CSV", "position": 1},
            {"cell_type": "ai_prompt","content": "Calculate: Revenue Growth, Gross Margin, EBITDA Margin, Current Ratio, Debt-to-Equity, ROE, ROA. Show MoM and YoY trends.", "position": 2},
            {"cell_type": "chart",    "content": "KPI scorecard with trend sparklines for each metric", "position": 3},
            {"cell_type": "ai_prompt","content": "Board-ready KPI summary with red/amber/green RAG status for each metric.", "position": 4},
        ],
    },
    {
        "id": "sales-performance",
        "name": "Sales Performance",
        "domain": "Sales",
        "description": "Full sales performance analysis by rep, region, and product.",
        "run_count": 5123,
        "cells": [
            {"cell_type": "markdown", "content": "# Sales Performance Analysis\nAnalyze sales by rep, region, product, and time period.", "position": 0},
            {"cell_type": "data",     "content": "Upload sales data CSV", "position": 1},
            {"cell_type": "ai_prompt","content": "Rank reps by performance. Identify top 20% driving 80% of revenue. Find underperforming regions.", "position": 2},
            {"cell_type": "chart",    "content": "Bar chart: revenue by rep, line chart: monthly trend, heatmap: region × product", "position": 3},
            {"cell_type": "ai_prompt","content": "Sales director briefing: top performers to retain, bottom performers needing coaching, territory rebalancing recommendations.", "position": 4},
        ],
    },
    {
        "id": "sales-pipeline",
        "name": "Pipeline Analysis",
        "domain": "Sales",
        "description": "Sales pipeline health, conversion rates, and revenue forecast.",
        "run_count": 3456,
        "cells": [
            {"cell_type": "markdown", "content": "# Sales Pipeline Analysis\nAnalyze pipeline health and conversion rates.", "position": 0},
            {"cell_type": "data",     "content": "Upload pipeline CSV (columns: opportunity, stage, value, close_date, rep)", "position": 1},
            {"cell_type": "ai_prompt","content": "Calculate: pipeline coverage ratio, stage conversion rates, average deal velocity, weighted forecast.", "position": 2},
            {"cell_type": "chart",    "content": "Funnel chart: pipeline by stage, scatter: deal size vs probability", "position": 3},
            {"cell_type": "ai_prompt","content": "CRO briefing: forecast accuracy, risk deals, recommended actions to close current quarter gap.", "position": 4},
        ],
    },
    {
        "id": "marketing-campaign-roi",
        "name": "Campaign ROI",
        "domain": "Marketing",
        "description": "Multi-channel campaign performance with ROI and attribution analysis.",
        "run_count": 2789,
        "cells": [
            {"cell_type": "markdown", "content": "# Campaign ROI Analysis\nMeasure marketing campaign effectiveness across channels.", "position": 0},
            {"cell_type": "data",     "content": "Upload campaign data CSV (spend, impressions, clicks, conversions, revenue per channel)", "position": 1},
            {"cell_type": "ai_prompt","content": "Calculate: CAC, ROAS, CPL, conversion rate by channel. Identify best and worst performing channels.", "position": 2},
            {"cell_type": "chart",    "content": "Bar chart: ROAS by channel, scatter: spend vs conversions", "position": 3},
            {"cell_type": "ai_prompt","content": "CMO briefing: which channels to scale, which to cut, recommended budget reallocation for next quarter.", "position": 4},
        ],
    },
    {
        "id": "marketing-funnel",
        "name": "Funnel Analysis",
        "domain": "Marketing",
        "description": "Full-funnel conversion analysis with drop-off identification.",
        "run_count": 1654,
        "cells": [
            {"cell_type": "markdown", "content": "# Marketing Funnel Analysis\nAnalyze conversion rates at each funnel stage.", "position": 0},
            {"cell_type": "data",     "content": "Upload funnel data CSV (stage, visitors, date)", "position": 1},
            {"cell_type": "ai_prompt","content": "Calculate stage-to-stage conversion rates. Identify biggest drop-off point and its dollar impact.", "position": 2},
            {"cell_type": "chart",    "content": "Funnel visualization with conversion rates and drop-off amounts", "position": 3},
            {"cell_type": "ai_prompt","content": "Growth team briefing: top 3 funnel optimization opportunities ranked by revenue impact.", "position": 4},
        ],
    },
    {
        "id": "operations-inventory",
        "name": "Inventory Analysis",
        "domain": "Operations",
        "description": "Inventory turnover, carrying costs, and stockout risk analysis.",
        "run_count": 2341,
        "cells": [
            {"cell_type": "markdown", "content": "# Inventory Analysis\nAnalyze inventory health, turnover, and optimization opportunities.", "position": 0},
            {"cell_type": "data",     "content": "Upload inventory CSV (SKU, quantity, cost, category, last_sold_date)", "position": 1},
            {"cell_type": "ai_prompt","content": "Calculate inventory turnover rate, days on hand, carrying cost, and identify slow-moving/dead stock.", "position": 2},
            {"cell_type": "chart",    "content": "Bar chart: turnover by category, scatter: days on hand vs carrying cost", "position": 3},
            {"cell_type": "ai_prompt","content": "Operations director briefing: top 10 items to liquidate, reorder recommendations, estimated working capital freed up.", "position": 4},
        ],
    },
    {
        "id": "operations-supply-chain",
        "name": "Supply Chain KPIs",
        "domain": "Operations",
        "description": "End-to-end supply chain performance with on-time delivery and cost analysis.",
        "run_count": 1892,
        "cells": [
            {"cell_type": "markdown", "content": "# Supply Chain KPI Analysis\nMeasure supply chain performance and identify bottlenecks.", "position": 0},
            {"cell_type": "data",     "content": "Upload supply chain data CSV", "position": 1},
            {"cell_type": "ai_prompt","content": "Calculate: on-time delivery rate, perfect order rate, supplier lead time variance, landed cost per unit.", "position": 2},
            {"cell_type": "chart",    "content": "Line chart: OTD rate trend, bar chart: cost by supplier", "position": 3},
            {"cell_type": "ai_prompt","content": "COO briefing: supply chain risk exposure, top 3 supplier issues, cost reduction opportunities.", "position": 4},
        ],
    },
    {
        "id": "hr-employee-performance",
        "name": "Employee Performance",
        "domain": "HR",
        "description": "Workforce performance analysis with attrition risk and productivity metrics.",
        "run_count": 1543,
        "cells": [
            {"cell_type": "markdown", "content": "# Employee Performance Analysis\nAnalyze workforce performance, productivity, and attrition risk.", "position": 0},
            {"cell_type": "data",     "content": "Upload HR data CSV (employee_id, department, tenure, performance_score, salary)", "position": 1},
            {"cell_type": "ai_prompt","content": "Identify top performers, attrition risk employees, departments with performance gaps. Calculate revenue per employee.", "position": 2},
            {"cell_type": "chart",    "content": "Scatter: tenure vs performance, bar: headcount by department, heatmap: performance distribution", "position": 3},
            {"cell_type": "ai_prompt","content": "CHRO briefing: retention risk assessment, compensation equity findings, recommended interventions.", "position": 4},
        ],
    },
    {
        "id": "sales-churn",
        "name": "Churn Prediction",
        "domain": "Sales",
        "description": "Customer churn analysis with predictive signals and retention recommendations.",
        "run_count": 2987,
        "cells": [
            {"cell_type": "markdown", "content": "# Churn Prediction Analysis\nIdentify at-risk customers and quantify churn impact.", "position": 0},
            {"cell_type": "data",     "content": "Upload customer data CSV (customer_id, last_purchase_date, purchase_frequency, total_value, support_tickets)", "position": 1},
            {"cell_type": "ai_prompt","content": "Segment customers by churn risk (high/medium/low). Calculate potential revenue at risk. Identify top churn signals.", "position": 2},
            {"cell_type": "chart",    "content": "Scatter: recency vs frequency colored by risk, bar: revenue at risk by segment", "position": 3},
            {"cell_type": "ai_prompt","content": "Revenue retention briefing: top 50 high-risk accounts, recommended win-back campaigns, estimated retention ROI.", "position": 4},
        ],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
#  Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("")
def list_notebooks(db: Session = Depends(get_db), user=Depends(get_current_user)):
    notebooks = db.query(Notebook).filter(
        Notebook.user_id == user["sub"],
        Notebook.is_template.is_(False),
    ).order_by(Notebook.updated_at.desc()).all()
    return [_notebook_dict(nb) for nb in notebooks]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_notebook(body: NotebookCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    import uuid
    nb = Notebook(
        id=str(uuid.uuid4()),
        title=body.title,
        description=body.description,
        domain=body.domain,
        dataset_id=body.dataset_id,
        user_id=user["sub"],
    )
    db.add(nb)
    db.flush()
    for i, c in enumerate(body.cells):
        cell = NotebookCell(
            id=str(uuid.uuid4()),
            notebook_id=nb.id,
            cell_type=c.cell_type,
            position=c.position if c.position else i,
            content=c.content,
            cell_metadata=c.cell_metadata,
        )
        db.add(cell)
    db.commit()
    db.refresh(nb)
    return _notebook_dict(nb)


# IMPORTANT: /templates routes MUST come before /{notebook_id}
@router.get("/templates")
def list_templates():
    """Return built-in notebook templates."""
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "domain": t["domain"],
            "description": t["description"],
            "run_count": t["run_count"],
            "cell_count": len(t["cells"]),
        }
        for t in BUILTIN_TEMPLATES
    ]


@router.post("/templates/{template_id}/use", status_code=status.HTTP_201_CREATED)
def use_template(
    template_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new notebook from a built-in template."""
    import uuid as _uuid

    template = next((t for t in BUILTIN_TEMPLATES if t["id"] == template_id), None)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    nb = Notebook(
        id=str(_uuid.uuid4()),
        title=template["name"],
        description=template["description"],
        domain=template["domain"].lower(),
        template_id=template_id,
        template_name=template["name"],
        user_id=user["sub"],
    )
    db.add(nb)
    db.flush()
    for c in template["cells"]:
        cell = NotebookCell(
            id=str(_uuid.uuid4()),
            notebook_id=nb.id,
            cell_type=c["cell_type"],
            position=c["position"],
            content=c["content"],
        )
        db.add(cell)
    db.commit()
    db.refresh(nb)
    return _notebook_dict(nb)


@router.get("/{notebook_id}")
def get_notebook(notebook_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    nb = db.query(Notebook).filter(Notebook.id == notebook_id, Notebook.user_id == user["sub"]).first()
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return _notebook_dict(nb)


@router.put("/{notebook_id}")
def update_notebook(
    notebook_id: str,
    body: NotebookUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    nb = db.query(Notebook).filter(Notebook.id == notebook_id, Notebook.user_id == user["sub"]).first()
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")
    if body.title is not None:
        nb.title = body.title
    if body.description is not None:
        nb.description = body.description
    if body.domain is not None:
        nb.domain = body.domain
    if body.dataset_id is not None:
        nb.dataset_id = body.dataset_id
    nb.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(nb)
    return _notebook_dict(nb)


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notebook(notebook_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    nb = db.query(Notebook).filter(Notebook.id == notebook_id, Notebook.user_id == user["sub"]).first()
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")
    db.delete(nb)
    db.commit()


@router.post("/{notebook_id}/cells")
def save_cells(
    notebook_id: str,
    body: CellUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Replace all cells in a notebook."""
    import uuid as _uuid
    nb = db.query(Notebook).filter(Notebook.id == notebook_id, Notebook.user_id == user["sub"]).first()
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")

    # Delete existing cells
    db.query(NotebookCell).filter(NotebookCell.notebook_id == notebook_id).delete()
    db.flush()

    for i, c in enumerate(body.cells):
        cell = NotebookCell(
            id=str(_uuid.uuid4()),
            notebook_id=nb.id,
            cell_type=c.cell_type,
            position=c.position if c.position else i,
            content=c.content,
            cell_metadata=c.cell_metadata,
        )
        db.add(cell)
    nb.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(nb)
    return _notebook_dict(nb)


@router.post("/{notebook_id}/run")
def run_notebook(
    notebook_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Execute all cells in sequence and return results."""
    nb = db.query(Notebook).filter(Notebook.id == notebook_id, Notebook.user_id == user["sub"]).first()
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")

    results = []
    for cell in nb.cells:
        cell_result = {"cell_id": cell.id, "cell_type": cell.cell_type, "output": None, "output_type": "text", "error": None}
        try:
            if cell.cell_type == "markdown":
                cell_result["output"] = cell.content
                cell_result["output_type"] = "markdown"
            elif cell.cell_type == "ai_prompt" and cell.content:
                from services.llm_service import LLMService
                llm = LLMService()
                context = f"Notebook: {nb.title}\nDataset: {nb.dataset_id or 'none'}\nDomain: {nb.domain or 'general'}"
                prompt = f"{context}\n\nUser instruction: {cell.content}\n\nProvide a concise, data-driven response."
                result = llm.complete(prompt, max_tokens=1000)
                cell_result["output"] = result
                cell_result["output_type"] = "markdown"
            elif cell.cell_type == "code" and cell.content:
                from services.sandbox import PythonSandbox
                sandbox = PythonSandbox(timeout=30)
                sb_result = sandbox.execute(cell.content)
                if sb_result.error:
                    cell_result["error"] = sb_result.error
                    cell_result["output_type"] = "error"
                else:
                    cell_result["output"] = sb_result.output or "(no output)"
                    cell_result["output_type"] = "text"
                    if sb_result.figures:
                        cell_result["figures"] = sb_result.figures
            elif cell.cell_type == "data":
                if nb.dataset_id:
                    ds = db.query(Dataset).filter(Dataset.id == nb.dataset_id).first()
                    if ds:
                        cell_result["output"] = f"Dataset: {ds.name} — {ds.row_count} rows × {ds.column_count} columns"
                    else:
                        cell_result["output"] = "No dataset loaded"
                else:
                    cell_result["output"] = "No dataset selected"
                cell_result["output_type"] = "text"
            else:
                cell_result["output"] = "(skipped)"

            # Persist output
            cell.output = json.dumps(cell_result.get("output")) if cell_result.get("output") else None
            cell.output_type = cell_result["output_type"]
            cell.is_executed = True
            cell.executed_at = datetime.utcnow()

        except Exception as exc:
            cell_result["error"] = str(exc)
            cell_result["output_type"] = "error"
            logger.warning(f"Cell {cell.id} error: {exc}")

        results.append(cell_result)

    nb.run_count += 1
    nb.updated_at = datetime.utcnow()
    db.commit()

    return {"notebook_id": notebook_id, "cells_executed": len(results), "results": results}
