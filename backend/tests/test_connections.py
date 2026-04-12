"""Tests for data connections endpoints."""

import pytest


@pytest.fixture
def sqlite_connection(client, auth_headers):
    resp = client.post(
        "/api/connections/",
        json={
            "name": "Test SQLite",
            "connection_type": "sqlite",
            "database": ":memory:",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()


def test_list_connections(client, auth_headers):
    resp = client.get("/api/connections/", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_create_sqlite_connection(client, auth_headers):
    resp = client.post(
        "/api/connections/",
        json={
            "name": "My SQLite DB",
            "connection_type": "sqlite",
            "database": ":memory:",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My SQLite DB"
    assert data["connection_type"] == "sqlite"
    assert "id" in data


def test_get_connection(client, auth_headers, sqlite_connection):
    conn_id = sqlite_connection["id"]
    resp = client.get(f"/api/connections/{conn_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == conn_id


def test_connection_not_found(client, auth_headers):
    resp = client.get("/api/connections/nonexistent", headers=auth_headers)
    assert resp.status_code == 404


def test_test_sqlite_connection(client, auth_headers, sqlite_connection):
    conn_id = sqlite_connection["id"]
    resp = client.post(f"/api/connections/{conn_id}/test", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "success" in data


def test_update_connection(client, auth_headers, sqlite_connection):
    conn_id = sqlite_connection["id"]
    resp = client.put(
        f"/api/connections/{conn_id}",
        json={"name": "Updated Connection"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


def test_delete_connection(client, auth_headers):
    # Create a connection to delete
    resp = client.post(
        "/api/connections/",
        json={"name": "To Delete", "connection_type": "sqlite", "database": ":memory:"},
        headers=auth_headers,
    )
    conn_id = resp.json()["id"]

    resp = client.delete(f"/api/connections/{conn_id}", headers=auth_headers)
    assert resp.status_code in (200, 204)

    resp = client.get(f"/api/connections/{conn_id}", headers=auth_headers)
    assert resp.status_code == 404
