from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from sklearn.ensemble import IsolationForest


def run_anomaly_detection(
    df: pd.DataFrame,
    output_path: str | Path = "outputs/anomalies.png",
    contamination: float = 0.01,
) -> dict[str, Any]:
    """
    Detect anomalies using IsolationForest on normalized_consumption.
    Runs post-prediction and does not modify training/prediction outputs.
    """
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if df is None or len(df) == 0:
        return {"status": "skipped", "reason": "empty_dataframe", "timestamps": []}

    work_df = df.copy()
    target_col = "normalized_consumption" if "normalized_consumption" in work_df.columns else "consumption"
    if target_col not in work_df.columns:
        return {"status": "skipped", "reason": "missing_target_column", "timestamps": []}

    if "timestamp" not in work_df.columns:
        return {"status": "skipped", "reason": "missing_timestamp", "timestamps": []}

    work_df["timestamp"] = pd.to_datetime(work_df["timestamp"], errors="coerce")
    work_df[target_col] = pd.to_numeric(work_df[target_col], errors="coerce")
    work_df = work_df.dropna(subset=["timestamp", target_col])

    if work_df.empty:
        return {"status": "skipped", "reason": "no_valid_rows", "timestamps": []}

    try:
        detector = IsolationForest(contamination=contamination, random_state=42)
        work_df["anomaly_flag"] = detector.fit_predict(work_df[[target_col]])
        anomalies_df = work_df[work_df["anomaly_flag"] == -1].copy()

        plt.figure(figsize=(12, 4))
        plt.plot(work_df["timestamp"], work_df[target_col], color="#5A7DFF", linewidth=1.3, label="series")
        if not anomalies_df.empty:
            plt.scatter(
                anomalies_df["timestamp"],
                anomalies_df[target_col],
                color="#FF4D4D",
                s=18,
                label="anomaly",
                zorder=3,
            )
        plt.title("Anomaly Detection")
        plt.tight_layout()
        plt.savefig(out_path, dpi=150)
        plt.close()

        timestamps = [ts.strftime("%Y-%m-%d %H:%M") for ts in anomalies_df["timestamp"]]
        return {"status": "ok", "reason": "", "timestamps": timestamps}
    except Exception as exc:
        return {"status": "skipped", "reason": f"anomaly_failed: {exc}", "timestamps": []}
