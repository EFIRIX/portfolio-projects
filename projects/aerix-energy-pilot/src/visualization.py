from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"



def run_eda(df: pd.DataFrame) -> dict[str, float | str | int]:
    """Compute lightweight EDA summary statistics."""
    summary = {
        "rows": int(len(df)),
        "start_timestamp": str(df["timestamp"].min()),
        "end_timestamp": str(df["timestamp"].max()),
        "mean_consumption": float(df["consumption"].mean()),
        "std_consumption": float(df["consumption"].std()),
        "min_consumption": float(df["consumption"].min()),
        "max_consumption": float(df["consumption"].max()),
        "missing_consumption": int(df["consumption"].isna().sum()),
    }
    return summary



def _resolve_output_path(output_path: str | Path, default_filename: str) -> Path:
    """Always save figures into the project's outputs folder."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    filename = Path(output_path).name if str(output_path).strip() else default_filename
    if not filename.lower().endswith(".png"):
        filename = f"{filename}.png"

    return OUTPUT_DIR / filename



def _normalize_prediction_df(predictions: pd.DataFrame | pd.Series) -> pd.DataFrame:
    if isinstance(predictions, pd.DataFrame):
        if {"timestamp", "predicted_consumption"}.issubset(predictions.columns):
            df = predictions[["timestamp", "predicted_consumption"]].copy()
        elif predictions.shape[1] == 1 and isinstance(predictions.index, pd.DatetimeIndex):
            df = pd.DataFrame(
                {
                    "timestamp": predictions.index,
                    "predicted_consumption": predictions.iloc[:, 0].values,
                }
            )
        else:
            raise ValueError(
                "predictions must include ['timestamp', 'predicted_consumption'] or be a single-column DataFrame with DatetimeIndex."
            )
    elif isinstance(predictions, pd.Series):
        if not isinstance(predictions.index, pd.DatetimeIndex):
            raise ValueError("Series predictions must use DatetimeIndex.")
        df = pd.DataFrame({"timestamp": predictions.index, "predicted_consumption": predictions.values})
    else:
        raise TypeError("predictions must be a pandas DataFrame or Series.")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["predicted_consumption"] = pd.to_numeric(df["predicted_consumption"], errors="coerce")
    return df.dropna(subset=["timestamp", "predicted_consumption"]).sort_values("timestamp")



def plot_historical(df: pd.DataFrame, output_path: str | Path) -> Path:
    """Plot historical consumption and save under outputs/."""
    fig_path = _resolve_output_path(output_path, "historical_consumption.png")

    plot_df = df.copy()
    if "timestamp" not in plot_df.columns:
        if isinstance(plot_df.index, pd.DatetimeIndex):
            index_name = plot_df.index.name if plot_df.index.name else "timestamp"
            plot_df = plot_df.reset_index().rename(columns={index_name: "timestamp"})
        else:
            raise ValueError("Historical data must include a timestamp column or DatetimeIndex.")

    if "consumption" not in plot_df.columns:
        raise ValueError("Historical data must include a consumption column.")

    plot_df["timestamp"] = pd.to_datetime(plot_df["timestamp"], errors="coerce")
    plot_df["consumption"] = pd.to_numeric(plot_df["consumption"], errors="coerce")
    plot_df = plot_df.dropna(subset=["timestamp", "consumption"]).sort_values("timestamp")

    plt.figure(figsize=(12, 4))
    plt.plot(plot_df["timestamp"], plot_df["consumption"], color="tab:blue", linewidth=1.2)
    plt.title("Historical Energy Consumption")
    plt.xlabel("Timestamp")
    plt.ylabel("Consumption")
    plt.tight_layout()
    plt.savefig(fig_path, dpi=140)
    plt.close()

    return fig_path



def plot_forecast_vs_actual(y_test: Any, y_pred: Any, output_path: str | Path) -> Path:
    """Plot actual vs forecast values and save under outputs/."""
    fig_path = _resolve_output_path(output_path, "forecast_vs_actual.png")

    if isinstance(y_test, pd.Series) and isinstance(y_test.index, pd.DatetimeIndex):
        x_axis = pd.to_datetime(y_test.index, errors="coerce")
        y_actual = pd.to_numeric(y_test, errors="coerce").reset_index(drop=True)
    else:
        y_actual = pd.to_numeric(pd.Series(y_test), errors="coerce").reset_index(drop=True)
        x_axis = pd.RangeIndex(start=0, stop=len(y_actual), step=1)

    y_forecast = pd.to_numeric(pd.Series(y_pred), errors="coerce").reset_index(drop=True)

    n = min(len(y_actual), len(y_forecast))
    y_actual = y_actual.iloc[:n]
    y_forecast = y_forecast.iloc[:n]
    if isinstance(x_axis, pd.RangeIndex):
        x_axis = pd.RangeIndex(start=0, stop=n, step=1)
    else:
        x_axis = pd.Series(x_axis).iloc[:n]

    plt.figure(figsize=(10, 4))
    plt.plot(x_axis, y_actual, label="Actual", marker="o", linewidth=1.6)
    plt.plot(x_axis, y_forecast, label="Forecast", marker="x", linewidth=1.6)
    plt.title("Forecast vs Actual (Next 24 Hours)")
    plt.xlabel("Timestamp")
    plt.ylabel("Consumption")
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_path, dpi=140)
    plt.close()

    return fig_path



def plot_detected_peaks(predictions: pd.DataFrame | pd.Series, peaks: Any, output_path: str | Path) -> Path:
    """Plot predictions with detected peaks highlighted and save under outputs/."""
    fig_path = _resolve_output_path(output_path, "detected_peaks.png")

    prediction_df = _normalize_prediction_df(predictions)

    if isinstance(peaks, pd.DataFrame):
        if "timestamp" not in peaks.columns:
            raise ValueError("peaks DataFrame must include a timestamp column.")
        peak_timestamps = pd.to_datetime(peaks["timestamp"], errors="coerce").dropna()
    else:
        peak_timestamps = pd.to_datetime(pd.Series(peaks), errors="coerce").dropna()

    peak_set = set(peak_timestamps.tolist())
    peak_df = prediction_df[prediction_df["timestamp"].isin(peak_set)]

    plt.figure(figsize=(10, 4))
    plt.plot(
        prediction_df["timestamp"],
        prediction_df["predicted_consumption"],
        label="Predicted",
        color="tab:green",
        linewidth=1.6,
    )
    plt.scatter(
        peak_df["timestamp"],
        peak_df["predicted_consumption"],
        color="tab:red",
        label="Detected Peaks",
        s=60,
        zorder=3,
    )
    plt.title("Detected Peak Hours (Forecast)")
    plt.xlabel("Timestamp")
    plt.ylabel("Predicted Consumption")
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_path, dpi=140)
    plt.close()

    return fig_path
