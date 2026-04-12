"""Tests for alerts endpoints."""

import pytest


@pytest.fixture
def created_alert(client, auth_headers):
    resp = client.post(
        "/api/alerts/",
        json={
            "name": "High Sales Alert",
            "description": "Triggers when mean sales > 100",
            "column_name": "sales",
            "condition": "gt",
            "threshold": 100.0,
            "aggregation": "mean",
            "notify_email": False,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()


def test_list_alerts(client, auth_headers):
    resp = client.get("/api/alerts/", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_create_alert(client, auth_headers):
    resp = client.post(
        "/api/alerts/",
        json={
            "name": "Unit Test Alert",
            "column_name": "value",
            "condition": "gt",
            "threshold": 50.0,
            "aggregation": "mean",
            "notify_email": False,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Unit Test Alert"
    assert data["condition"] == "gt"


def test_get_alert(client, auth_headers, created_alert):
    alert_id = created_alert["id"]
    resp = client.get(f"/api/alerts/{alert_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == alert_id


def test_update_alert(client, auth_headers, created_alert):
    alert_id = created_alert["id"]
    resp = client.put(
        f"/api/alerts/{alert_id}",
        json={"threshold": 200.0, "is_active": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200


def test_alert_logs(client, auth_headers, created_alert):
    alert_id = created_alert["id"]
    resp = client.get(f"/api/alerts/{alert_id}/logs", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_delete_alert(client, auth_headers):
    # Create then delete
    resp = client.post(
        "/api/alerts/",
        json={
            "name": "To Delete Alert",
            "column_name": "value",
            "condition": "lt",
            "threshold": 0.0,
            "notify_email": False,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    alert_id = resp.json()["id"]

    resp = client.delete(f"/api/alerts/{alert_id}", headers=auth_headers)
    assert resp.status_code in (200, 204)

    resp = client.get(f"/api/alerts/{alert_id}", headers=auth_headers)
    assert resp.status_code == 404
