"""
Database models and initialization
"""

from sqlalchemy import (
    create_engine, Column, String, Integer, Float, DateTime,
    Text, Boolean, ForeignKey, JSON, BigInteger, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid
import os
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ai_analyst.db")

# PostgreSQL requires different connect_args than SQLite
_is_sqlite = "sqlite" in DATABASE_URL
_is_postgres = not _is_sqlite
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,          # Reconnect on stale connections
    pool_recycle=3600,           # Recycle connections every hour
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# pgvector: only available when connected to PostgreSQL
_pgvector_available = False
try:
    from pgvector.sqlalchemy import Vector
    _pgvector_available = True
except ImportError:
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # Enable pgvector extension before table creation (PostgreSQL only)
    if _is_postgres and _pgvector_available:
        try:
            with engine.connect() as conn:
                conn.execute(__import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
            logger.info("pgvector extension enabled")
        except Exception as e:
            logger.warning(f"pgvector extension setup: {e}")
    Base.metadata.create_all(bind=engine)


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="analyst")
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    datasets = relationship("Dataset", back_populates="owner")


class Workspace(Base):
    __tablename__ = "workspaces"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    plan = Column(String, default="free")
    is_suspended = Column(Boolean, default=False)
    suspended_reason = Column(Text, nullable=True)
    suspended_at = Column(DateTime, nullable=True)


class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)
    file_type = Column(String, nullable=True)
    row_count = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    columns_meta = Column(JSON, nullable=True)
    status = Column(String, default="processing")
    owner_id = Column(String, ForeignKey("users.id"))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    description = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    owner = relationship("User", back_populates="datasets")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dataset_id = Column(String, ForeignKey("datasets.id"))
    analysis_type = Column(String, nullable=False)
    result_data = Column(JSON, nullable=True)
    charts = Column(JSON, nullable=True)
    insights = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    execution_time = Column(Float, nullable=True)


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=True)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=True)
    user_id = Column(String, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    messages = relationship("ChatMessage", back_populates="session")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("chat_sessions.id"))
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    charts = Column(JSON, nullable=True)
    code = Column(Text, nullable=True)
    insights = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    session = relationship("ChatSession", back_populates="messages")


class Dashboard(Base):
    __tablename__ = "dashboards"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    layout = Column(JSON, nullable=True)
    charts = Column(JSON, nullable=True)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=True)
    user_id = Column(String, ForeignKey("users.id"))
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Insight(Base):
    __tablename__ = "insights"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dataset_id = Column(String, ForeignKey("datasets.id"))
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    insight_type = Column(String, default="general")
    severity = Column(String, default="info")
    metric_value = Column(String, nullable=True)
    metric_change = Column(Float, nullable=True)
    chart = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    action = Column(String, nullable=False)
    resource_type = Column(String, nullable=True)
    resource_id = Column(String, nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PipelineResult(Base):
    """Auto-analysis pipeline result, generated on dataset upload."""
    __tablename__ = "pipeline_results"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dataset_id = Column(String, ForeignKey("datasets.id"), unique=True)
    # Structured sections of the pipeline output
    profile = Column(JSON, nullable=True)          # data quality report
    eda = Column(JSON, nullable=True)              # exploratory data analysis
    insights = Column(JSON, nullable=True)         # key auto-insights
    recommendations = Column(JSON, nullable=True)  # business recommendations
    story = Column(Text, nullable=True)            # narrative text
    anomalies = Column(JSON, nullable=True)        # detected anomalies
    charts = Column(JSON, nullable=True)           # auto-generated charts
    status = Column(String, default="pending")     # pending | running | done | error
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ForecastResult(Base):
    """Time-series forecast result per dataset + target column."""
    __tablename__ = "forecast_results"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dataset_id = Column(String, ForeignKey("datasets.id"))
    date_column = Column(String, nullable=False)
    target_column = Column(String, nullable=False)
    periods = Column(Integer, default=30)
    method = Column(String, default="auto")        # arima | linear | exp_smoothing
    forecast_data = Column(JSON, nullable=True)    # predicted values + confidence
    metrics = Column(JSON, nullable=True)          # MAE, RMSE, etc.
    chart = Column(JSON, nullable=True)            # Plotly chart spec
    created_at = Column(DateTime, default=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════
#  Phase 1 New Models
# ═══════════════════════════════════════════════════════════════

class Alert(Base):
    """User-defined data alerts — triggered when threshold conditions are met."""
    __tablename__ = "alerts"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # Condition definition
    column_name = Column(String, nullable=True)           # e.g. "revenue"
    condition = Column(String, nullable=False)            # gt | lt | eq | gte | lte | anomaly
    threshold = Column(Float, nullable=True)              # e.g. 10000.0
    aggregation = Column(String, default="mean")          # mean | sum | max | min | count

    # Notification settings — Email
    notify_email = Column(Boolean, default=True)
    email_recipient = Column(String, nullable=True)
    # Notification settings — Slack
    notify_slack = Column(Boolean, default=False)
    slack_webhook_url = Column(String, nullable=True)
    # Notification settings — Microsoft Teams
    notify_teams = Column(Boolean, default=False)
    teams_webhook_url = Column(String, nullable=True)
    # Notification settings — Telegram
    notify_telegram = Column(Boolean, default=False)
    telegram_bot_token = Column(String, nullable=True)
    telegram_chat_id = Column(String, nullable=True)

    is_active = Column(Boolean, default=True)

    # State
    last_checked = Column(DateTime, nullable=True)
    last_triggered = Column(DateTime, nullable=True)
    trigger_count = Column(Integer, default=0)
    status = Column(String, default="active")             # active | paused | fired

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    logs = relationship("AlertLog", back_populates="alert", cascade="all, delete-orphan")


class AlertLog(Base):
    """Immutable log of every alert trigger event."""
    __tablename__ = "alert_logs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_id = Column(String, ForeignKey("alerts.id"), nullable=False)
    triggered_at = Column(DateTime, default=datetime.utcnow)
    actual_value = Column(Float, nullable=True)
    message = Column(Text, nullable=True)
    notified = Column(Boolean, default=False)

    alert = relationship("Alert", back_populates="logs")


class ScheduledReport(Base):
    """Automated report delivery schedule."""
    __tablename__ = "scheduled_reports"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    title = Column(String, nullable=False)
    frequency = Column(String, default="weekly")    # daily | weekly | monthly
    email_recipient = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    last_sent = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DataConnection(Base):
    """External database / API connections (data sources beyond file upload)."""
    __tablename__ = "data_connections"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True)
    name = Column(String, nullable=False)
    connection_type = Column(String, nullable=False)    # postgresql | mysql | bigquery | snowflake | api
    host = Column(String, nullable=True)
    port = Column(Integer, nullable=True)
    database = Column(String, nullable=True)
    username = Column(String, nullable=True)
    # Encrypted credentials stored separately — password_hash or secret reference
    credentials_ref = Column(String, nullable=True)
    extra_config = Column(JSON, nullable=True)           # SSL certs, schema, etc.
    is_active = Column(Boolean, default=True)
    last_synced = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class NL2SQLQuery(Base):
    """Audit log of all Natural Language → SQL query translations."""
    __tablename__ = "nl2sql_queries"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    question = Column(Text, nullable=False)
    generated_sql = Column(Text, nullable=True)
    result_data = Column(JSON, nullable=True)           # Query result rows
    charts = Column(JSON, nullable=True)                # Auto-generated charts
    execution_time_ms = Column(Integer, nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    feedback = Column(Integer, nullable=True)            # 1 = thumbs up, -1 = thumbs down
    created_at = Column(DateTime, default=datetime.utcnow)


class VectorIndex(Base):
    """Tracks FAISS/embedding vector index state per dataset for RAG."""
    __tablename__ = "vector_indexes"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dataset_id = Column(String, ForeignKey("datasets.id"), unique=True, nullable=False)
    index_path = Column(String, nullable=True)
    chunk_count = Column(Integer, default=0)
    embedding_model = Column(String, default="all-MiniLM-L6-v2")
    status = Column(String, default="pending")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════
#  Phase 3-5 New Models
# ═══════════════════════════════════════════════════════════════

class ApiKey(Base):
    """Programmatic API keys — alternative to JWT for machine-to-machine access."""
    __tablename__ = "api_keys"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)                    # e.g. "CI Pipeline Key"
    key_hash = Column(String, nullable=False, unique=True)   # sha256 of the raw key
    key_prefix = Column(String, nullable=False)              # first 8 chars shown to user
    scopes = Column(JSON, default=list)                      # ["read", "write", "admin"]
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkspaceMember(Base):
    """Maps users to workspaces with roles."""
    __tablename__ = "workspace_members"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    role = Column(String, default="member")     # owner | admin | member | viewer
    invited_by = Column(String, ForeignKey("users.id"), nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow)


class WorkspaceInvite(Base):
    """Pending workspace invitations by email."""
    __tablename__ = "workspace_invites"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    invited_by = Column(String, ForeignKey("users.id"), nullable=False)
    email = Column(String, nullable=False)
    role = Column(String, default="member")
    token = Column(String, unique=True, nullable=False)      # accept URL token
    accepted = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Webhook(Base):
    """Webhook delivery endpoints for alert events."""
    __tablename__ = "webhooks"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    secret = Column(String, nullable=True)                   # HMAC-SHA256 signing secret
    events = Column(JSON, default=list)                      # ["alert.triggered", "report.sent"]
    is_active = Column(Boolean, default=True)
    last_triggered_at = Column(DateTime, nullable=True)
    failure_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class SharedDashboard(Base):
    """Public share tokens for dashboard read-only access."""
    __tablename__ = "shared_dashboards"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dashboard_id = Column(String, ForeignKey("dashboards.id"), nullable=False)
    token = Column(String, unique=True, nullable=False)      # URL-safe random token
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=True)
    view_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Notification(Base):
    """In-app notifications for users."""
    __tablename__ = "notifications"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)           # alert_triggered | upload_done | insight_ready | report_sent
    title = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    link = Column(String, nullable=True)            # e.g. /alerts/uuid or /datasets/uuid
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── pgvector: semantic chunk storage ─────────────────────────────
# Only creates the vector column when pgvector is available (PostgreSQL).
# Falls back gracefully — rag_service uses numpy files on SQLite.

def _make_dataset_chunk_class():
    """Factory so the Vector column is only added when pgvector is importable."""
    attrs = {
        "__tablename__": "dataset_chunks",
        "id": Column(String, primary_key=True, default=lambda: str(uuid.uuid4())),
        "dataset_id": Column(String, ForeignKey("datasets.id"), nullable=False, index=True),
        "chunk_index": Column(Integer, nullable=False),
        "chunk_type": Column(String, nullable=True),          # overview | column_summary | rows
        "chunk_text": Column(Text, nullable=False),
        "metadata_": Column("metadata", JSON, nullable=True),
        "created_at": Column(DateTime, default=datetime.utcnow),
    }
    if _pgvector_available:
        # 384-dim = all-MiniLM-L6-v2 output size
        attrs["embedding"] = Column(Vector(384), nullable=True)
    return type("DatasetChunk", (Base,), attrs)


DatasetChunk = _make_dataset_chunk_class()


class RefreshToken(Base):
    """
    Issued refresh tokens — stored for revocation support.
    On logout or password change, mark is_revoked=True.
    """
    __tablename__ = "refresh_tokens"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    jti = Column(String, unique=True, nullable=False, index=True)  # JWT ID claim
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════
#  Phase 6 Models — AI Supremacy
# ═══════════════════════════════════════════════════════════════

class LLMUsageLog(Base):
    """Per-request LLM usage for cost tracking and analytics."""
    __tablename__ = "llm_usage_logs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    model = Column(String, nullable=False)           # e.g. "GPT-4o"
    provider = Column(String, nullable=False)        # openai | anthropic | google | ollama
    task_type = Column(String, nullable=True)        # sql | narrative | rag | default …
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    latency_ms = Column(Integer, default=0)
    success = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class RCAResult(Base):
    """Root Cause Analysis results — explains why a metric changed."""
    __tablename__ = "rca_results"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    metric_column = Column(String, nullable=False)
    date_column = Column(String, nullable=True)
    comparison_period = Column(String, default="month")   # week | month | quarter
    change_pct = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    result_data = Column(JSON, nullable=True)             # top_drivers, segments
    narrative = Column(Text, nullable=True)               # LLM-generated explanation
    chart = Column(JSON, nullable=True)                   # waterfall Plotly chart
    status = Column(String, default="pending")            # pending | running | done | error
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AutoMLJob(Base):
    """No-code AutoML training job — trains classification/regression/clustering models."""
    __tablename__ = "automl_jobs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    target_column = Column(String, nullable=False)
    task_type = Column(String, nullable=False)            # classification | regression | clustering
    status = Column(String, default="queued")             # queued | training | done | error
    best_model = Column(String, nullable=True)            # e.g. "GradientBoosting"
    cv_score = Column(Float, nullable=True)               # cross-validation score
    feature_importance = Column(JSON, nullable=True)      # {feature: importance}
    confusion_matrix = Column(JSON, nullable=True)        # for classification
    metrics = Column(JSON, nullable=True)                 # MAE/RMSE for regression
    result_data = Column(JSON, nullable=True)             # sample predictions
    model_path = Column(String, nullable=True)            # local path to .pkl file
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    predictions = relationship("AutoMLPrediction", back_populates="job", cascade="all, delete-orphan")


class AutoMLPrediction(Base):
    """Inference results from a trained AutoML model."""
    __tablename__ = "automl_predictions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("automl_jobs.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    input_data = Column(JSON, nullable=True)
    predictions = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("AutoMLJob", back_populates="predictions")


# ═══════════════════════════════════════════════════════════════
#  Phase 7 Models — Real-time & Integrations
# ═══════════════════════════════════════════════════════════════
# (Alert model extended with nullable notification channel columns
#  via Alembic migration 007 — no structural changes here needed)


# ═══════════════════════════════════════════════════════════════
#  Phase 8 Models — Collaboration & Polish
# ═══════════════════════════════════════════════════════════════

class DashboardComment(Base):
    """Threaded comments pinned to a dashboard or specific chart."""
    __tablename__ = "dashboard_comments"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dashboard_id = Column(String, ForeignKey("dashboards.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    parent_id = Column(String, ForeignKey("dashboard_comments.id"), nullable=True)  # threaded replies
    content = Column(Text, nullable=False)
    chart_index = Column(Integer, nullable=True)       # which chart is being annotated
    position_x = Column(Float, nullable=True)          # canvas pin position
    position_y = Column(Float, nullable=True)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    replies = relationship("DashboardComment", backref=__import__("sqlalchemy.orm", fromlist=["backref"]).backref("parent", remote_side="DashboardComment.id"))


class DashboardVersion(Base):
    """Snapshot of a dashboard state — created on every PUT update."""
    __tablename__ = "dashboard_versions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dashboard_id = Column(String, ForeignKey("dashboards.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    layout = Column(JSON, nullable=True)
    charts = Column(JSON, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    change_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DashboardTemplate(Base):
    """Pre-built dashboard templates — instantiated by users via column mapping."""
    __tablename__ = "dashboard_templates"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    industry = Column(String, nullable=True)             # e-commerce | saas | finance | marketing | hr
    tags = Column(JSON, default=list)
    thumbnail_url = Column(String, nullable=True)
    layout = Column(JSON, nullable=True)
    charts_config = Column(JSON, nullable=True)          # chart defs with placeholder column names
    column_mappings = Column(JSON, nullable=True)        # {placeholder: human description}
    is_featured = Column(Boolean, default=False)
    usage_count = Column(Integer, default=0)
    created_by = Column(String, nullable=True)           # "DataMind" for built-ins
    created_at = Column(DateTime, default=datetime.utcnow)


class CatalogEntry(Base):
    """Searchable data catalog — indexes datasets, metrics, and columns."""
    __tablename__ = "catalog_entries"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True, index=True)
    resource_type = Column(String, nullable=False)       # dataset | metric | column
    resource_id = Column(String, nullable=False)         # FK to the actual resource
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True)
    is_certified = Column(Boolean, default=False)        # admin-certified quality badge
    steward_id = Column(String, ForeignKey("users.id"), nullable=True)
    sensitivity = Column(String, default="internal")     # public | internal | confidential | restricted
    lineage = Column(JSON, nullable=True)                # {source_connection: id, transformation: "..."}
    usage_count = Column(Integer, default=0)
    last_accessed = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════
#  Phase 9 Models — Proactive Intelligence Engine
# ═══════════════════════════════════════════════════════════════

class ProactiveInsight(Base):
    """Auto-generated insight pushed to users without them asking — Tableau Pulse style."""
    __tablename__ = "proactive_insights"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=True)
    metric_name = Column(String, nullable=True)          # column or KPI name monitored
    insight_type = Column(String, nullable=False)        # anomaly | trend_shift | record_high | record_low | data_quality
    change_pct = Column(Float, nullable=True)            # % change detected
    current_value = Column(Float, nullable=True)
    previous_value = Column(Float, nullable=True)
    drivers = Column(JSON, nullable=True)                # top contributing segments / dimensions
    narrative = Column(Text, nullable=True)              # LLM-generated plain-English explanation
    chart = Column(JSON, nullable=True)                  # optional Plotly chart
    severity = Column(String, default="info")            # info | warning | critical
    is_read = Column(Boolean, default=False)
    sent_via = Column(JSON, default=list)                # ["websocket", "email", "slack"]
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ProactiveConfig(Base):
    """Per-user configuration for the proactive monitoring engine."""
    __tablename__ = "proactive_configs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    is_enabled = Column(Boolean, default=True)
    scan_frequency_minutes = Column(Integer, default=60)   # how often to scan (min 15)
    notify_websocket = Column(Boolean, default=True)
    notify_email = Column(Boolean, default=False)
    notify_slack = Column(Boolean, default=False)
    slack_webhook_url = Column(String, nullable=True)
    monitored_datasets = Column(JSON, default=list)        # [] = all datasets
    anomaly_sensitivity = Column(String, default="medium") # low | medium | high
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════
#  Phase 10 Models — Governed Semantic Metric Catalog
# ═══════════════════════════════════════════════════════════════

class MetricDefinition(Base):
    """Central definition of a business KPI / metric — ThoughtSpot / Looker style."""
    __tablename__ = "metric_definitions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True, index=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False, index=True)        # e.g. "Monthly Recurring Revenue"
    display_name = Column(String, nullable=True)             # shorter label for charts
    description = Column(Text, nullable=True)
    category = Column(String, nullable=True)                 # revenue | growth | quality | engagement
    sql_expression = Column(Text, nullable=True)             # e.g. "SUM(amount) WHERE status='paid'"
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=True)
    source_columns = Column(JSON, default=list)              # columns used in expression
    approved_dimensions = Column(JSON, default=list)         # allowed breakdown dimensions
    unit = Column(String, nullable=True)                     # "$", "%", "users", etc.
    direction = Column(String, default="higher_is_better")   # higher_is_better | lower_is_better
    is_certified = Column(Boolean, default=False)
    certified_by = Column(String, ForeignKey("users.id"), nullable=True)
    certified_at = Column(DateTime, nullable=True)
    lineage = Column(JSON, nullable=True)                    # {source, transformations}
    tags = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════
#  Phase 12 Models — What-If Scenario Analysis
# ═══════════════════════════════════════════════════════════════

class ScenarioResult(Base):
    """Saved what-if scenario simulation — Qlik AutoML What-If style."""
    __tablename__ = "scenario_results"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    automl_job_id = Column(String, ForeignKey("automl_jobs.id"), nullable=False)
    name = Column(String, nullable=True)                     # user-given scenario name
    input_assumptions = Column(JSON, nullable=True)          # {feature: value} overrides
    baseline_prediction = Column(Float, nullable=True)
    scenario_prediction = Column(Float, nullable=True)
    delta = Column(Float, nullable=True)                     # scenario - baseline
    delta_pct = Column(Float, nullable=True)
    feature_impacts = Column(JSON, nullable=True)            # how each changed feature contributes
    chart = Column(JSON, nullable=True)                      # comparison Plotly chart
    is_shared = Column(Boolean, default=False)
    share_token = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════
#  Phase 13 Models — Real-Time Streaming
# ═══════════════════════════════════════════════════════════════

class DataStream(Base):
    """Configured real-time data stream for live dashboard widgets — Grafana style."""
    __tablename__ = "data_streams"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    source_type = Column(String, nullable=False)             # dataset | connection | api
    source_id = Column(String, nullable=True)                # dataset_id or connection_id
    query = Column(Text, nullable=True)                      # SQL or JSON path to stream
    refresh_interval_seconds = Column(Integer, default=30)   # 1 | 5 | 30 | 60
    transformations = Column(JSON, nullable=True)            # filter/aggregate steps
    is_active = Column(Boolean, default=True)
    subscriber_count = Column(Integer, default=0)
    last_pushed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════
#  Phase 14 Models — Personalized AI Digest
# ═══════════════════════════════════════════════════════════════

class DigestConfig(Base):
    """Per-user digest delivery preferences — Tableau Pulse / Domo style."""
    __tablename__ = "digest_configs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    is_enabled = Column(Boolean, default=False)
    frequency = Column(String, default="weekly")             # daily | weekly
    send_hour = Column(Integer, default=8)                   # hour of day (UTC) to send
    send_day = Column(String, default="monday")              # for weekly: day name
    include_anomalies = Column(Boolean, default=True)
    include_top_changes = Column(Boolean, default=True)
    include_suggestions = Column(Boolean, default=True)
    include_data_quality = Column(Boolean, default=True)
    monitored_datasets = Column(JSON, default=list)          # [] = all
    monitored_metrics = Column(JSON, default=list)           # [] = all
    delivery_email = Column(String, nullable=True)
    delivery_slack = Column(Boolean, default=False)
    slack_webhook_url = Column(String, nullable=True)
    last_sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════
#  Phase 17 Models — PR Review Workflow
# ═══════════════════════════════════════════════════════════════

class DashboardPR(Base):
    """Proposed dashboard change awaiting review — Hex diff view style."""
    __tablename__ = "dashboard_prs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dashboard_id = Column(String, ForeignKey("dashboards.id"), nullable=False, index=True)
    proposed_by = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    proposed_layout = Column(JSON, nullable=True)            # new layout
    proposed_charts = Column(JSON, nullable=True)            # new charts
    diff_summary = Column(JSON, nullable=True)               # human-readable diff
    status = Column(String, default="pending")               # pending | approved | rejected
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True)
    review_comment = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    source_session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=True)  # if from chat
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════
#  Autonomous Agent Models
# ═══════════════════════════════════════════════════════════════

class AgentRun(Base):
    """Autonomous ReAct agent run — tracks every step and token usage."""
    __tablename__ = "agent_runs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    task = Column(Text, nullable=False)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=True)
    connection_id = Column(String, nullable=True)
    domain = Column(String, nullable=True)                   # finance | retail | healthcare | …
    status = Column(String, default="running")               # running | completed | failed
    steps = Column(JSON, default=list)                       # list of {thought, action, observation}
    result_summary = Column(Text, nullable=True)
    charts = Column(JSON, default=list)                      # list of base64 PNGs with titles
    token_usage = Column(Integer, default=0)
    duration_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CustomReport(Base):
    """User-designed report assembled from typed sections — drag-and-drop support."""
    __tablename__ = "custom_reports"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    domain = Column(String, nullable=True)
    template_name = Column(String, nullable=True)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=True)
    connection_id = Column(String, nullable=True)
    sections = Column(JSON, default=list)                    # ordered list of section dicts
    generated_content = Column(JSON, default=dict)           # section_id -> content
    status = Column(String, default="draft")                 # draft | generating | ready | failed
    pdf_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════
#  Agent Memory — persistent per-user learning
# ═══════════════════════════════════════════════════════════════

class AgentMemory(Base):
    """Persistent per-user memory for the autonomous agent."""
    __tablename__ = "agent_memories"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    memory_type = Column(String, nullable=False)   # preference | domain_knowledge | past_analysis | correction
    key = Column(String, nullable=False)
    value = Column(Text, nullable=False)
    source_run_id = Column(String, nullable=True)  # which agent run produced this memory
    importance = Column(Float, default=1.0)
    access_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════
#  Notebooks — collaborative analysis notebooks (Julius-style)
# ═══════════════════════════════════════════════════════════════

class Notebook(Base):
    """Analysis notebook — contains ordered cells of different types."""
    __tablename__ = "notebooks"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False, default="Untitled Notebook")
    description = Column(Text, nullable=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=True)
    template_id = Column(String, nullable=True)
    template_name = Column(String, nullable=True)
    domain = Column(String, nullable=True)
    tags = Column(JSON, default=list)
    is_template = Column(Boolean, default=False)
    run_count = Column(Integer, default=0)
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    cells = relationship("NotebookCell", back_populates="notebook", cascade="all, delete-orphan", order_by="NotebookCell.position")


class NotebookCell(Base):
    """Single cell in a notebook."""
    __tablename__ = "notebook_cells"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    notebook_id = Column(String, ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True)
    cell_type = Column(String, nullable=False)
    position = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=True)
    output = Column(Text, nullable=True)
    output_type = Column(String, nullable=True)
    cell_metadata = Column(JSON, default=dict)
    is_executed = Column(Boolean, default=False)
    executed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notebook = relationship("Notebook", back_populates="cells")
