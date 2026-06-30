from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from src.precision import round_df


def _resolve_timestamp(timestamp: pd.Timestamp | None = None) -> pd.Timestamp:
    if timestamp is None:
        return pd.Timestamp(datetime.now(timezone.utc)).tz_convert(None)
    resolved = pd.to_datetime(timestamp, errors="coerce")
    if pd.isna(resolved):
        return pd.Timestamp(datetime.now(timezone.utc)).tz_convert(None)
    return pd.Timestamp(resolved).tz_localize(None) if pd.Timestamp(resolved).tzinfo else pd.Timestamp(resolved)


def stream_machine_telemetry(
    equipment_df: pd.DataFrame,
    seed: int | None = None,
    timestamp: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Simulate machine telemetry stream.

    Randomness is intentionally allowed in telemetry simulation only.
    """
    if equipment_df is None or equipment_df.empty:
        return pd.DataFrame(columns=["machine_id", "timestamp", "current_load_mw", "temperature", "runtime_hours"])

    resolved_ts = _resolve_timestamp(timestamp)
    rng = np.random.default_rng(seed)

    telemetry_rows: list[dict[str, Any]] = []
    for row in equipment_df.sort_values("machine_id").itertuples(index=False):
        machine_id = str(getattr(row, "machine_id"))
        power_mw = float(getattr(row, "power_mw", 0.0))
        availability = bool(getattr(row, "availability", True))

        base_load = power_mw * 0.68 if availability else 0.0
        fluctuation = float(rng.normal(0.0, max(power_mw * 0.07, 0.02)))
        current_load = max(0.0, min(base_load + fluctuation, max(power_mw * 1.25, 0.05)))

        load_ratio = (current_load / power_mw) if power_mw > 0 else 0.0
        temperature = 32.0 + (load_ratio * 46.0) + float(rng.normal(0.0, 2.2))
        temperature = max(15.0, temperature)

        runtime_hours = max(0.0, float(rng.uniform(0.5, 24.0))) if availability else 0.0

        telemetry_rows.append(
            {
                "machine_id": machine_id,
                "timestamp": resolved_ts,
                "current_load_mw": current_load,
                "temperature": temperature,
                "runtime_hours": runtime_hours,
            }
        )

    telemetry_df = pd.DataFrame(telemetry_rows)
    telemetry_df = round_df(telemetry_df, numeric_only=True)
    return telemetry_df
