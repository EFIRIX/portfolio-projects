from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import optuna
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from src.model import (
    LIGHTGBM_AVAILABLE,
    evaluate,
    recursive_forecast,
    train_lightgbm,
    train_linear_model,
    train_random_forest,
)


def _sample_for_tuning(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    max_samples: int = 8000,
) -> tuple[pd.DataFrame, pd.Series]:
    if len(X_train) <= max_samples:
        return X_train, y_train

    sampled_idx = X_train.sample(n=max_samples, random_state=42).index
    return X_train.loc[sampled_idx], y_train.loc[sampled_idx]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_mw(pred_normalized: pd.Series, region_peaks: pd.Series) -> pd.Series:
    normalized = pd.to_numeric(pred_normalized, errors="coerce").reset_index(drop=True)
    peaks = pd.to_numeric(region_peaks, errors="coerce").reset_index(drop=True)
    peaks = peaks.fillna(peaks.max() if not peaks.empty else 1.0)
    peaks = peaks.replace(0, peaks.max() if not peaks.empty else 1.0)
    if peaks.empty:
        peaks = pd.Series(np.ones(len(normalized)))
    return normalized * peaks


def _score_model(
    model: Any,
    history_df: pd.DataFrame,
    horizon: int,
    feature_columns: list[str],
    target_column: str,
    region_peaks_test: pd.Series,
    y_test_mw: pd.Series,
) -> tuple[pd.Series, dict[str, float]]:
    y_pred_normalized = recursive_forecast(
        model=model,
        history_df=history_df,
        horizon=horizon,
        feature_columns=feature_columns,
        target_column=target_column,
    ).reset_index(drop=True)

    y_pred_mw = _to_mw(y_pred_normalized, region_peaks_test)
    metrics = evaluate(y_test_mw.reset_index(drop=True), y_pred_mw)
    return y_pred_mw, metrics


def tune_random_forest(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    history_df: pd.DataFrame,
    y_test_mw: pd.Series,
    region_peaks_test: pd.Series,
    feature_columns: list[str],
    target_column: str,
    horizon: int,
    n_trials: int = 30,
) -> dict[str, Any]:
    X_tune, y_tune = _sample_for_tuning(X_train, y_train, max_samples=7000)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 40, 160),
            "max_depth": trial.suggest_int("max_depth", 4, 20),
            "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
            "random_state": 42,
            "n_jobs": -1,
        }
        model = RandomForestRegressor(**params)
        model.fit(X_tune, y_tune)
        _, metrics = _score_model(
            model=model,
            history_df=history_df,
            horizon=horizon,
            feature_columns=feature_columns,
            target_column=target_column,
            region_peaks_test=region_peaks_test,
            y_test_mw=y_test_mw,
        )
        return float(metrics["mae"])

    sampler = optuna.samplers.TPESampler(seed=42)
    study = optuna.create_study(direction="minimize", sampler=sampler)
    study.optimize(objective, n_trials=max(1, int(n_trials)), show_progress_bar=False)

    best = study.best_params
    best["random_state"] = 42
    best["n_jobs"] = -1
    return best


def tune_lightgbm(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    history_df: pd.DataFrame,
    y_test_mw: pd.Series,
    region_peaks_test: pd.Series,
    feature_columns: list[str],
    target_column: str,
    horizon: int,
    n_trials: int = 30,
) -> dict[str, Any]:
    X_tune, y_tune = _sample_for_tuning(X_train, y_train, max_samples=9000)

    def objective(trial: optuna.Trial) -> float:
        if LIGHTGBM_AVAILABLE:
            params = {
                "num_leaves": trial.suggest_int("num_leaves", 16, 256),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                "n_estimators": trial.suggest_int("n_estimators", 60, 260),
                "max_depth": trial.suggest_int("max_depth", -1, 16),
                "random_state": 42,
                "verbosity": -1,
            }
        else:
            # Fallback search space for HistGradientBoostingRegressor.
            params = {
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                "n_estimators": trial.suggest_int("n_estimators", 60, 260),
                "max_depth": trial.suggest_int("max_depth", 3, 16),
            }

        model = train_lightgbm(X_tune, y_tune, params=params)
        _, metrics = _score_model(
            model=model,
            history_df=history_df,
            horizon=horizon,
            feature_columns=feature_columns,
            target_column=target_column,
            region_peaks_test=region_peaks_test,
            y_test_mw=y_test_mw,
        )
        return float(metrics["mae"])

    sampler = optuna.samplers.TPESampler(seed=42)
    study = optuna.create_study(direction="minimize", sampler=sampler)
    study.optimize(objective, n_trials=max(1, int(n_trials)), show_progress_bar=False)

    best = study.best_params
    best["random_state"] = 42
    best["verbosity"] = -1
    return best


def append_model_registry(
    registry_path: str | Path,
    model_name: str,
    mae: float,
    rmse: float,
    dataset_mode: str,
    training_dataset_size: int | None = None,
    training_dataset_count: int | None = None,
    dataset_quality_score: float | None = None,
    ensemble_enabled: bool | None = None,
    ensemble_method: str | None = None,
    base_models: list[str] | None = None,
    ensemble_mae: float | None = None,
    automl_enabled: bool | None = None,
    automl_trials: int | None = None,
    best_trial_params: dict[str, Any] | None = None,
) -> None:
    path = Path(registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []
    else:
        existing = []

    existing.append(
        {
            "model_name": model_name,
            "MAE": float(mae),
            "RMSE": float(rmse),
            "training_dataset_size": int(training_dataset_size) if training_dataset_size is not None else None,
            "training_dataset_count": int(training_dataset_count) if training_dataset_count is not None else None,
            "dataset_quality_score": float(dataset_quality_score) if dataset_quality_score is not None else None,
            "ensemble_enabled": bool(ensemble_enabled) if ensemble_enabled is not None else None,
            "ensemble_method": str(ensemble_method) if ensemble_method is not None else None,
            "base_models": list(base_models) if base_models is not None else None,
            "ensemble_mae": float(ensemble_mae) if ensemble_mae is not None else None,
            "automl_enabled": bool(automl_enabled) if automl_enabled is not None else None,
            "automl_trials": int(automl_trials) if automl_trials is not None else None,
            "best_trial_params": dict(best_trial_params) if best_trial_params is not None else None,
            "timestamp": _utc_now_iso(),
            "dataset_mode": dataset_mode,
        }
    )

    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_loaded_model_compatible(model: Any, feature_columns: list[str]) -> bool:
    expected_count = len(feature_columns)

    model_feature_count = getattr(model, "n_features_in_", None)
    if model_feature_count is not None and int(model_feature_count) != expected_count:
        return False

    model_feature_names = getattr(model, "feature_names_in_", None)
    if model_feature_names is not None:
        return list(model_feature_names) == list(feature_columns)

    return True


def load_best_model(
    best_model_path: str | Path,
    feature_columns: list[str],
    dataset_mode: str,
) -> dict[str, Any] | None:
    path = Path(best_model_path)
    if not path.exists():
        return None

    try:
        payload = joblib.load(path)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    model = payload.get("model")
    if model is None:
        return None

    payload_features = payload.get("feature_columns")
    if isinstance(payload_features, list) and payload_features != list(feature_columns):
        return None

    payload_mode = payload.get("dataset_mode")
    if payload_mode is not None and str(payload_mode) != str(dataset_mode):
        return None

    if not _is_loaded_model_compatible(model, feature_columns):
        return None

    return payload


def save_best_model(
    best_model_path: str | Path,
    model: Any,
    model_name: str,
    feature_columns: list[str],
    dataset_mode: str,
    mae: float,
    rmse: float,
    ensemble_enabled: bool | None = None,
    ensemble_method: str | None = None,
    base_models: list[str] | None = None,
    ensemble_mae: float | None = None,
    automl_enabled: bool | None = None,
    automl_trials: int | None = None,
    best_trial_params: dict[str, Any] | None = None,
    automl_best_mae: float | None = None,
    automl_best_model: str | None = None,
) -> None:
    path = Path(best_model_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "model": model,
        "model_name": model_name,
        "feature_columns": list(feature_columns),
        "dataset_mode": dataset_mode,
        "mae": float(mae),
        "rmse": float(rmse),
        "ensemble_enabled": bool(ensemble_enabled) if ensemble_enabled is not None else None,
        "ensemble_method": str(ensemble_method) if ensemble_method is not None else None,
        "base_models": list(base_models) if base_models is not None else None,
        "ensemble_mae": float(ensemble_mae) if ensemble_mae is not None else None,
        "automl_enabled": bool(automl_enabled) if automl_enabled is not None else None,
        "automl_trials": int(automl_trials) if automl_trials is not None else None,
        "best_trial_params": dict(best_trial_params) if best_trial_params is not None else None,
        "automl_best_mae": float(automl_best_mae) if automl_best_mae is not None else None,
        "automl_best_model": str(automl_best_model) if automl_best_model is not None else None,
        "saved_at": _utc_now_iso(),
    }
    joblib.dump(payload, path)


def train_automl_models(
    history_df: pd.DataFrame,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    y_test_mw: pd.Series,
    region_peaks_test: pd.Series,
    feature_columns: list[str],
    target_column: str,
    horizon: int,
    n_trials: int = 30,
    tune_models: bool = True,
) -> dict[str, Any]:
    effective_trials = max(1, int(n_trials))
    if tune_models and len(X_train) > 50000:
        effective_trials = min(effective_trials, 6)
    elif tune_models and len(X_train) > 20000:
        effective_trials = min(effective_trials, 10)

    models: dict[str, Any] = {}
    predictions_mw: dict[str, pd.Series] = {}
    metrics: dict[str, dict[str, float]] = {}

    linear_model = train_linear_model(X_train, y_train)
    linear_pred, linear_metrics = _score_model(
        model=linear_model,
        history_df=history_df,
        horizon=horizon,
        feature_columns=feature_columns,
        target_column=target_column,
        region_peaks_test=region_peaks_test,
        y_test_mw=y_test_mw,
    )
    models["LinearRegression"] = linear_model
    predictions_mw["LinearRegression"] = linear_pred
    metrics["LinearRegression"] = linear_metrics

    rf_params: dict[str, Any] | None = None
    if tune_models:
        rf_params = tune_random_forest(
            X_train=X_train,
            y_train=y_train,
            history_df=history_df,
            y_test_mw=y_test_mw,
            region_peaks_test=region_peaks_test,
            feature_columns=feature_columns,
            target_column=target_column,
            horizon=horizon,
            n_trials=effective_trials,
        )

    if rf_params:
        rf_model = RandomForestRegressor(**rf_params)
        rf_model.fit(X_train, y_train)
    else:
        rf_model = RandomForestRegressor(n_estimators=120, random_state=42, n_jobs=-1)
        rf_model.fit(X_train, y_train)

    rf_pred, rf_metrics = _score_model(
        model=rf_model,
        history_df=history_df,
        horizon=horizon,
        feature_columns=feature_columns,
        target_column=target_column,
        region_peaks_test=region_peaks_test,
        y_test_mw=y_test_mw,
    )
    models["RandomForest"] = rf_model
    predictions_mw["RandomForest"] = rf_pred
    metrics["RandomForest"] = rf_metrics

    lgbm_params: dict[str, Any] | None = None
    if tune_models:
        lgbm_params = tune_lightgbm(
            X_train=X_train,
            y_train=y_train,
            history_df=history_df,
            y_test_mw=y_test_mw,
            region_peaks_test=region_peaks_test,
            feature_columns=feature_columns,
            target_column=target_column,
            horizon=horizon,
            n_trials=effective_trials,
        )

    lgbm_model = train_lightgbm(X_train, y_train, params=lgbm_params)
    lgbm_pred, lgbm_metrics = _score_model(
        model=lgbm_model,
        history_df=history_df,
        horizon=horizon,
        feature_columns=feature_columns,
        target_column=target_column,
        region_peaks_test=region_peaks_test,
        y_test_mw=y_test_mw,
    )
    models["LightGBM"] = lgbm_model
    predictions_mw["LightGBM"] = lgbm_pred
    metrics["LightGBM"] = lgbm_metrics

    best_model_name = min(metrics.keys(), key=lambda name: metrics[name]["mae"])

    return {
        "models": models,
        "predictions_mw": predictions_mw,
        "metrics": metrics,
        "best_model_name": best_model_name,
        "best_model": models[best_model_name],
        "best_metrics": metrics[best_model_name],
    }
