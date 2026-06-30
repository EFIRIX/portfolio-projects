from __future__ import annotations

import pandas as pd



def preprocess_energy_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and normalize energy consumption time-series data."""
    cleaned = df.copy()

    # Support input where timestamp is already the DatetimeIndex.
    if "timestamp" not in cleaned.columns:
        if not isinstance(cleaned.index, pd.DatetimeIndex):
            raise ValueError("Input must include a 'timestamp' column or a DatetimeIndex.")
        index_name = cleaned.index.name if cleaned.index.name else "timestamp"
        cleaned = cleaned.reset_index().rename(columns={index_name: "timestamp"})

    if "consumption" not in cleaned.columns:
        raise ValueError("Input data must include a 'consumption' column.")

    cleaned["timestamp"] = pd.to_datetime(cleaned["timestamp"], errors="coerce")
    cleaned["consumption"] = pd.to_numeric(cleaned["consumption"], errors="coerce")
    if "normalized_consumption" in cleaned.columns:
        cleaned["normalized_consumption"] = pd.to_numeric(
            cleaned["normalized_consumption"], errors="coerce"
        )
    if "region_peak" in cleaned.columns:
        cleaned["region_peak"] = pd.to_numeric(cleaned["region_peak"], errors="coerce")

    cleaned = cleaned.dropna(subset=["timestamp"]).sort_values("timestamp")
    cleaned = cleaned.drop_duplicates(subset=["timestamp"], keep="last")

    cleaned = cleaned.set_index("timestamp")

    # Reindex to hourly frequency to make gaps explicit.
    full_index = pd.date_range(cleaned.index.min(), cleaned.index.max(), freq="h")
    cleaned = cleaned.reindex(full_index)
    cleaned.index.name = "timestamp"

    # Fill missing values with interpolation and edge fills.
    cleaned["consumption"] = cleaned["consumption"].interpolate(method="time")
    cleaned["consumption"] = cleaned["consumption"].ffill().bfill()
    cleaned["consumption"] = cleaned["consumption"].clip(lower=0)

    if "region_peak" in cleaned.columns:
        cleaned["region_peak"] = cleaned["region_peak"].ffill().bfill()
        fallback_peak = float(cleaned["consumption"].max()) if len(cleaned) else 1.0
        if not pd.notna(fallback_peak) or fallback_peak <= 0:
            fallback_peak = 1.0
        cleaned["region_peak"] = cleaned["region_peak"].fillna(fallback_peak)
        cleaned.loc[cleaned["region_peak"] <= 0, "region_peak"] = fallback_peak
    else:
        fallback_peak = float(cleaned["consumption"].max()) if len(cleaned) else 1.0
        if not pd.notna(fallback_peak) or fallback_peak <= 0:
            fallback_peak = 1.0
        cleaned["region_peak"] = fallback_peak

    if "region_name" in cleaned.columns:
        cleaned["region_name"] = cleaned["region_name"].ffill().bfill().fillna("unknown_region")

    # Keep normalized target aligned with restored MW scale.
    cleaned["normalized_consumption"] = cleaned["consumption"] / cleaned["region_peak"]
    cleaned["normalized_consumption"] = cleaned["normalized_consumption"].clip(lower=0)

    return cleaned.reset_index()
