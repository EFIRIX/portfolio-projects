from __future__ import annotations

import numpy as np
import pandas as pd


def _normalize_percentile(percentile: float) -> float:
    """Accept percentile in [0, 1] or [0, 100] and normalize to [0, 100]."""
    if 0 < percentile <= 1:
        return percentile * 100
    if 0 < percentile <= 100:
        return percentile
    raise ValueError("percentile must be in the range (0, 1] or (0, 100].")


def get_peak_threshold(series: pd.Series, percentile: float) -> float:
    """Compute the peak threshold from a prediction series and percentile."""
    values = pd.to_numeric(pd.Series(series), errors="coerce").dropna()
    if values.empty:
        raise ValueError("Cannot compute peak threshold from an empty series.")

    normalized_percentile = _normalize_percentile(percentile)
    return float(np.percentile(values, normalized_percentile))


def detect_peaks(predictions: pd.Series | pd.DataFrame, threshold: float) -> tuple[list, list]:
    """
    Detect peak points above threshold.

    Returns:
    - list of peak timestamps
    - list of peak values
    """
    if isinstance(predictions, pd.DataFrame):
        if {"timestamp", "predicted_consumption"}.issubset(predictions.columns):
            prediction_df = predictions[["timestamp", "predicted_consumption"]].copy()
        elif predictions.shape[1] == 1 and isinstance(predictions.index, pd.DatetimeIndex):
            prediction_df = pd.DataFrame(
                {
                    "timestamp": predictions.index,
                    "predicted_consumption": predictions.iloc[:, 0],
                }
            )
        else:
            raise ValueError(
                "DataFrame predictions must include ['timestamp', 'predicted_consumption'] "
                "or use a DatetimeIndex with one value column."
            )
    elif isinstance(predictions, pd.Series):
        if not isinstance(predictions.index, pd.DatetimeIndex):
            raise ValueError("Series predictions must use a DatetimeIndex for timestamp output.")
        prediction_df = pd.DataFrame(
            {"timestamp": predictions.index, "predicted_consumption": predictions.values}
        )
    else:
        raise TypeError("predictions must be a pandas Series or DataFrame.")

    prediction_df["timestamp"] = pd.to_datetime(prediction_df["timestamp"], errors="coerce")
    prediction_df["predicted_consumption"] = pd.to_numeric(
        prediction_df["predicted_consumption"], errors="coerce"
    )
    prediction_df = prediction_df.dropna(
        subset=["timestamp", "predicted_consumption"]
    )

    peak_rows = prediction_df[prediction_df["predicted_consumption"] > threshold]

    peak_timestamps = peak_rows["timestamp"].tolist()
    peak_values = peak_rows["predicted_consumption"].astype(float).tolist()
    return peak_timestamps, peak_values
