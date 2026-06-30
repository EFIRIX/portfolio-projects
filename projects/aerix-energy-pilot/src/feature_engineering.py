from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "hour_sin",
    "hour_cos",
    "day_of_week_sin",
    "day_of_week_cos",
    "month",
    "dayofyear",
    "weekofyear",
    "lag_1",
    "lag_24",
    "lag_168",
    "rolling_24",
    "rolling_168",
]
OPTIONAL_FEATURE_COLUMNS = ["temperature"]
WEATHER_OPTIONAL_COLUMNS = ["humidity", "wind_speed", "pressure"]
TARGET_COLUMN = "consumption"



def create_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add model-ready time, lag, and rolling features from timestamp and consumption."""
    featured = df.copy().sort_values("timestamp").reset_index(drop=True)
    target_col = "normalized_consumption" if "normalized_consumption" in featured.columns else TARGET_COLUMN

    # Calendar/time features.
    featured["hour"] = featured["timestamp"].dt.hour
    featured["day_of_week"] = featured["timestamp"].dt.dayofweek
    featured["hour_sin"] = np.sin(2 * np.pi * featured["hour"] / 24.0)
    featured["hour_cos"] = np.cos(2 * np.pi * featured["hour"] / 24.0)
    featured["day_of_week_sin"] = np.sin(2 * np.pi * featured["day_of_week"] / 7.0)
    featured["day_of_week_cos"] = np.cos(2 * np.pi * featured["day_of_week"] / 7.0)
    featured["month"] = featured["timestamp"].dt.month
    featured["dayofyear"] = featured["timestamp"].dt.dayofyear
    featured["weekofyear"] = featured["timestamp"].dt.isocalendar().week.astype("int64")

    # Lag features.
    featured["lag_1"] = featured[target_col].shift(1)
    featured["lag_24"] = featured[target_col].shift(24)
    featured["lag_168"] = featured[target_col].shift(168)

    # Rolling means are built from past values only (shifted) to avoid target leakage.
    past_consumption = featured[target_col].shift(1)
    featured["rolling_24"] = past_consumption.rolling(window=24, min_periods=24).mean()
    featured["rolling_168"] = past_consumption.rolling(window=168, min_periods=168).mean()

    # Drop rows with NaN after feature creation to keep X and y aligned.
    feature_columns_for_drop = FEATURE_COLUMNS.copy()
    featured = featured.dropna(subset=feature_columns_for_drop + [target_col]).reset_index(drop=True)

    return featured


def train_test_split_time_series(df: pd.DataFrame, test_horizon_hours: int = 24) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split chronologically; keep last N hours for testing/next-day forecast validation."""
    if len(df) <= test_horizon_hours:
        raise ValueError(
            f"Dataset has {len(df)} rows, but at least {test_horizon_hours + 1} are required for splitting."
        )

    train_df = df.iloc[:-test_horizon_hours].copy()
    test_df = df.iloc[-test_horizon_hours:].copy()
    return train_df, test_df


def _get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return mandatory features plus optional ones present in the dataset."""
    selected = FEATURE_COLUMNS.copy()
    for optional_col in OPTIONAL_FEATURE_COLUMNS:
        if optional_col in df.columns:
            selected.append(optional_col)
    for weather_col in WEATHER_OPTIONAL_COLUMNS:
        if weather_col in df.columns:
            selected.append(weather_col)
    return selected


def get_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    selected_features = _get_feature_columns(df)
    X = df[selected_features].copy()

    if "temperature" in X.columns:
        X["temperature"] = pd.to_numeric(X["temperature"], errors="coerce")
        temperature_median = X["temperature"].median()
        if pd.notna(temperature_median):
            X["temperature"] = X["temperature"].fillna(temperature_median)

    for col in WEATHER_OPTIONAL_COLUMNS:
        if col in X.columns:
            X[col] = pd.to_numeric(X[col], errors="coerce")
            median_value = X[col].median()
            if pd.notna(median_value):
                X[col] = X[col].fillna(median_value)

    target_col = "normalized_consumption" if "normalized_consumption" in df.columns else TARGET_COLUMN
    y = df[target_col].copy()
    return X, y
