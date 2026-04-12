"""
Pytest configuration and shared fixtures for DataMind backend tests.
"""

import os
import io
import pytest
import pandas as pd

# Use a file-based SQLite test DB (avoids in-memory connection sharing issues)
_TEST_DB_PATH = "/tmp/datamind_test.db"

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("UPLOAD_DIR", "/tmp/test_uploads")

os.makedirs("/tmp/test_uploads", exist_ok=True)

# Import AFTER setting env vars
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from models.database import Base, get_db, DATABASE_URL
from main import app


# ── Test DB engine (same URL that models.database will use) ─────
_engine = create_engine(
    f"sqlite:///{_TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
)
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    yield
    # Cleanup
    Base.metadata.drop_all(bind=_engine)
    try:
        os.remove(_TEST_DB_PATH)
    except Exception:
        pass


@pytest.fixture(scope="session")
def client(setup_test_db):
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(scope="session")
def auth_headers(client):
    """Demo login — returns auth headers for the session."""
    resp = client.post("/api/auth/demo-login")
    assert resp.status_code == 200, f"Demo login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_csv_bytes():
    """A simple 50-row test CSV."""
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=50, freq="D").astype(str),
        "sales": [100 + i * 2 + (i % 5) * 10 for i in range(50)],
        "region": ["North", "South", "East", "West", "Central"] * 10,
        "units": [10 + i for i in range(50)],
        "profit": [20.0 + i * 0.5 for i in range(50)],
    })
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return buf.read()


@pytest.fixture(scope="session")
def uploaded_dataset(client, auth_headers):
    """Upload a test dataset once per test session."""
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=50, freq="D").astype(str),
        "sales": [100 + i * 2 + (i % 5) * 10 for i in range(50)],
        "region": ["North", "South", "East", "West", "Central"] * 10,
        "units": [10 + i for i in range(50)],
        "profit": [20.0 + i * 0.5 for i in range(50)],
    })
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    data = buf.read()

    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("test_data.csv", data, "text/csv")},
        data={"name": "Test Dataset"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()
