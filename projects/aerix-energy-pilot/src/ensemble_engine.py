from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.model import evaluate, train_lightgbm, train_linear_model, train_random_forest


BASE_MODEL_ORDER = ["LinearRegression", "RandomForest", "LightGBM"]


def _ordered_model_names(names: list[str]) -> list[str]:
    order_map = {name: idx for idx, name in enumerate(BASE_MODEL_ORDER)}
    return sorted(names, key=lambda name: (order_map.get(name, 999), name))


def _to_series(value: pd.Series | np.ndarray | list[float]) -> pd.Series:
    if isinstance(value, pd.Series):
        return pd.to_numeric(value, errors="coerce").reset_index(drop=True)
    return pd.Series(pd.to_numeric(pd.Series(value), errors="coerce")).reset_index(drop=True)


def _infer_target_column(train_df: pd.DataFrame) -> str:
    if "normalized_consumption" in train_df.columns:
        return "normalized_consumption"
    if "consumption" in train_df.columns:
        return "consumption"
    numeric_cols = [
        col for col in train_df.columns if pd.to_numeric(train_df[col], errors="coerce").notna().any()
    ]
    if not numeric_cols:
        raise ValueError("train_df does not contain numeric target candidates.")
    return str(numeric_cols[-1])


def _infer_feature_columns(train_df: pd.DataFrame, target_column: str) -> list[str]:
    excluded = {target_column, "timestamp", "Datetime"}
    feature_candidates = [col for col in train_df.columns if col not in excluded]
    numeric_features = [
        col
        for col in feature_candidates
        if pd.to_numeric(train_df[col], errors="coerce").notna().any()
    ]
    if not numeric_features:
        raise ValueError("No numeric feature columns found for ensemble base models.")
    return [str(col) for col in numeric_features]


@dataclass
class EnsembleForecaster:
    models: dict[str, Any]
    method: str = "weighted"
    weights: dict[str, float] | None = None
    base_models: list[str] | None = None

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        model_names = self.base_models or _ordered_model_names(list(self.models.keys()))
        model_map = {name: self.models[name] for name in model_names if name in self.models}
        predictions = predict_with_models(model_map, X)
        combined = combine_predictions(
            predictions=predictions,
            method=self.method,
            weights=self.weights,
        )
        return combined.to_numpy(dtype=float)


def train_base_models(train_df: pd.DataFrame) -> dict[str, Any]:
    if train_df is None or not isinstance(train_df, pd.DataFrame) or train_df.empty:
        raise ValueError("train_df is empty.")

    target_column = _infer_target_column(train_df)
    feature_columns = _infer_feature_columns(train_df, target_column)

    X_train = train_df[feature_columns].apply(pd.to_numeric, errors="coerce")
    y_train = pd.to_numeric(train_df[target_column], errors="coerce")

    valid_mask = y_train.notna()
    for col in feature_columns:
        valid_mask &= X_train[col].notna()

    X_train = X_train.loc[valid_mask].reset_index(drop=True)
    y_train = y_train.loc[valid_mask].reset_index(drop=True)

    if X_train.empty or y_train.empty:
        raise ValueError("No valid rows for base model training.")

    models: dict[str, Any] = {
        "LinearRegression": train_linear_model(X_train, y_train),
        "RandomForest": train_random_forest(X_train, y_train),
        "LightGBM": train_lightgbm(X_train, y_train),
    }
    return {
        "models": models,
        "feature_columns": feature_columns,
        "target_column": target_column,
    }


def predict_with_models(models: dict[str, Any], X: pd.DataFrame) -> dict[str, pd.Series]:
    if not models:
        return {}

    model_names = _ordered_model_names([str(name) for name in models.keys()])
    predictions: dict[str, pd.Series] = {}
    for name in model_names:
        model = models.get(name)
        if model is None:
            continue
        raw_pred = model.predict(X)
        predictions[name] = _to_series(raw_pred)
    return predictions


def combine_predictions(
    predictions: dict[str, pd.Series | np.ndarray | list[float]],
    method: str = "mean",
    weights: dict[str, float] | None = None,
) -> pd.Series:
    if not predictions:
        return pd.Series(dtype=float)

    ordered_names = _ordered_model_names([str(name) for name in predictions.keys()])
    frames: dict[str, pd.Series] = {name: _to_series(predictions[name]) for name in ordered_names}
    matrix = pd.concat([frames[name] for name in ordered_names], axis=1)
    matrix.columns = ordered_names
    matrix = matrix.apply(pd.to_numeric, errors="coerce")

    if method == "weighted":
        weights = weights or {}
        raw_weights = np.array([float(weights.get(name, 0.0)) for name in ordered_names], dtype=float)
        if np.sum(raw_weights) <= 0:
            combined = matrix.mean(axis=1)
        else:
            normalized = raw_weights / np.sum(raw_weights)
            combined = pd.Series(matrix.to_numpy(dtype=float).dot(normalized), index=matrix.index)
        return combined.reset_index(drop=True)

    # Default strategy is mean ensemble.
    return matrix.mean(axis=1).reset_index(drop=True)


def evaluate_ensemble(y_true: pd.Series, predictions: pd.Series | np.ndarray | list[float]) -> dict[str, float]:
    y_true_series = _to_series(y_true)
    pred_series = _to_series(predictions)
    return evaluate(y_true_series, pred_series.to_numpy(dtype=float))


def compute_inverse_mae_weights(base_metrics: dict[str, dict[str, float]]) -> dict[str, float]:
    model_names = _ordered_model_names(list(base_metrics.keys()))
    raw: dict[str, float] = {}
    for name in model_names:
        mae = float(base_metrics.get(name, {}).get("mae", np.inf))
        raw[name] = 1.0 / (mae + 1e-9)

    total = float(sum(raw.values()))
    if total <= 0:
        uniform = 1.0 / max(1, len(model_names))
        return {name: uniform for name in model_names}
    return {name: float(raw[name] / total) for name in model_names}


def select_ensemble_method(
    y_true: pd.Series,
    predictions_mw: dict[str, pd.Series],
    base_metrics: dict[str, dict[str, float]],
) -> dict[str, Any]:
    weights = compute_inverse_mae_weights(base_metrics)

    mean_pred = combine_predictions(predictions_mw, method="mean")
    weighted_pred = combine_predictions(predictions_mw, method="weighted", weights=weights)

    mean_metrics = evaluate_ensemble(y_true, mean_pred)
    weighted_metrics = evaluate_ensemble(y_true, weighted_pred)

    candidates = {
        "mean": {"prediction": mean_pred, "metrics": mean_metrics},
        "weighted": {"prediction": weighted_pred, "metrics": weighted_metrics},
    }
    selected_method = min(
        candidates.keys(),
        key=lambda method: (candidates[method]["metrics"]["mae"], method),
    )

    return {
        "weights": weights,
        "method_metrics": {
            "mean": mean_metrics,
            "weighted": weighted_metrics,
        },
        "method_predictions": {
            "mean": mean_pred,
            "weighted": weighted_pred,
        },
        "selected_method": selected_method,
        "selected_prediction": candidates[selected_method]["prediction"],
        "selected_metrics": candidates[selected_method]["metrics"],
    }


def select_best_forecast_candidate(
    y_true: pd.Series,
    predictions_mw: dict[str, pd.Series],
    base_metrics: dict[str, dict[str, float]],
    base_models: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model_names = _ordered_model_names(list(base_metrics.keys()))
    base_best_name = min(model_names, key=lambda name: (base_metrics[name]["mae"], name))
    base_best_metrics = dict(base_metrics[base_best_name])
    base_best_prediction = _to_series(predictions_mw[base_best_name])

    ensemble = select_ensemble_method(
        y_true=y_true,
        predictions_mw=predictions_mw,
        base_metrics=base_metrics,
    )
    ensemble_metrics = dict(ensemble["selected_metrics"])
    ensemble_prediction = _to_series(ensemble["selected_prediction"])
    ensemble_method = str(ensemble["selected_method"])

    use_ensemble = bool(ensemble_metrics["mae"] < base_best_metrics["mae"])
    if use_ensemble:
        selected_source = "ensemble"
        selected_model_name = f"Ensemble({ensemble_method})"
        selected_prediction = ensemble_prediction
        selected_metrics = ensemble_metrics
        selected_model = None
        if base_models:
            selected_model = EnsembleForecaster(
                models={name: base_models[name] for name in model_names if name in base_models},
                method=ensemble_method,
                weights=ensemble["weights"],
                base_models=model_names,
            )
    else:
        selected_source = "base"
        selected_model_name = base_best_name
        selected_prediction = base_best_prediction
        selected_metrics = base_best_metrics
        selected_model = base_models.get(base_best_name) if base_models else None

    return {
        "base_models": model_names,
        "base_best_name": base_best_name,
        "base_best_prediction": base_best_prediction,
        "base_best_metrics": base_best_metrics,
        "ensemble_method": ensemble_method,
        "ensemble_weights": ensemble["weights"],
        "ensemble_method_metrics": ensemble["method_metrics"],
        "ensemble_method_predictions": ensemble["method_predictions"],
        "ensemble_selected_metrics": ensemble_metrics,
        "ensemble_selected_prediction": ensemble_prediction,
        "selected_source": selected_source,
        "selected_model_name": selected_model_name,
        "selected_prediction": selected_prediction,
        "selected_metrics": selected_metrics,
        "selected_model": selected_model,
    }

