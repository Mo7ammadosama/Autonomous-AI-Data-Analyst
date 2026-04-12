"""
Data processing service: cleaning, profiling, type detection
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import json
import re
import logging

logger = logging.getLogger(__name__)


def load_dataset(file_path: str, file_type: str) -> pd.DataFrame:
    """Load dataset from file"""
    try:
        if file_type in ["csv", "text/csv"]:
            return pd.read_csv(file_path)
        elif file_type in ["json", "application/json"]:
            return pd.read_json(file_path)
        elif file_type in ["xlsx", "xls", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]:
            return pd.read_excel(file_path)
        elif file_type == "parquet":
            return pd.read_parquet(file_path)
        else:
            # Try CSV as fallback
            return pd.read_csv(file_path)
    except Exception as e:
        logger.error(f"Failed to load dataset: {e}")
        raise ValueError(f"Cannot load file: {str(e)}")


def detect_column_types(df: pd.DataFrame) -> Dict[str, str]:
    """Detect semantic types of columns"""
    types = {}
    for col in df.columns:
        dtype = str(df[col].dtype)
        sample = df[col].dropna().head(20)

        if "int" in dtype or "float" in dtype:
            # Check if it might be a year
            if df[col].dropna().between(1900, 2100).all() and df[col].dropna().apply(lambda x: x == int(x)).all():
                types[col] = "year"
            elif df[col].dropna().between(0, 1).all():
                types[col] = "percentage"
            else:
                types[col] = "numeric"
        elif "datetime" in dtype:
            types[col] = "datetime"
        elif "bool" in dtype:
            types[col] = "boolean"
        elif "object" in dtype:
            # Try datetime parse
            try:
                pd.to_datetime(sample.head(5))
                types[col] = "datetime_string"
            except Exception:
                pass

            # Check cardinality
            n_unique = df[col].nunique()
            n_total = len(df[col].dropna())
            if n_unique / max(n_total, 1) < 0.05 or n_unique <= 20:
                types[col] = "categorical"
            else:
                types[col] = "text"
        else:
            types[col] = "unknown"

    return types


def profile_dataset(df: pd.DataFrame) -> Dict[str, Any]:
    """Generate comprehensive dataset profile"""
    profile = {
        "shape": {"rows": int(df.shape[0]), "columns": int(df.shape[1])},
        "memory_usage": int(df.memory_usage(deep=True).sum()),
        "columns": {},
        "missing_summary": {},
        "duplicates": int(df.duplicated().sum()),
    }

    col_types = detect_column_types(df)

    for col in df.columns:
        col_data = df[col]
        missing = int(col_data.isna().sum())
        missing_pct = round(missing / len(col_data) * 100, 2)

        col_profile: Dict[str, Any] = {
            "dtype": str(col_data.dtype),
            "semantic_type": col_types.get(col, "unknown"),
            "missing_count": missing,
            "missing_pct": missing_pct,
            "unique_count": int(col_data.nunique()),
            "sample_values": [str(v) for v in col_data.dropna().head(5).tolist()],
        }

        if col_types.get(col) in ["numeric", "year", "percentage"]:
            try:
                col_profile.update({
                    "mean": round(float(col_data.mean()), 4) if not col_data.empty else None,
                    "median": round(float(col_data.median()), 4) if not col_data.empty else None,
                    "std": round(float(col_data.std()), 4) if not col_data.empty else None,
                    "min": round(float(col_data.min()), 4) if not col_data.empty else None,
                    "max": round(float(col_data.max()), 4) if not col_data.empty else None,
                    "q25": round(float(col_data.quantile(0.25)), 4) if not col_data.empty else None,
                    "q75": round(float(col_data.quantile(0.75)), 4) if not col_data.empty else None,
                })
            except Exception:
                pass
        elif col_types.get(col) == "categorical":
            value_counts = col_data.value_counts().head(10)
            col_profile["top_values"] = {str(k): int(v) for k, v in value_counts.items()}

        profile["columns"][col] = col_profile
        if missing > 0:
            profile["missing_summary"][col] = {"count": missing, "pct": missing_pct}

    return profile


def clean_dataset(df: pd.DataFrame, options: Optional[Dict] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Clean dataset and return cleaned df with report"""
    options = options or {}
    report = {"operations": [], "rows_before": len(df), "cols_before": len(df.columns)}

    # Remove duplicates
    dupes = df.duplicated().sum()
    if dupes > 0:
        df = df.drop_duplicates()
        report["operations"].append(f"Removed {dupes} duplicate rows")

    # Handle missing values
    for col in df.columns:
        missing = df[col].isna().sum()
        if missing == 0:
            continue
        dtype = str(df[col].dtype)
        if "int" in dtype or "float" in dtype:
            df[col] = df[col].fillna(df[col].median())
            report["operations"].append(f"Filled {missing} missing values in '{col}' with median")
        elif "object" in dtype:
            mode_val = df[col].mode()
            if not mode_val.empty:
                df[col] = df[col].fillna(mode_val[0])
                report["operations"].append(f"Filled {missing} missing values in '{col}' with mode")

    # Convert datetime columns
    col_types = detect_column_types(df)
    for col, ctype in col_types.items():
        if ctype == "datetime_string":
            try:
                df[col] = pd.to_datetime(df[col])
                report["operations"].append(f"Converted '{col}' to datetime")
            except Exception:
                pass

    report["rows_after"] = len(df)
    report["cols_after"] = len(df.columns)
    return df, report


def compute_descriptive_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """Compute descriptive statistics"""
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    stats = {}

    if numeric_cols:
        desc = df[numeric_cols].describe().round(4)
        stats["numeric"] = desc.to_dict()

    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    if cat_cols:
        stats["categorical"] = {}
        for col in cat_cols[:10]:
            vc = df[col].value_counts().head(10)
            stats["categorical"][col] = {"value_counts": vc.to_dict(), "unique": int(df[col].nunique())}

    return stats


def compute_correlations(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Compute correlation matrix"""
    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.shape[1] < 2:
        return None
    corr = numeric_df.corr().round(4)
    return {
        "matrix": corr.to_dict(),
        "columns": corr.columns.tolist(),
        "strong_pairs": find_strong_correlations(corr),
    }


def find_strong_correlations(corr_matrix: pd.DataFrame, threshold: float = 0.7) -> List[Dict]:
    """Find strongly correlated pairs"""
    pairs = []
    cols = corr_matrix.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            val = corr_matrix.iloc[i, j]
            if abs(val) >= threshold:
                pairs.append({"col1": cols[i], "col2": cols[j], "correlation": round(float(val), 4)})
    return sorted(pairs, key=lambda x: abs(x["correlation"]), reverse=True)


def detect_outliers(df: pd.DataFrame) -> Dict[str, Any]:
    """Detect outliers using IQR method"""
    outliers = {}
    numeric_cols = df.select_dtypes(include=[np.number]).columns

    for col in numeric_cols:
        Q1 = df[col].quantile(0.25)
        Q3 = df[col].quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 1.5 * IQR
        upper = Q3 + 1.5 * IQR
        outlier_mask = (df[col] < lower) | (df[col] > upper)
        count = int(outlier_mask.sum())
        if count > 0:
            outliers[col] = {
                "count": count,
                "pct": round(count / len(df) * 100, 2),
                "lower_bound": round(float(lower), 4),
                "upper_bound": round(float(upper), 4),
            }

    return outliers


def sample_data_for_chart(df: pd.DataFrame, max_rows: int = 1000) -> pd.DataFrame:
    """Sample large dataframes for visualization"""
    if len(df) > max_rows:
        return df.sample(n=max_rows, random_state=42)
    return df


def detect_dataset_type(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Determine if a dataset is TIME_SERIES or CROSS_SECTIONAL.

    Rules:
    - A 'Year' / 'yr' integer column with only 1 unique value → CROSS_SECTIONAL
    - A parsed date/datetime column with > 1 unique period → TIME_SERIES
    - No date/time column at all → CROSS_SECTIONAL
    """
    _YEAR_NAMES = {"year", "yr", "year_", "año"}

    # 1. Check integer-style year columns first (e.g. FSI dataset has Year=2023)
    for col in df.columns:
        if col.lower().strip() in _YEAR_NAMES:
            try:
                unique_vals = int(df[col].nunique())
                if unique_vals <= 1:
                    return {
                        "type": "CROSS_SECTIONAL",
                        "reason": (
                            f"Column '{col}' contains only {unique_vals} unique value "
                            f"({df[col].dropna().iloc[0] if len(df[col].dropna()) else '?'}) — "
                            "all records belong to the same period. Trend / forecasting not applicable."
                        ),
                        "date_col": col,
                        "unique_periods": unique_vals,
                    }
                else:
                    return {
                        "type": "TIME_SERIES",
                        "date_col": col,
                        "unique_periods": unique_vals,
                    }
            except Exception:
                pass

    # 2. Check for proper datetime columns
    date_cols: List[str] = []
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            date_cols.append(col)
        elif df[col].dtype == object:
            try:
                parsed = pd.to_datetime(df[col].dropna().head(10), infer_datetime_format=True)
                if len(parsed) > 0:
                    date_cols.append(col)
            except Exception:
                pass

    for col in date_cols:
        try:
            series = pd.to_datetime(df[col], errors="coerce").dropna()
            unique_periods = int(series.nunique())
            if unique_periods > 1:
                return {
                    "type": "TIME_SERIES",
                    "date_col": col,
                    "unique_periods": unique_periods,
                }
        except Exception:
            pass

    return {
        "type": "CROSS_SECTIONAL",
        "reason": "No date column with multiple time periods found.",
        "date_col": None,
        "unique_periods": 0,
    }
