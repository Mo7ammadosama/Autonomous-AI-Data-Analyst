"""phase9_17_world_class_features

Revision ID: 009_phase9_17
Revises: 006_phase6
Create Date: 2026-03-18 00:00:00.000000

Adds tables for Phase 9-17 world-class features:
  - proactive_insights     (Phase 9: Proactive Intelligence)
  - proactive_configs      (Phase 9: Proactive Monitor Config)
  - metric_definitions     (Phase 10: Governed Semantic Metric Catalog)
  - scenario_results       (Phase 12: What-If Scenarios)
  - data_streams           (Phase 13: Real-Time Streaming)
  - digest_configs         (Phase 14: Personalized Digest)
  - dashboard_prs          (Phase 17: PR Review Workflow)
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "009_phase9_17"
down_revision: Union[str, Sequence[str], None] = "006_phase6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    ctx = op.get_context()
    with_batch = is_sqlite

    # ── proactive_insights ─────────────────────────────────────
    op.create_table(
        "proactive_insights",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("dataset_id", sa.String, sa.ForeignKey("datasets.id"), nullable=True),
        sa.Column("metric_name", sa.String, nullable=True),
        sa.Column("insight_type", sa.String, nullable=False),
        sa.Column("change_pct", sa.Float, nullable=True),
        sa.Column("current_value", sa.Float, nullable=True),
        sa.Column("previous_value", sa.Float, nullable=True),
        sa.Column("drivers", sa.JSON, nullable=True),
        sa.Column("narrative", sa.Text, nullable=True),
        sa.Column("chart", sa.JSON, nullable=True),
        sa.Column("severity", sa.String, default="info"),
        sa.Column("is_read", sa.Boolean, default=False),
        sa.Column("sent_via", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_proactive_insights_user_id", "proactive_insights", ["user_id"])
    op.create_index("ix_proactive_insights_created_at", "proactive_insights", ["created_at"])

    # ── proactive_configs ──────────────────────────────────────
    op.create_table(
        "proactive_configs",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("is_enabled", sa.Boolean, default=True),
        sa.Column("scan_frequency_minutes", sa.Integer, default=60),
        sa.Column("notify_websocket", sa.Boolean, default=True),
        sa.Column("notify_email", sa.Boolean, default=False),
        sa.Column("notify_slack", sa.Boolean, default=False),
        sa.Column("slack_webhook_url", sa.String, nullable=True),
        sa.Column("monitored_datasets", sa.JSON, nullable=True),
        sa.Column("anomaly_sensitivity", sa.String, default="medium"),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    # ── metric_definitions ─────────────────────────────────────
    op.create_table(
        "metric_definitions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("workspace_id", sa.String, sa.ForeignKey("workspaces.id"), nullable=True),
        sa.Column("owner_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("display_name", sa.String, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String, nullable=True),
        sa.Column("sql_expression", sa.Text, nullable=True),
        sa.Column("dataset_id", sa.String, sa.ForeignKey("datasets.id"), nullable=True),
        sa.Column("source_columns", sa.JSON, nullable=True),
        sa.Column("approved_dimensions", sa.JSON, nullable=True),
        sa.Column("unit", sa.String, nullable=True),
        sa.Column("direction", sa.String, default="higher_is_better"),
        sa.Column("is_certified", sa.Boolean, default=False),
        sa.Column("certified_by", sa.String, nullable=True),
        sa.Column("certified_at", sa.DateTime, nullable=True),
        sa.Column("lineage", sa.JSON, nullable=True),
        sa.Column("tags", sa.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_metric_definitions_name", "metric_definitions", ["name"])
    op.create_index("ix_metric_definitions_workspace_id", "metric_definitions", ["workspace_id"])

    # ── scenario_results ───────────────────────────────────────
    op.create_table(
        "scenario_results",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("automl_job_id", sa.String, sa.ForeignKey("automl_jobs.id"), nullable=False),
        sa.Column("name", sa.String, nullable=True),
        sa.Column("input_assumptions", sa.JSON, nullable=True),
        sa.Column("baseline_prediction", sa.Float, nullable=True),
        sa.Column("scenario_prediction", sa.Float, nullable=True),
        sa.Column("delta", sa.Float, nullable=True),
        sa.Column("delta_pct", sa.Float, nullable=True),
        sa.Column("feature_impacts", sa.JSON, nullable=True),
        sa.Column("chart", sa.JSON, nullable=True),
        sa.Column("is_shared", sa.Boolean, default=False),
        sa.Column("share_token", sa.String, nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_scenario_results_user_id", "scenario_results", ["user_id"])

    # ── data_streams ───────────────────────────────────────────
    op.create_table(
        "data_streams",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source_type", sa.String, nullable=False),
        sa.Column("source_id", sa.String, nullable=True),
        sa.Column("query", sa.Text, nullable=True),
        sa.Column("refresh_interval_seconds", sa.Integer, default=30),
        sa.Column("transformations", sa.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("subscriber_count", sa.Integer, default=0),
        sa.Column("last_pushed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_data_streams_user_id", "data_streams", ["user_id"])

    # ── digest_configs ─────────────────────────────────────────
    op.create_table(
        "digest_configs",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("is_enabled", sa.Boolean, default=False),
        sa.Column("frequency", sa.String, default="weekly"),
        sa.Column("send_hour", sa.Integer, default=8),
        sa.Column("send_day", sa.String, default="monday"),
        sa.Column("include_anomalies", sa.Boolean, default=True),
        sa.Column("include_top_changes", sa.Boolean, default=True),
        sa.Column("include_suggestions", sa.Boolean, default=True),
        sa.Column("include_data_quality", sa.Boolean, default=True),
        sa.Column("monitored_datasets", sa.JSON, nullable=True),
        sa.Column("monitored_metrics", sa.JSON, nullable=True),
        sa.Column("delivery_email", sa.String, nullable=True),
        sa.Column("delivery_slack", sa.Boolean, default=False),
        sa.Column("slack_webhook_url", sa.String, nullable=True),
        sa.Column("last_sent_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    # ── dashboard_prs ──────────────────────────────────────────
    op.create_table(
        "dashboard_prs",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("dashboard_id", sa.String, sa.ForeignKey("dashboards.id"), nullable=False),
        sa.Column("proposed_by", sa.String, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("proposed_layout", sa.JSON, nullable=True),
        sa.Column("proposed_charts", sa.JSON, nullable=True),
        sa.Column("diff_summary", sa.JSON, nullable=True),
        sa.Column("status", sa.String, default="pending"),
        sa.Column("reviewed_by", sa.String, nullable=True),
        sa.Column("review_comment", sa.Text, nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("source_session_id", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_dashboard_prs_dashboard_id", "dashboard_prs", ["dashboard_id"])


def downgrade() -> None:
    op.drop_index("ix_dashboard_prs_dashboard_id", "dashboard_prs")
    op.drop_table("dashboard_prs")
    op.drop_table("digest_configs")
    op.drop_index("ix_data_streams_user_id", "data_streams")
    op.drop_table("data_streams")
    op.drop_index("ix_scenario_results_user_id", "scenario_results")
    op.drop_table("scenario_results")
    op.drop_index("ix_metric_definitions_workspace_id", "metric_definitions")
    op.drop_index("ix_metric_definitions_name", "metric_definitions")
    op.drop_table("metric_definitions")
    op.drop_table("proactive_configs")
    op.drop_index("ix_proactive_insights_created_at", "proactive_insights")
    op.drop_index("ix_proactive_insights_user_id", "proactive_insights")
    op.drop_table("proactive_insights")
