"""phase6_ai_supremacy

Revision ID: 006_phase6
Revises: d90aa225954e
Create Date: 2026-03-14 00:00:00.000000

Adds:
  - llm_usage_logs
  - rca_results
  - automl_jobs
  - automl_predictions
  - dashboard_comments   (Phase 8, bundled here for convenience)
  - dashboard_versions   (Phase 8)
  - dashboard_templates  (Phase 8)
  - catalog_entries      (Phase 8)
  - alert table extension: Slack / Teams / Telegram columns  (Phase 7)
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "006_phase6"
down_revision: Union[str, Sequence[str], None] = "d90aa225954e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── LLM usage logs ──────────────────────────────────────────
    op.create_table(
        "llm_usage_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("task_type", sa.String(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), default=0),
        sa.Column("completion_tokens", sa.Integer(), default=0),
        sa.Column("cost_usd", sa.Float(), default=0.0),
        sa.Column("latency_ms", sa.Integer(), default=0),
        sa.Column("success", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # ── RCA results ─────────────────────────────────────────────
    op.create_table(
        "rca_results",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("dataset_id", sa.String(), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("metric_column", sa.String(), nullable=False),
        sa.Column("date_column", sa.String(), nullable=True),
        sa.Column("comparison_period", sa.String(), default="month"),
        sa.Column("change_pct", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("result_data", sa.JSON(), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("chart", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # ── AutoML jobs ─────────────────────────────────────────────
    op.create_table(
        "automl_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("dataset_id", sa.String(), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("target_column", sa.String(), nullable=False),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), default="queued"),
        sa.Column("best_model", sa.String(), nullable=True),
        sa.Column("cv_score", sa.Float(), nullable=True),
        sa.Column("feature_importance", sa.JSON(), nullable=True),
        sa.Column("confusion_matrix", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("result_data", sa.JSON(), nullable=True),
        sa.Column("model_path", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    # ── AutoML predictions ───────────────────────────────────────
    op.create_table(
        "automl_predictions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("job_id", sa.String(), sa.ForeignKey("automl_jobs.id"), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("input_data", sa.JSON(), nullable=True),
        sa.Column("predictions", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # ── Alert table: add notification channel columns (Phase 7) ──
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("notify_slack", sa.Boolean(), nullable=True, server_default="0"))
        batch_op.add_column(sa.Column("slack_webhook_url", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("notify_teams", sa.Boolean(), nullable=True, server_default="0"))
        batch_op.add_column(sa.Column("teams_webhook_url", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("notify_telegram", sa.Boolean(), nullable=True, server_default="0"))
        batch_op.add_column(sa.Column("telegram_bot_token", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("telegram_chat_id", sa.String(), nullable=True))

    # ── Dashboard comments (Phase 8) ─────────────────────────────
    op.create_table(
        "dashboard_comments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dashboard_id", sa.String(), sa.ForeignKey("dashboards.id"), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("parent_id", sa.String(), sa.ForeignKey("dashboard_comments.id"), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chart_index", sa.Integer(), nullable=True),
        sa.Column("position_x", sa.Float(), nullable=True),
        sa.Column("position_y", sa.Float(), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    # ── Dashboard versions (Phase 8) ─────────────────────────────
    op.create_table(
        "dashboard_versions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dashboard_id", sa.String(), sa.ForeignKey("dashboards.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("layout", sa.JSON(), nullable=True),
        sa.Column("charts", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # ── Dashboard templates (Phase 8) ────────────────────────────
    op.create_table(
        "dashboard_templates",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("industry", sa.String(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("thumbnail_url", sa.String(), nullable=True),
        sa.Column("layout", sa.JSON(), nullable=True),
        sa.Column("charts_config", sa.JSON(), nullable=True),
        sa.Column("column_mappings", sa.JSON(), nullable=True),
        sa.Column("is_featured", sa.Boolean(), default=False),
        sa.Column("usage_count", sa.Integer(), default=0),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # ── Seed 10 built-in templates ───────────────────────────────
    op.bulk_insert(
        sa.table(
            "dashboard_templates",
            sa.column("id", sa.String),
            sa.column("name", sa.String),
            sa.column("description", sa.Text),
            sa.column("industry", sa.String),
            sa.column("tags", sa.JSON),
            sa.column("is_featured", sa.Boolean),
            sa.column("usage_count", sa.Integer),
            sa.column("created_by", sa.String),
            sa.column("charts_config", sa.JSON),
            sa.column("column_mappings", sa.JSON),
            sa.column("created_at", sa.DateTime),
        ),
        [
            {"id": "tmpl-ecom-1", "name": "E-commerce Sales Overview", "description": "Revenue, orders, AOV, and top products at a glance.", "industry": "e-commerce", "tags": ["sales", "revenue", "orders"], "is_featured": True, "usage_count": 0, "created_by": "DataMind", "charts_config": [{"type": "line", "x": "__date__", "y": "__revenue__", "title": "Revenue Over Time"}, {"type": "bar", "x": "__product__", "y": "__sales__", "title": "Top Products by Sales"}], "column_mappings": {"__date__": "Date / order date column", "__revenue__": "Revenue / sales amount column", "__product__": "Product name column", "__sales__": "Sales quantity or amount column"}, "created_at": None},
            {"id": "tmpl-ecom-2", "name": "Customer Cohort Analysis", "description": "Retention and LTV by customer acquisition cohort.", "industry": "e-commerce", "tags": ["retention", "cohort", "ltv"], "is_featured": False, "usage_count": 0, "created_by": "DataMind", "charts_config": [{"type": "bar", "x": "__cohort__", "y": "__retention__", "title": "Cohort Retention Rate"}, {"type": "line", "x": "__date__", "y": "__ltv__", "title": "Customer LTV Over Time"}], "column_mappings": {"__cohort__": "Cohort / signup month column", "__retention__": "Retention rate column", "__date__": "Date column", "__ltv__": "Lifetime value column"}, "created_at": None},
            {"id": "tmpl-saas-1", "name": "SaaS MRR Dashboard", "description": "Monthly recurring revenue, churn, and expansion tracking.", "industry": "saas", "tags": ["mrr", "churn", "arr"], "is_featured": True, "usage_count": 0, "created_by": "DataMind", "charts_config": [{"type": "line", "x": "__month__", "y": "__mrr__", "title": "MRR Trend"}, {"type": "bar", "x": "__month__", "y": "__churn_rate__", "title": "Monthly Churn Rate"}], "column_mappings": {"__month__": "Month / period column", "__mrr__": "MRR / monthly revenue column", "__churn_rate__": "Churn rate column"}, "created_at": None},
            {"id": "tmpl-saas-2", "name": "Churn Analysis", "description": "Identify at-risk customers and churn drivers.", "industry": "saas", "tags": ["churn", "retention", "risk"], "is_featured": False, "usage_count": 0, "created_by": "DataMind", "charts_config": [{"type": "bar", "x": "__reason__", "y": "__count__", "title": "Churn Reasons"}, {"type": "line", "x": "__date__", "y": "__active_users__", "title": "Active Users Over Time"}], "column_mappings": {"__reason__": "Churn reason column", "__count__": "Count column", "__date__": "Date column", "__active_users__": "Active users column"}, "created_at": None},
            {"id": "tmpl-fin-1", "name": "P&L Summary", "description": "Profit and loss across revenue, COGS, and expenses.", "industry": "finance", "tags": ["pnl", "revenue", "expenses"], "is_featured": True, "usage_count": 0, "created_by": "DataMind", "charts_config": [{"type": "bar", "x": "__period__", "y": "__revenue__", "title": "Revenue vs Expenses"}, {"type": "line", "x": "__period__", "y": "__profit__", "title": "Net Profit Trend"}], "column_mappings": {"__period__": "Period / quarter column", "__revenue__": "Revenue column", "__profit__": "Net profit column"}, "created_at": None},
            {"id": "tmpl-fin-2", "name": "Cash Flow Dashboard", "description": "Operating, investing, and financing cash flow overview.", "industry": "finance", "tags": ["cashflow", "liquidity"], "is_featured": False, "usage_count": 0, "created_by": "DataMind", "charts_config": [{"type": "bar", "x": "__month__", "y": "__cash_in__", "title": "Cash Inflows"}, {"type": "bar", "x": "__month__", "y": "__cash_out__", "title": "Cash Outflows"}], "column_mappings": {"__month__": "Month column", "__cash_in__": "Cash inflow column", "__cash_out__": "Cash outflow column"}, "created_at": None},
            {"id": "tmpl-mkt-1", "name": "Campaign Performance", "description": "CTR, conversions, CPA, and ROAS across marketing campaigns.", "industry": "marketing", "tags": ["campaigns", "ctr", "roas"], "is_featured": True, "usage_count": 0, "created_by": "DataMind", "charts_config": [{"type": "bar", "x": "__campaign__", "y": "__conversions__", "title": "Conversions by Campaign"}, {"type": "scatter", "x": "__spend__", "y": "__revenue__", "title": "Spend vs Revenue"}], "column_mappings": {"__campaign__": "Campaign name column", "__conversions__": "Conversions column", "__spend__": "Ad spend column", "__revenue__": "Revenue generated column"}, "created_at": None},
            {"id": "tmpl-mkt-2", "name": "Funnel Analysis", "description": "Conversion funnel from awareness to purchase.", "industry": "marketing", "tags": ["funnel", "conversion", "leads"], "is_featured": False, "usage_count": 0, "created_by": "DataMind", "charts_config": [{"type": "bar", "x": "__stage__", "y": "__count__", "title": "Funnel Stages"}], "column_mappings": {"__stage__": "Funnel stage column", "__count__": "Count / users column"}, "created_at": None},
            {"id": "tmpl-hr-1", "name": "Headcount Dashboard", "description": "Headcount trends, department breakdown, and hiring pipeline.", "industry": "hr", "tags": ["headcount", "hiring", "departments"], "is_featured": True, "usage_count": 0, "created_by": "DataMind", "charts_config": [{"type": "bar", "x": "__department__", "y": "__headcount__", "title": "Headcount by Department"}, {"type": "line", "x": "__month__", "y": "__total_headcount__", "title": "Total Headcount Over Time"}], "column_mappings": {"__department__": "Department column", "__headcount__": "Headcount column", "__month__": "Month column", "__total_headcount__": "Total headcount column"}, "created_at": None},
            {"id": "tmpl-hr-2", "name": "Attrition Analysis", "description": "Employee attrition rate, tenure, and exit reasons.", "industry": "hr", "tags": ["attrition", "retention", "turnover"], "is_featured": False, "usage_count": 0, "created_by": "DataMind", "charts_config": [{"type": "bar", "x": "__reason__", "y": "__count__", "title": "Exit Reasons"}, {"type": "line", "x": "__month__", "y": "__attrition_rate__", "title": "Monthly Attrition Rate"}], "column_mappings": {"__reason__": "Exit reason column", "__count__": "Count column", "__month__": "Month column", "__attrition_rate__": "Attrition rate column"}, "created_at": None},
        ],
    )

    # ── Catalog entries (Phase 8) ─────────────────────────────────
    op.create_table(
        "catalog_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), sa.ForeignKey("workspaces.id"), nullable=True),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_certified", sa.Boolean(), default=False),
        sa.Column("steward_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("sensitivity", sa.String(), default="internal"),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column("usage_count", sa.Integer(), default=0),
        sa.Column("last_accessed", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("catalog_entries")
    op.drop_table("dashboard_templates")
    op.drop_table("dashboard_versions")
    op.drop_table("dashboard_comments")
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        for col in ["notify_slack", "slack_webhook_url", "notify_teams", "teams_webhook_url",
                    "notify_telegram", "telegram_bot_token", "telegram_chat_id"]:
            batch_op.drop_column(col)
    op.drop_table("automl_predictions")
    op.drop_table("automl_jobs")
    op.drop_table("rca_results")
    op.drop_table("llm_usage_logs")
