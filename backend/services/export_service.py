"""
Export Service — Multi-format dataset export (CSV, Excel, JSON, Parquet).

Supports filtering, column selection, and chunked streaming for large files.
"""

import io
import json
import logging
from typing import Optional, List

import pandas as pd

logger = logging.getLogger(__name__)


def export_dataset(
    df: pd.DataFrame,
    fmt: str = "csv",
    columns: Optional[List[str]] = None,
    max_rows: Optional[int] = None,
) -> tuple[bytes, str, str]:
    """
    Export a DataFrame to the specified format.

    Returns (bytes_data, media_type, file_extension).
    """
    if columns:
        valid_cols = [c for c in columns if c in df.columns]
        if valid_cols:
            df = df[valid_cols]

    if max_rows and len(df) > max_rows:
        df = df.head(max_rows)

    fmt = fmt.lower()

    if fmt == "csv":
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        data = buf.getvalue().encode("utf-8")
        return data, "text/csv", ".csv"

    elif fmt == "excel" or fmt == "xlsx":
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Data")
        data = buf.getvalue()
        return data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"

    elif fmt == "json":
        data = df.to_json(orient="records", date_format="iso").encode("utf-8")
        return data, "application/json", ".json"

    elif fmt == "parquet":
        buf = io.BytesIO()
        df.to_parquet(buf, index=False, engine="pyarrow")
        data = buf.getvalue()
        return data, "application/octet-stream", ".parquet"

    elif fmt == "tsv":
        buf = io.StringIO()
        df.to_csv(buf, index=False, sep="\t")
        data = buf.getvalue().encode("utf-8")
        return data, "text/tab-separated-values", ".tsv"

    else:
        raise ValueError(f"Unsupported export format: {fmt}. Use csv, excel, json, parquet, or tsv.")


def compare_datasets(df1: pd.DataFrame, df2: pd.DataFrame, name1: str = "Dataset A", name2: str = "Dataset B") -> dict:
    """
    Compare two DataFrames statistically.
    Returns a structured comparison report.
    """
    result: dict = {
        "datasets": [name1, name2],
        "shape": {
            name1: {"rows": len(df1), "columns": len(df1.columns)},
            name2: {"rows": len(df2), "columns": len(df2.columns)},
        },
        "common_columns": [],
        "only_in_first": [],
        "only_in_second": [],
        "column_stats": {},
        "summary": [],
    }

    cols1 = set(df1.columns)
    cols2 = set(df2.columns)
    common = sorted(cols1 & cols2)
    result["common_columns"] = common
    result["only_in_first"] = sorted(cols1 - cols2)
    result["only_in_second"] = sorted(cols2 - cols1)

    # Per-column stat comparison
    for col in common:
        s1 = df1[col]
        s2 = df2[col]
        col_info: dict = {"dtype1": str(s1.dtype), "dtype2": str(s2.dtype)}

        if pd.api.types.is_numeric_dtype(s1) and pd.api.types.is_numeric_dtype(s2):
            def safe_stats(s: pd.Series) -> dict:
                return {
                    "mean": round(float(s.mean()), 4) if len(s.dropna()) > 0 else None,
                    "std": round(float(s.std()), 4) if len(s.dropna()) > 1 else None,
                    "min": round(float(s.min()), 4) if len(s.dropna()) > 0 else None,
                    "max": round(float(s.max()), 4) if len(s.dropna()) > 0 else None,
                    "null_pct": round(s.isna().mean() * 100, 2),
                }

            col_info["stats1"] = safe_stats(s1)
            col_info["stats2"] = safe_stats(s2)

            if col_info["stats1"]["mean"] and col_info["stats2"]["mean"]:
                mean_diff_pct = abs(col_info["stats1"]["mean"] - col_info["stats2"]["mean"])
                baseline = max(abs(col_info["stats1"]["mean"]), 1e-9)
                col_info["mean_diff_pct"] = round(mean_diff_pct / baseline * 100, 2)

        elif pd.api.types.is_object_dtype(s1) or pd.api.types.is_categorical_dtype(s1):
            col_info["unique1"] = int(s1.nunique())
            col_info["unique2"] = int(s2.nunique())
            col_info["null_pct1"] = round(s1.isna().mean() * 100, 2)
            col_info["null_pct2"] = round(s2.isna().mean() * 100, 2)
            # Top values in common
            top1 = set(s1.value_counts().head(5).index.tolist())
            top2 = set(s2.value_counts().head(5).index.tolist())
            col_info["top_values_overlap"] = len(top1 & top2)

        result["column_stats"][col] = col_info

    # High-level summary bullets
    summary = []
    row_diff = len(df1) - len(df2)
    if row_diff != 0:
        summary.append(f"{name1} has {'more' if row_diff > 0 else 'fewer'} rows than {name2} ({abs(row_diff):,} difference).")
    if result["only_in_first"]:
        summary.append(f"{len(result['only_in_first'])} column(s) only in {name1}: {', '.join(result['only_in_first'][:5])}.")
    if result["only_in_second"]:
        summary.append(f"{len(result['only_in_second'])} column(s) only in {name2}: {', '.join(result['only_in_second'][:5])}.")
    numeric_common = [c for c in common if pd.api.types.is_numeric_dtype(df1[c]) and pd.api.types.is_numeric_dtype(df2[c])]
    if numeric_common:
        drifted = [c for c in numeric_common if result["column_stats"][c].get("mean_diff_pct", 0) > 10]
        if drifted:
            summary.append(f"{len(drifted)} numeric column(s) show >10% mean drift: {', '.join(drifted[:3])}.")
    result["summary"] = summary

    return result
