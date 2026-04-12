"""
Forecasting Service
Supports ARIMA, Exponential Smoothing, and Linear Trend projection.
Falls back gracefully when statsmodels is unavailable.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _detect_date_and_target(df: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
    """Auto-detect the date column and a suitable numeric target column."""
    date_col = None
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            date_col = col
            break
    if date_col is None:
        # Try parsing object columns
        for col in df.select_dtypes(include="object").columns:
            try:
                parsed = pd.to_datetime(df[col], infer_datetime_format=True)
                df[col] = parsed
                date_col = col
                break
            except Exception:
                continue

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    target_col = numeric_cols[0] if numeric_cols else None
    return date_col, target_col


def _linear_forecast(series: pd.Series, periods: int) -> Tuple[List[float], List[float], List[float]]:
    """Simple linear regression trend forecast with confidence bands."""
    from sklearn.linear_model import LinearRegression

    X = np.arange(len(series)).reshape(-1, 1)
    y = series.values
    model = LinearRegression()
    model.fit(X, y)

    future_X = np.arange(len(series), len(series) + periods).reshape(-1, 1)
    preds = model.predict(future_X).tolist()

    residuals = y - model.predict(X)
    std = float(np.std(residuals))
    lower = [p - 1.96 * std for p in preds]
    upper = [p + 1.96 * std for p in preds]
    return preds, lower, upper


def _exp_smoothing_forecast(series: pd.Series, periods: int) -> Tuple[List[float], List[float], List[float]]:
    """Holt-Winters Exponential Smoothing forecast."""
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        model = ExponentialSmoothing(series, trend="add", seasonal=None, initialization_method="estimated")
        fitted = model.fit(optimized=True)
        preds = fitted.forecast(periods).tolist()
        # Approximate confidence intervals from residual std
        residuals = series.values - fitted.fittedvalues.values
        std = float(np.std(residuals))
        lower = [p - 1.96 * std for p in preds]
        upper = [p + 1.96 * std for p in preds]
        return preds, lower, upper
    except Exception as e:
        logger.warning(f"ExponentialSmoothing failed: {e}, falling back to linear")
        return _linear_forecast(series, periods)


def _arima_forecast(series: pd.Series, periods: int) -> Tuple[List[float], List[float], List[float]]:
    """ARIMA forecast with auto-order selection (simple grid)."""
    try:
        from statsmodels.tsa.arima.model import ARIMA

        best_aic = np.inf
        best_order = (1, 1, 1)
        for p in range(0, 3):
            for d in range(0, 2):
                for q in range(0, 2):
                    try:
                        m = ARIMA(series, order=(p, d, q)).fit()
                        if m.aic < best_aic:
                            best_aic = m.aic
                            best_order = (p, d, q)
                    except Exception:
                        continue

        model = ARIMA(series, order=best_order).fit()
        forecast = model.get_forecast(steps=periods)
        preds = forecast.predicted_mean.tolist()
        ci = forecast.conf_int(alpha=0.05)
        lower = ci.iloc[:, 0].tolist()
        upper = ci.iloc[:, 1].tolist()
        return preds, lower, upper
    except Exception as e:
        logger.warning(f"ARIMA failed: {e}, falling back to exp smoothing")
        return _exp_smoothing_forecast(series, periods)


def _compute_metrics(actual: np.ndarray, fitted: np.ndarray) -> Dict[str, float]:
    """Compute MAE and RMSE on in-sample fit."""
    mae = float(np.mean(np.abs(actual - fitted)))
    rmse = float(np.sqrt(np.mean((actual - fitted) ** 2)))
    # MAPE — skip zeros
    nonzero = actual != 0
    mape = float(np.mean(np.abs((actual[nonzero] - fitted[nonzero]) / actual[nonzero])) * 100) if nonzero.any() else 0.0
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "mape": round(mape, 2)}


def _build_chart(
    date_col: str,
    target_col: str,
    historical_dates: List[str],
    historical_values: List[float],
    future_dates: List[str],
    predictions: List[float],
    lower: List[float],
    upper: List[float],
) -> Dict[str, Any]:
    """Build a Plotly chart spec for the forecast."""
    return {
        "type": "forecast",
        "title": f"{target_col} Forecast",
        "data": [
            {
                "x": historical_dates,
                "y": historical_values,
                "type": "scatter",
                "mode": "lines",
                "name": "Historical",
                "line": {"color": "rgba(99,102,241,1)", "width": 2},
            },
            {
                "x": future_dates,
                "y": predictions,
                "type": "scatter",
                "mode": "lines+markers",
                "name": "Forecast",
                "line": {"color": "rgba(16,185,129,1)", "width": 2, "dash": "dash"},
            },
            {
                "x": future_dates + future_dates[::-1],
                "y": upper + lower[::-1],
                "fill": "toself",
                "fillcolor": "rgba(16,185,129,0.15)",
                "line": {"color": "transparent"},
                "name": "95% CI",
                "type": "scatter",
                "showlegend": True,
            },
        ],
        "layout": {
            "title": f"{target_col} Forecast",
            "xaxis_title": date_col,
            "yaxis_title": target_col,
            "showlegend": True,
        },
    }


def run_forecast(
    df: pd.DataFrame,
    date_column: Optional[str] = None,
    target_column: Optional[str] = None,
    periods: int = 30,
    method: str = "auto",
) -> Dict[str, Any]:
    """
    Main forecast entry point.
    Returns: predictions, confidence intervals, metrics, Plotly chart, method used.
    """
    # Auto-detect columns if not provided
    if not date_column or not target_column:
        auto_date, auto_target = _detect_date_and_target(df)
        date_column = date_column or auto_date
        target_column = target_column or auto_target

    if not date_column:
        return {"error": "No date column detected. Please specify a date column."}
    if not target_column:
        return {"error": "No numeric target column detected."}
    if date_column not in df.columns:
        return {"error": f"Date column '{date_column}' not found."}
    if target_column not in df.columns:
        return {"error": f"Target column '{target_column}' not found."}

    # Prepare time series
    ts_df = df[[date_column, target_column]].copy()
    ts_df[date_column] = pd.to_datetime(ts_df[date_column], infer_datetime_format=True, errors="coerce")
    ts_df = ts_df.dropna(subset=[date_column, target_column])
    ts_df = ts_df.sort_values(date_column).reset_index(drop=True)

    if len(ts_df) < 10:
        return {"error": "Need at least 10 data points for forecasting."}

    series = ts_df[target_column].astype(float)

    # Choose method
    used_method = method
    if method == "auto":
        used_method = "arima" if len(series) >= 30 else "exp_smoothing" if len(series) >= 15 else "linear"

    # Run forecast
    if used_method == "arima":
        preds, lower, upper = _arima_forecast(series, periods)
    elif used_method == "exp_smoothing":
        preds, lower, upper = _exp_smoothing_forecast(series, periods)
    else:
        preds, lower, upper = _linear_forecast(series, periods)

    # Generate future dates
    last_date = ts_df[date_column].iloc[-1]
    try:
        freq = pd.infer_freq(ts_df[date_column]) or "D"
    except Exception:
        freq = "D"
    future_idx = pd.date_range(start=last_date, periods=periods + 1, freq=freq)[1:]
    future_dates = [d.strftime("%Y-%m-%d") for d in future_idx]

    # In-sample metrics (use last 20% as pseudo-test)
    split = max(int(len(series) * 0.8), 5)
    train = series.iloc[:split]
    if used_method == "arima":
        fitted_preds, _, _ = _arima_forecast(train, len(series) - split)
    elif used_method == "exp_smoothing":
        fitted_preds, _, _ = _exp_smoothing_forecast(train, len(series) - split)
    else:
        fitted_preds, _, _ = _linear_forecast(train, len(series) - split)

    actual_test = series.iloc[split:].values
    fitted_arr = np.array(fitted_preds[: len(actual_test)])
    metrics = _compute_metrics(actual_test, fitted_arr) if len(actual_test) > 0 else {}

    historical_dates = [d.strftime("%Y-%m-%d") for d in ts_df[date_column]]
    historical_values = series.tolist()

    chart = _build_chart(
        date_column, target_column,
        historical_dates, historical_values,
        future_dates, preds, lower, upper,
    )

    return {
        "date_column": date_column,
        "target_column": target_column,
        "method": used_method,
        "periods": periods,
        "historical": {"dates": historical_dates, "values": historical_values},
        "forecast": {
            "dates": future_dates,
            "predictions": [round(p, 4) for p in preds],
            "lower": [round(v, 4) for v in lower],
            "upper": [round(v, 4) for v in upper],
        },
        "metrics": metrics,
        "chart": chart,
        "summary": (
            f"{target_column} is forecast to reach "
            f"{preds[-1]:.2f} in {periods} periods "
            f"(from current {historical_values[-1]:.2f}). "
            f"Method: {used_method.upper()}."
        ),
    }
