"""Tests for dataset endpoints."""

import io
import pytest
import pandas as pd


def test_list_datasets_empty(client, auth_headers):
    resp = client.get("/api/datasets/", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_upload_dataset(client, auth_headers, sample_csv_bytes):
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("sales.csv", sample_csv_bytes, "text/csv")},
        data={"name": "Sales Data"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["status"] == "ready"
    assert data["row_count"] == 50
    assert data["column_count"] == 5


def test_upload_invalid_extension(client, auth_headers):
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("data.txt", b"hello world", "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_get_dataset(client, auth_headers, uploaded_dataset):
    dataset_id = uploaded_dataset["id"]
    resp = client.get(f"/api/datasets/{dataset_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == dataset_id
    assert data["status"] == "ready"


def test_get_dataset_not_found(client, auth_headers):
    resp = client.get("/api/datasets/nonexistent-id", headers=auth_headers)
    assert resp.status_code == 404


def test_preview_dataset(client, auth_headers, uploaded_dataset):
    dataset_id = uploaded_dataset["id"]
    resp = client.get(f"/api/datasets/{dataset_id}/preview?rows=5", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "columns" in data
    assert "rows" in data
    assert len(data["rows"]) <= 5
    assert data["total_rows"] == 50


def test_profile_dataset(client, auth_headers, uploaded_dataset):
    dataset_id = uploaded_dataset["id"]
    resp = client.get(f"/api/datasets/{dataset_id}/profile", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "shape" in data
    assert "columns" in data


def test_export_dataset_csv(client, auth_headers, uploaded_dataset):
    dataset_id = uploaded_dataset["id"]
    resp = client.get(f"/api/datasets/{dataset_id}/export?fmt=csv", headers=auth_headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    content = resp.content.decode("utf-8")
    assert "sales" in content
    assert "region" in content


def test_export_dataset_json(client, auth_headers, uploaded_dataset):
    dataset_id = uploaded_dataset["id"]
    resp = client.get(f"/api/datasets/{dataset_id}/export?fmt=json", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 50


def test_export_dataset_invalid_format(client, auth_headers, uploaded_dataset):
    dataset_id = uploaded_dataset["id"]
    resp = client.get(f"/api/datasets/{dataset_id}/export?fmt=pdf", headers=auth_headers)
    assert resp.status_code == 400


def test_clean_dataset(client, auth_headers, uploaded_dataset):
    dataset_id = uploaded_dataset["id"]
    resp = client.post(
        f"/api/datasets/{dataset_id}/clean",
        json={"missing_strategy": "median", "remove_outliers": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "report" in data


def test_delete_dataset(client, auth_headers, sample_csv_bytes):
    # Upload a dataset to delete
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("to_delete.csv", sample_csv_bytes, "text/csv")},
        data={"name": "To Delete"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    dataset_id = resp.json()["id"]

    # Delete it
    resp = client.delete(f"/api/datasets/{dataset_id}", headers=auth_headers)
    assert resp.status_code == 200

    # Confirm gone
    resp = client.get(f"/api/datasets/{dataset_id}", headers=auth_headers)
    assert resp.status_code == 404
