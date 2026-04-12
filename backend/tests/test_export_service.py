"""Tests for the export service utility."""

import io
import pytest
import pandas as pd
from services.export_service import export_dataset, compare_datasets


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie", "Dave"],
        "age": [30, 25, 35, 28],
        "score": [90.5, 85.0, 92.3, 78.9],
        "city": ["NYC", "LA", "Chicago", "NYC"],
    })


def test_export_csv(sample_df):
    data, media_type, ext = export_dataset(sample_df, fmt="csv")
    assert ext == ".csv"
    assert "text/csv" in media_type
    df_back = pd.read_csv(io.BytesIO(data))
    assert list(df_back.columns) == list(sample_df.columns)
    assert len(df_back) == len(sample_df)


def test_export_json(sample_df):
    data, media_type, ext = export_dataset(sample_df, fmt="json")
    assert ext == ".json"
    import json
    records = json.loads(data)
    assert isinstance(records, list)
    assert len(records) == len(sample_df)


def test_export_tsv(sample_df):
    data, media_type, ext = export_dataset(sample_df, fmt="tsv")
    assert ext == ".tsv"
    df_back = pd.read_csv(io.BytesIO(data), sep="\t")
    assert len(df_back) == len(sample_df)


def test_export_with_column_filter(sample_df):
    data, _, _ = export_dataset(sample_df, fmt="csv", columns=["name", "age"])
    df_back = pd.read_csv(io.BytesIO(data))
    assert list(df_back.columns) == ["name", "age"]


def test_export_with_max_rows(sample_df):
    data, _, _ = export_dataset(sample_df, fmt="csv", max_rows=2)
    df_back = pd.read_csv(io.BytesIO(data))
    assert len(df_back) == 2


def test_export_unsupported_format(sample_df):
    with pytest.raises(ValueError, match="Unsupported export format"):
        export_dataset(sample_df, fmt="pdf")


def test_compare_identical_datasets(sample_df):
    result = compare_datasets(sample_df, sample_df, "A", "A")
    assert result["common_columns"] == sorted(sample_df.columns.tolist())
    assert result["only_in_first"] == []
    assert result["only_in_second"] == []


def test_compare_different_datasets():
    df1 = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
    df2 = pd.DataFrame({"x": [10, 20, 30], "z": [7, 8, 9]})
    result = compare_datasets(df1, df2, "First", "Second")
    assert "y" in result["only_in_first"]
    assert "z" in result["only_in_second"]
    assert "x" in result["common_columns"]
    assert len(result["summary"]) > 0


def test_compare_drift_detection():
    df1 = pd.DataFrame({"val": [100, 200, 300, 400, 500]})
    df2 = pd.DataFrame({"val": [1000, 2000, 3000, 4000, 5000]})  # 10x drift
    result = compare_datasets(df1, df2)
    # Should detect >10% mean drift
    assert any("drift" in s.lower() for s in result["summary"])
