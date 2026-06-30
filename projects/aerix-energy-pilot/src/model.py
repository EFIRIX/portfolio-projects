from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error

try:
    from lightgbm import LGBMRegressor

    LIGHTGBM_AVAILABLE = True
except Exception:
    LGBMRegressor = None  # type: ignore[assignment]
    LIGHTGBM_AVAILABLE = False


def train_linear_model(X_train: pd.DataFrame, y_train: pd.Series) -> LinearRegression:
    """Train and return a Linear Regression model."""
    model = LinearRegression()
    model.fit(X_train, y_train)
    return model


def train_random_forest(X_train: pd.DataFrame, y_train: pd.Series) -> RandomForestRegressor:
    """Train and return a Random Forest regressor."""
    model = RandomForestRegressor(n_estimators=160, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    return model


def train_lightgbm(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    params: dict[str, Any] | None = None,
) -> Any:
    """Train and return a LightGBM regressor."""
    if LIGHTGBM_AVAILABLE and LGBMRegressor is not None:
        base_params: dict[str, Any] = {
            "random_state": 42,
            "verbosity": -1,
        }
        if params:
            base_params.update(params)

        model = LGBMRegressor(**base_params)
        model.fit(X_train, y_train)
        return model

    # Fallback for environments without LightGBM runtime (e.g., missing libomp).
    fallback_params: dict[str, Any] = {
        "random_state": 42,
        "max_iter": 250,
        "learning_rate": 0.05,
    }
    if params:
        if "n_estimators" in params:
            fallback_params["max_iter"] = int(params["n_estimators"])
        if "learning_rate" in params:
            fallback_params["learning_rate"] = float(params["learning_rate"])
        if "max_depth" in params:
            max_depth = int(params["max_depth"])
            fallback_params["max_depth"] = None if max_depth <= 0 else max_depth

    model = HistGradientBoostingRegressor(**fallback_params)
    model.fit(X_train, y_train)
    return model


def predict(model: Any, X_test: pd.DataFrame) -> np.ndarray:
    """Generate predictions for the provided feature matrix."""
    return model.predict(X_test)


def _safe_lag(values: list[float], lag: int) -> float:
    if not values:
        raise ValueError("History is empty; cannot build lag features.")
    if len(values) >= lag:
        return float(values[-lag])
    return float(values[0])


def _safe_rolling_mean(values: list[float], window: int) -> float:
    if not values:
        raise ValueError("History is empty; cannot build rolling features.")
    window_values = values[-window:] if len(values) >= window else values
    return float(np.mean(window_values))


def _build_recursive_feature_row(
    timestamp: pd.Timestamp,
    history_values: list[float],
    feature_columns: list[str],
    last_temperature: float | None,
) -> pd.DataFrame:
    row: dict[str, float | int] = {}

    hour = int(timestamp.hour)
    day_of_week = int(timestamp.dayofweek)

    if "hour" in feature_columns:
        row["hour"] = hour
    if "day_of_week" in feature_columns:
        row["day_of_week"] = day_of_week
    if "hour_sin" in feature_columns:
        row["hour_sin"] = float(np.sin(2 * np.pi * hour / 24.0))
    if "hour_cos" in feature_columns:
        row["hour_cos"] = float(np.cos(2 * np.pi * hour / 24.0))
    if "day_of_week_sin" in feature_columns:
        row["day_of_week_sin"] = float(np.sin(2 * np.pi * day_of_week / 7.0))
    if "day_of_week_cos" in feature_columns:
        row["day_of_week_cos"] = float(np.cos(2 * np.pi * day_of_week / 7.0))
    if "month" in feature_columns:
        row["month"] = int(timestamp.month)
    if "dayofyear" in feature_columns:
        row["dayofyear"] = int(timestamp.dayofyear)
    if "weekofyear" in feature_columns:
        row["weekofyear"] = int(timestamp.isocalendar().week)

    if "lag_1" in feature_columns:
        row["lag_1"] = _safe_lag(history_values, 1)
    if "lag_24" in feature_columns:
        row["lag_24"] = _safe_lag(history_values, 24)
    if "lag_168" in feature_columns:
        row["lag_168"] = _safe_lag(history_values, 168)

    if "rolling_24" in feature_columns:
        row["rolling_24"] = _safe_rolling_mean(history_values, 24)
    if "rolling_168" in feature_columns:
        row["rolling_168"] = _safe_rolling_mean(history_values, 168)

    if "temperature" in feature_columns:
        row["temperature"] = float(last_temperature) if last_temperature is not None else 0.0

    return pd.DataFrame([[row.get(col, 0.0) for col in feature_columns]], columns=feature_columns)


def recursive_forecast(
    model: Any,
    history_df: pd.DataFrame,
    horizon: int,
    feature_columns: list[str],
    target_column: str = "consumption",
) -> pd.Series:
    """
    Multi-step recursive forecast.

    For each future step:
    - builds lag/rolling features from known history + previous predictions
    - predicts next hour
    - appends prediction back to history
    """
    if horizon <= 0:
        return pd.Series(dtype=float, name="predicted_consumption")

    history = history_df.copy().sort_values("timestamp")
    history["timestamp"] = pd.to_datetime(history["timestamp"], errors="coerce")
    if target_column not in history.columns:
        raise ValueError(f"history_df must contain target column '{target_column}'.")

    history[target_column] = pd.to_numeric(history[target_column], errors="coerce")
    history = history.dropna(subset=["timestamp", target_column])
    if history.empty:
        raise ValueError(f"history_df must contain valid timestamp and '{target_column}' values.")

    history_values = history[target_column].astype(float).tolist()
    current_timestamp = pd.Timestamp(history["timestamp"].iloc[-1])

    last_temperature: float | None = None
    if "temperature" in feature_columns:
        if "temperature" in history.columns:
            temp_series = pd.to_numeric(history["temperature"], errors="coerce").dropna()
            last_temperature = float(temp_series.iloc[-1]) if not temp_series.empty else 0.0
        else:
            last_temperature = 0.0

    future_timestamps: list[pd.Timestamp] = []
    predictions: list[float] = []

    for _ in range(horizon):
        next_timestamp = current_timestamp + pd.Timedelta(hours=1)
        x_next = _build_recursive_feature_row(
            timestamp=next_timestamp,
            history_values=history_values,
            feature_columns=feature_columns,
            last_temperature=last_temperature,
        )

        next_prediction = float(model.predict(x_next)[0])
        predictions.append(next_prediction)
        future_timestamps.append(next_timestamp)

        history_values.append(next_prediction)
        current_timestamp = next_timestamp

    return pd.Series(predictions, index=pd.to_datetime(future_timestamps), name="predicted_consumption")


def evaluate(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    """Return MAE and RMSE metrics."""
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    return {"mae": float(mae), "rmse": rmse}


def save_model(model: Any, model_path: str | Path) -> None:
    """Persist a model artifact with joblib."""
    path = Path(model_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)


def load_model(model_path: str | Path) -> Any:
    """Load a model artifact with joblib."""
    return joblib.load(Path(model_path))


def _is_model_compatible_with_features(model: Any, X_train: pd.DataFrame) -> bool:
    """Check whether loaded model can be used with current feature set."""
    expected_count = X_train.shape[1]

    model_feature_count = getattr(model, "n_features_in_", None)
    if model_feature_count is not None and int(model_feature_count) != expected_count:
        return False

    model_feature_names = getattr(model, "feature_names_in_", None)
    if model_feature_names is not None:
        return list(model_feature_names) == list(X_train.columns)

    return True


def load_or_train_rf(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    model_path: str | Path,
) -> tuple[Any, bool]:
    """
    Load Random Forest model if model_path exists; otherwise train and save it.

    Returns:
    - model
    - loaded_from_disk flag
    """
    path = Path(model_path)
    if path.exists():
        loaded_model = joblib.load(path)
        if _is_model_compatible_with_features(loaded_model, X_train):
            return loaded_model, True

    model = train_random_forest(X_train, y_train)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    return model, False


# Backward-compatible wrappers to avoid breaking existing pipeline code paths.
def train_regression_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    model_type: str = "random_forest",
):
    """Train a regression model (Random Forest or Linear Regression)."""
    if model_type == "linear":
        return train_linear_model(X_train, y_train)
    return train_random_forest(X_train, y_train)


def load_or_train_random_forest(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    model_path: str | Path,
):
    return load_or_train_rf(X_train, y_train, model_path)


def predict_consumption(model: Any, X: pd.DataFrame) -> np.ndarray:
    return predict(model, X)


def evaluate_forecast(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    return evaluate(y_true, y_pred)
