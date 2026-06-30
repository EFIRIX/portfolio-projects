from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.precision import round_df, round_float


def detect_machine_anomalies(telemetry_df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect per-machine telemetry anomalies.

    Supported anomaly classes:
    - load_spike
    - overheating
    - runtime_anomaly
    """
    anomaly_columns = ["machine_id", "timestamp", "anomaly_type", "metric_value", "severity", "reason"]
    if telemetry_df is None or telemetry_df.empty:
        return pd.DataFrame(columns=anomaly_columns)

    work_df = telemetry_df.copy()
    work_df["machine_id"] = work_df["machine_id"].astype(str)
    work_df["timestamp"] = pd.to_datetime(work_df["timestamp"], errors="coerce")
    work_df["current_load_mw"] = pd.to_numeric(work_df["current_load_mw"], errors="coerce")
    work_df["temperature"] = pd.to_numeric(work_df["temperature"], errors="coerce")
    work_df["runtime_hours"] = pd.to_numeric(work_df["runtime_hours"], errors="coerce")
    work_df = work_df.dropna(subset=["machine_id", "timestamp", "current_load_mw", "temperature", "runtime_hours"])
    if work_df.empty:
        return pd.DataFrame(columns=anomaly_columns)

    global_load_threshold = float(work_df["current_load_mw"].quantile(0.9))
    if not np.isfinite(global_load_threshold) or global_load_threshold <= 0:
        global_load_threshold = float(work_df["current_load_mw"].max())

    anomalies: list[dict[str, Any]] = []
    for row in work_df.itertuples(index=False):
        machine_id = str(row.machine_id)
        timestamp = pd.Timestamp(row.timestamp)
        load = float(row.current_load_mw)
        temperature = float(row.temperature)
        runtime_hours = float(row.runtime_hours)

        machine_rows = work_df[work_df["machine_id"] == machine_id]
        machine_mean_load = float(machine_rows["current_load_mw"].mean())
        machine_std_load = float(machine_rows["current_load_mw"].std(ddof=0))
        dynamic_threshold = machine_mean_load + (2.5 * machine_std_load)
        load_threshold = max(global_load_threshold, dynamic_threshold)

        if load > load_threshold and load_threshold > 0:
            severity = min(1.0, load / load_threshold)
            anomalies.append(
                {
                    "machine_id": machine_id,
                    "timestamp": timestamp,
                    "anomaly_type": "load_spike",
                    "metric_value": load,
                    "severity": severity,
                    "reason": "Unexpected load spike above dynamic threshold.",
                }
            )

        if temperature > 85.0:
            severity = min(1.0, temperature / 100.0)
            anomalies.append(
                {
                    "machine_id": machine_id,
                    "timestamp": timestamp,
                    "anomaly_type": "overheating",
                    "metric_value": temperature,
                    "severity": severity,
                    "reason": "Machine temperature exceeds safe operating level.",
                }
            )

        if runtime_hours > 20.0 or runtime_hours < 0.25:
            severity = min(1.0, abs(runtime_hours - 8.0) / 12.0)
            anomalies.append(
                {
                    "machine_id": machine_id,
                    "timestamp": timestamp,
                    "anomaly_type": "runtime_anomaly",
                    "metric_value": runtime_hours,
                    "severity": severity,
                    "reason": "Runtime is outside expected operational window.",
                }
            )

    if not anomalies:
        return pd.DataFrame(columns=anomaly_columns)

    anomalies_df = pd.DataFrame(anomalies).sort_values(["timestamp", "machine_id", "anomaly_type"]).reset_index(
        drop=True
    )
    anomalies_df = round_df(anomalies_df, numeric_only=True)
    anomalies_df["severity"] = anomalies_df["severity"].apply(lambda value: round_float(value, 6))
    anomalies_df["metric_value"] = anomalies_df["metric_value"].apply(lambda value: round_float(value, 6))
    return anomalies_df[anomaly_columns]
