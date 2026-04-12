"""Tests for analytics endpoints."""

import pytest


def test_analytics_overview(client, auth_headers, uploaded_dataset):
    dataset_id = uploaded_dataset["id"]
    resp = client.get(f"/api/analytics/{dataset_id}/overview", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "profile" in data
    assert "stats" in data


def test_analytics_overview_cache(client, auth_headers, uploaded_dataset):
    """Second call should be served from cache — same result."""
    dataset_id = uploaded_dataset["id"]
    r1 = client.get(f"/api/analytics/{dataset_id}/overview", headers=auth_headers)
    r2 = client.get(f"/api/analytics/{dataset_id}/overview", headers=auth_headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["profile"]["shape"] == r2.json()["profile"]["shape"]


def test_analytics_correlations(client, auth_headers, uploaded_dataset):
    dataset_id = uploaded_dataset["id"]
    resp = client.get(f"/api/analytics/{dataset_id}/correlations", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "correlations" in data


def test_analytics_outliers(client, auth_headers, uploaded_dataset):
    dataset_id = uploaded_dataset["id"]
    resp = client.get(f"/api/analytics/{dataset_id}/outliers", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "outliers" in data


def test_analytics_charts(client, auth_headers, uploaded_dataset):
    dataset_id = uploaded_dataset["id"]
    resp = client.get(f"/api/analytics/{dataset_id}/charts?max_charts=3", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "charts" in data
    assert isinstance(data["charts"], list)


def test_analytics_ml_clustering(client, auth_headers, uploaded_dataset):
    dataset_id = uploaded_dataset["id"]
    resp = client.post(
        f"/api/analytics/{dataset_id}/ml",
        json={"analysis_type": "clustering", "n_clusters": 3},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "clustering"
    assert "silhouette_score" in data


def test_analytics_ml_regression(client, auth_headers, uploaded_dataset):
    dataset_id = uploaded_dataset["id"]
    resp = client.post(
        f"/api/analytics/{dataset_id}/ml",
        json={"analysis_type": "regression", "target_column": "sales"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "regression"
    assert "r2_score" in data


def test_analytics_not_found(client, auth_headers):
    resp = client.get("/api/analytics/nonexistent/overview", headers=auth_headers)
    assert resp.status_code == 404
