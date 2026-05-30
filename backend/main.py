"""
DataMind AI Analytics Platform — FastAPI Backend
"""

import os
import time
import logging
from contextlib import asynccontextmanager

# Load .env file before anything else (override=True ensures .env wins over
# any stale/empty shell env vars that may be set in the parent process)
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass  # python-dotenv not installed — env vars must be set manually

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn

from routers import datasets, analytics, chat, insights, dashboards, auth, reports
from routers import copilot, forecasting, pipeline, autonomous
from routers import alerts, nl2sql, connections, scheduled_reports
from routers import workspaces, api_keys, webhooks, notifications, metrics, sharing
# Phase 6 — AI Supremacy
from routers import ai_models, root_cause, automl
# Phase 7 — Real-time & Integrations
from routers import realtime
# Phase 8 — Collaboration & Polish
from routers import templates, catalog
# Phase 9-17 — World-Class Features
from routers import proactive, scenarios, streaming, digest
# Phase 18 — Multi-Tenant Admin System
from routers import admin as admin_router
# Phase 19 — Autonomous Agent + Domain Templates + Custom Reports
from routers import agent as agent_router
from routers import domain_templates as domain_templates_router
from routers import custom_reports as custom_reports_router
# Phase 20 — Notebooks (Julius-killer)
from routers import notebooks as notebooks_router
from models.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    ",".join([
        f"http://localhost:{p}" for p in range(3000, 3010)
    ] + [
        f"http://127.0.0.1:{p}" for p in range(3000, 3010)
    ]),
).split(",")


# ── Rate Limiter ─────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ── Lifespan ─────────────────────────────────────────────────────
def _seed_superadmin():
    """Create or upgrade the SuperAdmin account from env vars (idempotent)."""
    import uuid as _uuid
    email = os.getenv("SUPERADMIN_EMAIL")
    password = os.getenv("SUPERADMIN_PASSWORD")
    if not email or not password:
        return
    from models.database import SessionLocal, User, Workspace, WorkspaceMember
    from security.auth import get_password_hash
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            if existing.role != "superadmin":
                existing.role = "superadmin"
                db.commit()
                logger.info(f"Upgraded {email} to superadmin")
            return
        ws = Workspace(id=str(_uuid.uuid4()), name="Platform Admin")
        db.add(ws)
        db.flush()
        user = User(
            id=str(_uuid.uuid4()),
            email=email,
            username="superadmin",
            hashed_password=get_password_hash(password),
            role="superadmin",
            workspace_id=ws.id,
        )
        db.add(user)
        db.flush()
        db.add(WorkspaceMember(
            id=str(_uuid.uuid4()),
            workspace_id=ws.id,
            user_id=user.id,
            role="owner",
        ))
        db.commit()
        logger.info(f"SuperAdmin account created: {email}")
    except Exception as e:
        logger.error(f"SuperAdmin seed failed: {e}")
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting DataMind AI Analytics Platform API…")
    init_db()
    logger.info("Database initialized")
    _seed_superadmin()
    yield
    logger.info("Shutting down…")


# ── FastAPI app ───────────────────────────────────────────────────
app = FastAPI(
    title="DataMind AI Analytics Platform",
    description=(
        "Enterprise-grade AI-powered data analytics platform. "
        "Supports multi-tenant analytics, NL2SQL, RAG-based chat, "
        "forecasting, anomaly detection, and automated alerting."
    ),
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if ENVIRONMENT != "production" else None,
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Middleware ────────────────────────────────────────────────────

# GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{(time.time() - start) * 1000:.1f}ms"
    return response


# ── Routers ───────────────────────────────────────────────────────
# Core
app.include_router(auth.router,        prefix="/api/auth",        tags=["Authentication"])
app.include_router(datasets.router,    prefix="/api/datasets",    tags=["Datasets"])
app.include_router(analytics.router,   prefix="/api/analytics",   tags=["Analytics"])
app.include_router(chat.router,        prefix="/api/chat",        tags=["AI Chat"])
app.include_router(insights.router,    prefix="/api/insights",    tags=["Insights"])
app.include_router(dashboards.router,  prefix="/api/dashboards",  tags=["Dashboards"])
app.include_router(reports.router,     prefix="/api/reports",     tags=["Reports"])
# Enterprise extensions
app.include_router(copilot.router,     prefix="/api/copilot",     tags=["AI Copilot"])
app.include_router(forecasting.router, prefix="/api/forecasting", tags=["Forecasting"])
app.include_router(pipeline.router,    prefix="/api/pipeline",    tags=["Auto Pipeline"])
app.include_router(autonomous.router,  prefix="/api/autonomous",  tags=["Autonomous Analyst"])
# Phase 1 new features
app.include_router(alerts.router,            prefix="/api/alerts",             tags=["Alerts"])
app.include_router(nl2sql.router,            prefix="/api/nl2sql",             tags=["NL2SQL"])
# Phase 2 new features
app.include_router(connections.router,       prefix="/api/connections",        tags=["Data Connections"])
app.include_router(scheduled_reports.router, prefix="/api/scheduled-reports",  tags=["Scheduled Reports"])
# Phase 3–5 new features
app.include_router(workspaces.router,        prefix="/api/workspaces",         tags=["Workspaces"])
app.include_router(api_keys.router,          prefix="/api/auth/api-keys",      tags=["API Keys"])
app.include_router(webhooks.router,          prefix="/api/webhooks",           tags=["Webhooks"])
app.include_router(notifications.router,     prefix="/api/notifications",      tags=["Notifications"])
app.include_router(metrics.router,           prefix="/api/metrics",            tags=["Metrics"])
# Sharing: dashboard-scoped routes + public view
app.include_router(sharing.router,           prefix="/api/dashboards",         tags=["Sharing"])
app.include_router(sharing.public_router,    prefix="/api/shared",             tags=["Public Share"])
# Phase 6 — AI Supremacy
app.include_router(ai_models.router,         prefix="/api/ai",                 tags=["AI Models"])
app.include_router(root_cause.router,        prefix="/api/root-cause",         tags=["Root Cause Analysis"])
app.include_router(automl.router,            prefix="/api/automl",             tags=["AutoML"])
# Phase 7 — Real-time
app.include_router(realtime.router,          prefix="/api",                    tags=["Real-time WebSocket"])
# Phase 8 — Collaboration
app.include_router(templates.router,         prefix="/api/templates",          tags=["Dashboard Templates"])
app.include_router(catalog.router,           prefix="/api/catalog",            tags=["Data Catalog"])
# Phase 9-17 — World-Class Features
app.include_router(proactive.router)
app.include_router(scenarios.router)
app.include_router(streaming.router)
app.include_router(digest.router)
# Phase 18 — SuperAdmin
app.include_router(admin_router.router)
# Phase 19 — Autonomous Agent + Domain Templates + Custom Reports
app.include_router(agent_router.router)
app.include_router(domain_templates_router.router)
app.include_router(custom_reports_router.router)
# Phase 20 — Notebooks
app.include_router(notebooks_router.router)


# ── Health & Root ─────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["System"])
async def health():
    """Health check endpoint for load balancers and Docker."""
    return {
        "status": "healthy",
        "service": "datamind-api",
        "version": "2.0.0",
    }


@app.get("/api/version", tags=["System"])
async def version():
    """Return current API version and feature flags."""
    return {
        "version": "2.0.0",
        "features": {
            "nl2sql": True,
            "rag_chat": True,
            "alerts": True,
            "forecasting": True,
            "autonomous_analyst": True,
            "scheduled_reports": True,
            "data_connections": True,
            "redis_caching": True,
            "alembic_migrations": True,
            "auto_insights_v2": True,
            # Phase 6
            "multi_model_llm": True,
            "streaming_chat": True,
            "root_cause_analysis": True,
            "automl": True,
            # Phase 7
            "websocket_realtime": True,
            "slack_teams_telegram": True,
            "extended_connectors": True,
            # Phase 8
            "dashboard_comments": True,
            "dashboard_versions": True,
            "template_library": True,
            "data_catalog": True,
            # Phase 9-17 — World-Class Features
            "proactive_intelligence": True,
            "semantic_metric_catalog": True,
            "transparent_ai": True,
            "what_if_scenarios": True,
            "real_time_streaming": True,
            "personalized_digest": True,
            "mcp_server": True,
            "business_user_mode": True,
            "pr_review_workflow": True,
        },
    }


@app.get("/.well-known/mcp.json", include_in_schema=False)
async def mcp_manifest():
    """MCP server manifest — used by Claude Desktop / Cursor to discover DataMind tools."""
    return {
        "schema_version": "v1",
        "name": "datamind",
        "display_name": "DataMind AI Analytics",
        "description": "Query datasets, run forecasts, get insights, and search the data catalog",
        "version": "9.0.0",
        "tools": [
            {"name": "list_datasets", "description": "List all available datasets"},
            {"name": "query_dataset", "description": "Natural language query against a dataset"},
            {"name": "get_insights", "description": "Get AI insights for a dataset"},
            {"name": "get_metric", "description": "Look up a governed business metric"},
            {"name": "search_catalog", "description": "Search the data catalog"},
            {"name": "run_forecast", "description": "Run time-series forecast"},
            {"name": "get_proactive_feed", "description": "Get latest intelligence insights"},
        ],
        "connection": {
            "type": "stdio",
            "command": "python",
            "args": ["mcp_server.py"],
        },
    }


# ── CORS Proxy (dev helper) ───────────────────────────────────────
@app.api_route(
    "/proxy/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    include_in_schema=False,
)
async def proxy_api(path: str, request: Request):
    url = f"http://127.0.0.1:8001/api/{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=request.method,
            url=url,
            headers=dict(request.headers),
            content=await request.body(),
        )
    try:
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception:
        return JSONResponse(content={"detail": resp.text}, status_code=resp.status_code)


# ── Entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=ENVIRONMENT == "development",
    )
