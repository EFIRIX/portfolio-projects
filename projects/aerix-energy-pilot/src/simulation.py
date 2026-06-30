from __future__ import annotations

from typing import Any

import pandas as pd


def _to_series(forecast: pd.Series | pd.DataFrame) -> pd.Series:
    if isinstance(forecast, pd.DataFrame):
        if "predicted_consumption" in forecast.columns:
            return pd.to_numeric(forecast["predicted_consumption"], errors="coerce").dropna().reset_index(drop=True)
        if forecast.shape[1] >= 1:
            return pd.to_numeric(forecast.iloc[:, 0], errors="coerce").dropna().reset_index(drop=True)
    return pd.to_numeric(pd.Series(forecast), errors="coerce").dropna().reset_index(drop=True)


def simulate_peak_reduction(
    forecast: pd.Series | pd.DataFrame,
    peak_threshold: float,
    reduction_percent: float,
) -> pd.Series:
    """Reduce values above threshold by reduction_percent (0-1)."""
    series = _to_series(forecast)
    pct = max(0.0, min(float(reduction_percent), 1.0))
    reduced = series.copy()
    mask = reduced > float(peak_threshold)
    reduced.loc[mask] = reduced.loc[mask] * (1.0 - pct)
    return reduced


def simulate_load_shift(
    original: pd.Series | pd.DataFrame,
    reduced: pd.Series,
    shift_percent: float,
) -> pd.Series:
    """Shift a part of reduced peak load into the lowest-load hours."""
    original_series = _to_series(original)
    optimized = reduced.copy().reset_index(drop=True)
    if original_series.empty or optimized.empty:
        return optimized

    shift_pct = max(0.0, min(float(shift_percent), 1.0))
    if shift_pct <= 0:
        return optimized

    aligned_len = min(len(original_series), len(optimized))
    original_series = original_series.iloc[:aligned_len]
    optimized = optimized.iloc[:aligned_len]

    reduced_energy = (original_series - optimized).clip(lower=0).sum()
    shift_energy = float(reduced_energy) * shift_pct
    if shift_energy <= 0:
        return optimized

    target_count = max(1, int(aligned_len * 0.25))
    low_load_idx = optimized.nsmallest(target_count).index
    per_slot = shift_energy / float(len(low_load_idx))
    optimized.loc[low_load_idx] = optimized.loc[low_load_idx] + per_slot
    return optimized


def simulate_energy_savings(
    original_peak: float,
    simulated_peak: float,
    price_per_mwh: float,
    co2_factor: float,
) -> dict[str, float]:
    reduced_mw = max(0.0, float(original_peak) - float(simulated_peak))
    savings = reduced_mw * float(price_per_mwh)
    co2_reduction = reduced_mw * float(co2_factor)
    return {
        "simulated_peak_load": float(simulated_peak),
        "peak_reduction_mw": reduced_mw,
        "simulated_savings": float(savings),
        "simulated_co2_reduction": float(co2_reduction),
    }


def simulate_system(
    forecast: pd.Series | pd.DataFrame,
    peak_threshold: float,
    peak_reduction_percent: float,
    load_shift_percent: float,
    price_per_mwh: float,
    co2_factor: float,
) -> dict[str, Any]:
    """Full optional digital twin simulation."""
    original = _to_series(forecast)
    reduced = simulate_peak_reduction(
        forecast=original,
        peak_threshold=peak_threshold,
        reduction_percent=peak_reduction_percent,
    )
    optimized = simulate_load_shift(
        original=original,
        reduced=reduced,
        shift_percent=load_shift_percent,
    )

    original_peak = float(original.max()) if not original.empty else 0.0
    simulated_peak = float(optimized.max()) if not optimized.empty else 0.0
    savings = simulate_energy_savings(
        original_peak=original_peak,
        simulated_peak=simulated_peak,
        price_per_mwh=price_per_mwh,
        co2_factor=co2_factor,
    )

    return {
        "original_series": original,
        "optimized_series": optimized,
        "original_peak": original_peak,
        **savings,
    }
