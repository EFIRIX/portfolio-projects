from __future__ import annotations

from pathlib import Path

import pandas as pd


WEATHER_COLUMNS = ["temperature", "humidity", "wind_speed", "pressure"]


def load_weather_data(weather_path: str | Path = "data/weather.csv") -> pd.DataFrame | None:
    """Load optional weather data. Returns None when file is unavailable/invalid."""
    path = Path(weather_path)
    if not path.exists():
        return None

    try:
        weather_df = pd.read_csv(path)
    except Exception:
        return None

    if "timestamp" not in weather_df.columns:
        return None

    weather_df = weather_df.copy()
    weather_df["timestamp"] = pd.to_datetime(weather_df["timestamp"], errors="coerce")

    existing_columns = [col for col in WEATHER_COLUMNS if col in weather_df.columns]
    if not existing_columns:
        return None

    for col in existing_columns:
        weather_df[col] = pd.to_numeric(weather_df[col], errors="coerce")

    weather_df = weather_df[["timestamp", *existing_columns]].dropna(subset=["timestamp"])
    if weather_df.empty:
        return None

    weather_df = weather_df.sort_values("timestamp")
    weather_df = weather_df.drop_duplicates(subset=["timestamp"], keep="last")

    weather_df = weather_df.set_index("timestamp")
    weather_df = weather_df.resample("h").mean()
    weather_df = weather_df.interpolate(method="time").ffill().bfill()

    return weather_df.reset_index()


def merge_weather_features(
    energy_df: pd.DataFrame,
    weather_df: pd.DataFrame | None,
) -> pd.DataFrame:
    """Merge optional weather features by timestamp without breaking existing flow."""
    if weather_df is None or weather_df.empty:
        return energy_df

    if "timestamp" not in energy_df.columns:
        return energy_df

    merged = energy_df.copy()
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], errors="coerce")

    weather = weather_df.copy()
    weather["timestamp"] = pd.to_datetime(weather["timestamp"], errors="coerce")

    try:
        merged = merged.merge(weather, on="timestamp", how="left")
        for col in WEATHER_COLUMNS:
            if col in merged.columns:
                merged[col] = pd.to_numeric(merged[col], errors="coerce")
                merged[col] = merged[col].interpolate(method="linear").ffill().bfill()
        return merged
    except Exception:
        return energy_df
