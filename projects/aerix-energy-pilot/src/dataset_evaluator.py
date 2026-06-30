from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_BASELINE_PATH = Path("data") / "grid_training_pool.csv"
DEFAULT_BASELINE_FALLBACK = Path("data") / "grid_AEP.csv"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return float(max(low, min(high, value)))


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    mapping = {str(col).strip().lower(): str(col) for col in df.columns}
    for candidate in candidates:
        hit = mapping.get(candidate.strip().lower())
        if hit:
            return hit
    return None


def _normalize_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=["timestamp", "consumption"]), {
            "valid": False,
            "reason": "empty_dataframe",
        }

    timestamp_col = _find_column(df, ["timestamp", "datetime", "date_time", "date", "Datetime"])
    if timestamp_col is None:
        return pd.DataFrame(columns=["timestamp", "consumption"]), {
            "valid": False,
            "reason": "missing_timestamp",
        }

    consumption_col = _find_column(df, ["consumption", "load", "energy", "aep_mw", "mw", "AERIX_MW"])
    if consumption_col is None:
        numeric_candidates = [
            col
            for col in df.columns
            if col != timestamp_col and pd.to_numeric(df[col], errors="coerce").notna().any()
        ]
        consumption_col = numeric_candidates[0] if numeric_candidates else None

    if consumption_col is None:
        return pd.DataFrame(columns=["timestamp", "consumption"]), {
            "valid": False,
            "reason": "missing_consumption_or_load",
        }

    normalized = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(df[timestamp_col], errors="coerce", utc=True),
            "consumption": pd.to_numeric(df[consumption_col], errors="coerce"),
        }
    )
    normalized = normalized.dropna(subset=["timestamp", "consumption"]).copy()
    if normalized.empty:
        return pd.DataFrame(columns=["timestamp", "consumption"]), {
            "valid": False,
            "reason": "no_valid_rows",
        }

    normalized["timestamp"] = normalized["timestamp"].dt.tz_convert("UTC").dt.tz_localize(None)
    normalized = normalized.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    normalized = normalized.reset_index(drop=True)

    return normalized, {
        "valid": True,
        "reason": "ok",
        "timestamp_column": timestamp_col,
        "consumption_column": consumption_col,
        "rows": int(len(normalized)),
    }


def _load_baseline_df(baseline_path: str | Path | None = None) -> pd.DataFrame:
    candidates = []
    if baseline_path is not None:
        candidates.append(Path(baseline_path))
    candidates.extend([DEFAULT_BASELINE_PATH, DEFAULT_BASELINE_FALLBACK])

    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            raw = pd.read_csv(candidate)
            normalized, meta = _normalize_dataset(raw)
            if meta.get("valid") and not normalized.empty:
                return normalized
        except Exception:
            continue
    return pd.DataFrame(columns=["timestamp", "consumption"])


def _schema_score(normalized_df: pd.DataFrame) -> float:
    if normalized_df.empty:
        return 0.0
    expected = {"timestamp", "consumption"}
    has_expected = expected.issubset(set(normalized_df.columns))
    return 1.0 if has_expected else 0.0


def _missing_quality_score(raw_df: pd.DataFrame) -> float:
    if raw_df.empty:
        return 0.0
    missing_ratio = float(raw_df.isna().mean().mean())
    return _clamp(1.0 - missing_ratio)


def _timestamp_continuity_score(normalized_df: pd.DataFrame) -> float:
    if len(normalized_df) < 3:
        return 0.4

    diffs = normalized_df["timestamp"].diff().dropna()
    diffs_hours = pd.to_numeric(diffs.dt.total_seconds() / 3600.0, errors="coerce").dropna()
    if diffs_hours.empty:
        return 0.3

    median_step = float(diffs_hours.median())
    if median_step <= 0:
        return 0.2

    large_gap_ratio = float((diffs_hours > (median_step * 3.0)).mean())
    return _clamp(1.0 - large_gap_ratio)


def _variance_score(normalized_df: pd.DataFrame) -> float:
    if normalized_df.empty:
        return 0.0

    values = pd.to_numeric(normalized_df["consumption"], errors="coerce").dropna()
    if values.empty:
        return 0.0

    mean_abs = float(values.abs().mean())
    if mean_abs <= 1e-12:
        return 0.0

    coefficient_var = float(values.std(ddof=0) / mean_abs)
    # Saturate near CV=1 for robust scale-independent scoring.
    return _clamp(coefficient_var / 1.0)


def _distribution_similarity_score(normalized_df: pd.DataFrame, baseline_df: pd.DataFrame) -> float:
    if normalized_df.empty or baseline_df.empty:
        return 0.5

    data_values = pd.to_numeric(normalized_df["consumption"], errors="coerce").dropna()
    baseline_values = pd.to_numeric(baseline_df["consumption"], errors="coerce").dropna()
    if data_values.empty or baseline_values.empty:
        return 0.5

    quantiles = np.linspace(0.05, 0.95, 19)
    data_q = np.quantile(data_values.values, quantiles)
    base_q = np.quantile(baseline_values.values, quantiles)

    scale = float(np.std(baseline_values.values))
    if scale <= 1e-12:
        scale = float(np.abs(np.mean(baseline_values.values))) or 1.0

    mean_abs_diff = float(np.mean(np.abs(data_q - base_q)))
    similarity = 1.0 - (mean_abs_diff / (3.0 * scale))
    return _clamp(similarity)


def _expected_model_gain(
    quality_score: float,
    similarity_score: float,
    variance_score: float,
    baseline_rows: int,
    dataset_rows: int,
) -> float:
    coverage_factor = _clamp(dataset_rows / max(1000.0, float(baseline_rows or 1)))
    raw_gain = (
        (quality_score * 0.35)
        + (similarity_score * 0.35)
        + (variance_score * 0.20)
        + (coverage_factor * 0.10)
        - 0.55
    )
    return float(raw_gain)


def calculate_dataset_score(metrics: dict[str, Any]) -> float:
    schema_score = float(metrics.get("schema_score", 0.0))
    quality_score = float(metrics.get("quality_score", 0.0))
    similarity_score = float(metrics.get("similarity_score", 0.0))
    variance_score = float(
        metrics.get(
            "feature_variance_score",
            metrics.get("variance_score", 0.0),
        )
    )
    return _clamp(
        (schema_score * 0.25)
        + (quality_score * 0.35)
        + (similarity_score * 0.30)
        + (variance_score * 0.10)
    )


def should_accept_dataset(score: dict[str, Any] | float | int) -> bool:
    if isinstance(score, dict):
        final_score = float(score.get("final_score", 0.0))
        expected_gain = float(score.get("expected_model_gain", 0.0))
        return bool(final_score > 0.65 and expected_gain > 0.0)

    final_score = float(score)
    return bool(final_score > 0.65)


def evaluate_dataset(df: pd.DataFrame, baseline_df: pd.DataFrame) -> dict[str, Any]:
    normalized_df, meta = _normalize_dataset(df)
    baseline_norm, _ = _normalize_dataset(baseline_df)

    schema_score = _schema_score(normalized_df) if meta.get("valid") else 0.0
    missing_ratio = float(df.isna().mean().mean()) if not df.empty else 1.0
    missing_score = _missing_quality_score(df)
    continuity_score = _timestamp_continuity_score(normalized_df) if meta.get("valid") else 0.0
    variance_score = _variance_score(normalized_df) if meta.get("valid") else 0.0
    quality_score = _clamp((missing_score * 0.4) + (continuity_score * 0.4) + (variance_score * 0.2))
    similarity_score = _distribution_similarity_score(normalized_df, baseline_norm) if meta.get("valid") else 0.0

    expected_gain = (
        _expected_model_gain(
            quality_score=quality_score,
            similarity_score=similarity_score,
            variance_score=variance_score,
            baseline_rows=len(baseline_norm),
            dataset_rows=len(normalized_df),
        )
        if meta.get("valid")
        else -1.0
    )

    final_score = calculate_dataset_score(
        {
            "schema_score": schema_score,
            "quality_score": quality_score,
            "similarity_score": similarity_score,
            "feature_variance_score": variance_score,
        }
    )

    result = {
        "schema_score": float(schema_score),
        "quality_score": float(quality_score),
        "similarity_score": float(similarity_score),
        "missing_value_ratio": float(missing_ratio),
        "timestamp_continuity_score": float(continuity_score),
        "feature_variance_score": float(variance_score),
        "expected_model_gain": float(expected_gain),
        "final_score": float(final_score),
        "accepted": False,
        "reason": str(meta.get("reason", "ok")),
        "rows": int(meta.get("rows", 0)),
    }
    result["accepted"] = should_accept_dataset(result)
    if not result["accepted"] and result["reason"] == "ok":
        if result["final_score"] <= 0.65:
            result["reason"] = "final_score_below_threshold"
        elif result["expected_model_gain"] <= 0:
            result["reason"] = "expected_gain_not_positive"
    return result


def score_dataset(df: pd.DataFrame, baseline_df: pd.DataFrame) -> dict[str, Any]:
    """
    Backward-compatible alias for evaluate_dataset.
    """
    return evaluate_dataset(df, baseline_df)


def evaluate_dataset_for_training(
    dataset_path: str | Path,
    baseline_path: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(dataset_path)
    if not path.exists():
        return {
            "dataset_path": str(path),
            "schema_score": 0.0,
            "quality_score": 0.0,
            "similarity_score": 0.0,
            "expected_model_gain": -1.0,
            "final_score": 0.0,
            "accepted": False,
            "reason": "dataset_not_found",
            "rows": 0,
        }

    try:
        raw_df = pd.read_csv(path)
    except Exception as exc:
        return {
            "dataset_path": str(path),
            "schema_score": 0.0,
            "quality_score": 0.0,
            "similarity_score": 0.0,
            "expected_model_gain": -1.0,
            "final_score": 0.0,
            "accepted": False,
            "reason": f"read_error:{exc}",
            "rows": 0,
        }

    baseline_df = _load_baseline_df(baseline_path)
    score = evaluate_dataset(raw_df, baseline_df)
    score["dataset_path"] = str(path)
    return score
