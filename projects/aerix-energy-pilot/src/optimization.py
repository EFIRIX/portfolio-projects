from __future__ import annotations

import numpy as np
import pandas as pd


def _prepare_predictions(predictions: pd.DataFrame | pd.Series) -> pd.DataFrame:
    """Normalize predictions input to a DataFrame with timestamp and predicted_consumption."""
    if isinstance(predictions, pd.DataFrame):
        if {"timestamp", "predicted_consumption"}.issubset(predictions.columns):
            df = predictions.copy()
        elif predictions.shape[1] == 1 and isinstance(predictions.index, pd.DatetimeIndex):
            df = pd.DataFrame(
                {
                    "timestamp": predictions.index,
                    "predicted_consumption": predictions.iloc[:, 0].values,
                }
            )
        else:
            raise ValueError(
                "predictions must include ['timestamp', 'predicted_consumption'] "
                "or be a single-column DataFrame with DatetimeIndex."
            )
    elif isinstance(predictions, pd.Series):
        if not isinstance(predictions.index, pd.DatetimeIndex):
            raise ValueError("Series predictions must use DatetimeIndex.")
        df = pd.DataFrame({"timestamp": predictions.index, "predicted_consumption": predictions.values})
    else:
        raise TypeError("predictions must be a pandas DataFrame or Series.")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["predicted_consumption"] = pd.to_numeric(df["predicted_consumption"], errors="coerce")
    df = df.dropna(subset=["timestamp", "predicted_consumption"]).sort_values("timestamp").reset_index(drop=True)
    return df


def _prepare_peak_timestamps(peaks) -> pd.Series:
    """Normalize peak input to a datetime Series."""
    if isinstance(peaks, pd.DataFrame):
        if "timestamp" not in peaks.columns:
            raise ValueError("peaks DataFrame must include 'timestamp'.")
        peak_ts = pd.to_datetime(peaks["timestamp"], errors="coerce")
    else:
        peak_ts = pd.to_datetime(pd.Series(peaks), errors="coerce")

    return peak_ts.dropna()


def optimize_peaks(
    predictions: pd.DataFrame | pd.Series,
    peaks,
    shift_min: float,
    shift_max: float,
) -> tuple[pd.DataFrame, float, float]:
    """
    Reduce each peak by a random fraction and shift that load to the nearest non-peak hour.

    Returns:
    - optimized_predictions
    - peak_reduction_mw
    - peak_reduction_percent
    """
    if shift_min < 0 or shift_max < 0 or shift_min > shift_max:
        raise ValueError("shift_min and shift_max must satisfy 0 <= shift_min <= shift_max.")

    optimized_predictions = _prepare_predictions(predictions)
    if optimized_predictions.empty:
        return optimized_predictions, 0.0, 0.0

    peak_timestamps = _prepare_peak_timestamps(peaks)
    if peak_timestamps.empty:
        return optimized_predictions, 0.0, 0.0

    peak_mask = optimized_predictions["timestamp"].isin(set(peak_timestamps.tolist()))
    peak_indices = optimized_predictions.index[peak_mask].tolist()
    non_peak_indices = optimized_predictions.index[~peak_mask].tolist()

    if not peak_indices or not non_peak_indices:
        return optimized_predictions, 0.0, 0.0

    rng = np.random.default_rng(42)
    total_peak_load = float(optimized_predictions.loc[peak_indices, "predicted_consumption"].sum())
    total_reduction = 0.0

    for peak_idx in peak_indices:
        peak_time = optimized_predictions.loc[peak_idx, "timestamp"]
        nearest_non_peak_idx = min(
            non_peak_indices,
            key=lambda idx: abs(optimized_predictions.loc[idx, "timestamp"] - peak_time),
        )

        shift_fraction = float(rng.uniform(shift_min, shift_max))
        current_peak_load = float(optimized_predictions.loc[peak_idx, "predicted_consumption"])
        reduction_mw = current_peak_load * shift_fraction

        optimized_predictions.loc[peak_idx, "predicted_consumption"] = current_peak_load - reduction_mw
        optimized_predictions.loc[nearest_non_peak_idx, "predicted_consumption"] += reduction_mw
        total_reduction += reduction_mw

    peak_reduction_percent = (total_reduction / total_peak_load) * 100 if total_peak_load > 0 else 0.0
    return optimized_predictions, float(total_reduction), float(peak_reduction_percent)



def recommend_load_shifts(
    peaks_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    shift_min: float = 0.10,
    shift_max: float = 0.20,
    random_seed: int = 42,
) -> tuple[pd.DataFrame, float]:
    """
    Suggest shifting 10-20% of each peak hour load to nearest non-peak hour.

    Returns:
    - recommendations DataFrame
    - estimated peak reduction percentage
    """
    if peaks_df.empty:
        empty_cols = [
            "peak_hour",
            "predicted_peak_load",
            "suggested_shift_to_hour",
            "shift_percentage",
            "shift_amount",
        ]
        return pd.DataFrame(columns=empty_cols), 0.0

    peaks_df = peaks_df.dropna(subset=["timestamp", "predicted_consumption"]).copy()
    if peaks_df.empty:
        return pd.DataFrame(), 0.0

    non_peak_df = forecast_df[~forecast_df["is_peak"]].dropna(subset=["timestamp"]).copy()
    if non_peak_df.empty:
        return pd.DataFrame(), 0.0

    rng = np.random.default_rng(random_seed)
    recs = []

    for _, peak_row in peaks_df.iterrows():
        peak_time = peak_row["timestamp"]
        nearest_idx = (non_peak_df["timestamp"] - peak_time).abs().idxmin()
        target_row = non_peak_df.loc[nearest_idx]

        shift_pct = float(rng.uniform(shift_min, shift_max))
        shift_amount = float(peak_row["predicted_consumption"] * shift_pct)

        recs.append(
            {
                "peak_hour": peak_time,
                "predicted_peak_load": float(peak_row["predicted_consumption"]),
                "suggested_shift_to_hour": target_row["timestamp"],
                "shift_percentage": shift_pct,
                "shift_amount": shift_amount,
            }
        )

    rec_df = pd.DataFrame(recs)

    total_peak_load = float(peaks_df["predicted_consumption"].sum())
    total_shift_amount = float(rec_df["shift_amount"].sum())

    peak_reduction_pct = (total_shift_amount / total_peak_load) * 100 if total_peak_load > 0 else 0.0

    return rec_df, peak_reduction_pct
