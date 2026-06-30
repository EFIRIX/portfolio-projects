from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=["timestamp", "consumption"])

    columns_map = {str(col).strip().lower(): str(col) for col in df.columns}
    ts_col = (
        columns_map.get("timestamp")
        or columns_map.get("datetime")
        or columns_map.get("date_time")
        or columns_map.get("date")
    )
    if ts_col is None:
        return pd.DataFrame(columns=["timestamp", "consumption"])

    val_col = (
        columns_map.get("consumption")
        or columns_map.get("load")
        or columns_map.get("energy")
        or columns_map.get("aep_mw")
        or columns_map.get("aerix_mw")
    )
    if val_col is None:
        numeric_candidates = [
            col
            for col in df.columns
            if col != ts_col and pd.to_numeric(df[col], errors="coerce").notna().any()
        ]
        if not numeric_candidates:
            return pd.DataFrame(columns=["timestamp", "consumption"])
        val_col = numeric_candidates[0]

    normalized = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(df[ts_col], errors="coerce", utc=True),
            "consumption": pd.to_numeric(df[val_col], errors="coerce"),
        }
    )
    normalized = normalized.dropna(subset=["timestamp", "consumption"]).copy()
    if normalized.empty:
        return normalized
    normalized["timestamp"] = normalized["timestamp"].dt.tz_convert("UTC").dt.tz_localize(None)
    normalized = normalized.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    return normalized.reset_index(drop=True)


def _drift_score(current_df: pd.DataFrame, baseline_df: pd.DataFrame) -> float:
    if current_df.empty or baseline_df.empty:
        return 0.0
    current_mean = float(current_df["consumption"].mean())
    base_mean = float(baseline_df["consumption"].mean())
    base_std = float(baseline_df["consumption"].std(ddof=0))
    if base_std <= 1e-12:
        base_std = abs(base_mean) if abs(base_mean) > 1e-12 else 1.0
    return float((current_mean - base_mean) / base_std)


def _timestamp_gap_ratio(df: pd.DataFrame) -> float:
    if len(df) < 3:
        return 0.0
    diffs = df["timestamp"].diff().dropna()
    hours = pd.to_numeric(diffs.dt.total_seconds() / 3600.0, errors="coerce").dropna()
    if hours.empty:
        return 0.0
    median_step = float(hours.median())
    if median_step <= 0:
        return 1.0
    return float((hours > (median_step * 3.0)).mean())


def _abnormal_range_ratio(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    values = pd.to_numeric(df["consumption"], errors="coerce").dropna()
    if values.empty:
        return 0.0
    mean = float(values.mean())
    std = float(values.std(ddof=0))
    if std <= 1e-12:
        return 0.0
    z_scores = (values - mean) / std
    return float((z_scores.abs() > 4.0).mean())


def assess_dataset_health(
    current_df: pd.DataFrame,
    baseline_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    current = _normalize(current_df)
    baseline = _normalize(baseline_df) if baseline_df is not None else pd.DataFrame(
        columns=["timestamp", "consumption"]
    )

    current_schema = list(current.columns)
    baseline_schema = list(baseline.columns)
    schema_drift = bool(baseline_schema and current_schema != baseline_schema)

    drift_value = _drift_score(current, baseline) if not baseline.empty else 0.0
    gap_ratio = _timestamp_gap_ratio(current)
    abnormal_ratio = _abnormal_range_ratio(current)

    return {
        "rows": int(len(current)),
        "schema_drift": schema_drift,
        "dataset_drift": float(drift_value),
        "timestamp_gap_ratio": float(gap_ratio),
        "abnormal_range_ratio": float(abnormal_ratio),
    }


def monitor_training_pool(
    training_pool_path: str | Path = Path("data") / "training_pool" / "global_training_pool.csv",
    baseline_path: str | Path = Path("data") / "grid_training_pool.csv",
) -> dict[str, Any]:
    pool_path = Path(training_pool_path)
    baseline = Path(baseline_path)

    if not pool_path.exists():
        return {
            "rows": 0,
            "schema_drift": False,
            "dataset_drift": 0.0,
            "timestamp_gap_ratio": 0.0,
            "abnormal_range_ratio": 0.0,
            "status": "no_training_pool",
        }

    try:
        pool_df = pd.read_csv(pool_path)
    except Exception:
        return {
            "rows": 0,
            "schema_drift": True,
            "dataset_drift": 0.0,
            "timestamp_gap_ratio": 1.0,
            "abnormal_range_ratio": 1.0,
            "status": "pool_read_error",
        }

    baseline_df = None
    if baseline.exists():
        try:
            baseline_df = pd.read_csv(baseline)
        except Exception:
            baseline_df = None

    metrics = assess_dataset_health(pool_df, baseline_df)
    metrics["status"] = "ok"
    return metrics
