"""Tests for authentication endpoints."""

import pytest


def test_demo_login(client):
    resp = client.post("/api/auth/demo-login")
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "user" in data
    assert data["user"]["email"] == "demo@analyst.ai"


def test_register_and_login(client):
    # Register
    resp = client.post("/api/auth/register", json={
        "email": "test_unit@example.com",
        "username": "test_unit_user",
        "password": "securepass123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data

    # Login
    resp = client.post("/api/auth/login", json={
        "email": "test_unit@example.com",
        "password": "securepass123",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", json={
        "email": "demo@analyst.ai",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


def test_get_me(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "email" in data
    assert "username" in data


def test_get_me_unauthorized(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code in (401, 403)


def test_update_profile(client, auth_headers):
    resp = client.patch("/api/auth/me", json={"username": "demo_analyst_updated"}, headers=auth_headers)
    # Should succeed or fail with 400 if username is taken
    assert resp.status_code in (200, 400)
    if resp.status_code == 200:
        # Restore original username
        client.patch("/api/auth/me", json={"username": "demo_analyst"}, headers=auth_headers)


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_version_endpoint(client):
    resp = client.get("/api/version")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "features" in data
    assert data["features"]["nl2sql"] is True
    assert data["features"]["alerts"] is True
