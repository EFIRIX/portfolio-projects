from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

from src.ensemble_engine import combine_predictions
from src.model import evaluate, recursive_forecast, train_lightgbm

try:
    from xgboost import XGBRegressor  # type: ignore

    XGBOOST_AVAILABLE = True
except Exception:
    XGBRegressor = None  # type: ignore[assignment]
    XGBOOST_AVAILABLE = False

try:
    from catboost import CatBoostRegressor  # type: ignore

    CATBOOST_AVAILABLE = True
except Exception:
    CatBoostRegressor = None  # type: ignore[assignment]
    CATBOOST_AVAILABLE = False


class AutoMLEngine:
    """
    Deterministic AutoML search over model type/hyperparameters + ensemble usage.
    """

    def __init__(
        self,
        *,
        history_df: pd.DataFrame,
        feature_columns: list[str],
        target_column: str,
        horizon: int,
        y_true_mw: pd.Series,
        region_peaks_test: pd.Series,
        dataset_mode: str = "grid",
        max_trials: int = 30,
        output_path: str | Path = Path("outputs") / "automl_trials.json",
        top_k_models: int = 5,
    ) -> None:
        self.history_df = history_df.copy()
        self.feature_columns = list(feature_columns)
        self.target_column = str(target_column)
        self.horizon = int(max(1, horizon))
        self.y_true_mw = pd.to_numeric(y_true_mw, errors="coerce").reset_index(drop=True)
        self.region_peaks_test = pd.to_numeric(region_peaks_test, errors="coerce").reset_index(drop=True)
        self.dataset_mode = str(dataset_mode)
        self.max_trials = int(max(1, max_trials))
        self.output_path = Path(output_path)
        self.top_k_models = int(max(1, top_k_models))

        self.candidates: list[dict[str, Any]] = []
        self.trials: list[dict[str, Any]] = []
        self._candidate_models: dict[str, Any] = {}
        self._candidate_predictions_mw: dict[str, pd.Series] = {}
        self._candidate_metrics: dict[str, dict[str, float]] = {}
        self._train_df = pd.DataFrame()

    def run_search(self, train_df: pd.DataFrame) -> dict[str, Any]:
        self._train_df = train_df.copy()
        self.generate_candidates()
        self.evaluate_candidates()
        best_trial = self.select_best_model()

        payload = {
            "automl_enabled": True,
            "dataset_mode": self.dataset_mode,
            "max_trials": self.max_trials,
            "trial_count": len(self.trials),
            "evaluated_trials": int(sum(1 for trial in self.trials if trial.get("status") == "evaluated")),
            "best_trial": self._json_safe(best_trial),
            "trials": self._json_safe(self.trials),
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        top_pool = self._build_top_candidate_pool()
        return {
            "best_trial": best_trial,
            "trials": self.trials,
            "trial_count": len(self.trials),
            "evaluated_trials": int(sum(1 for trial in self.trials if trial.get("status") == "evaluated")),
            "output_path": str(self.output_path),
            "candidate_pool": top_pool,
        }

    def generate_candidates(self) -> list[dict[str, Any]]:
        generated: list[dict[str, Any]] = []

        # LinearRegression
        for fit_intercept in [True, False]:
            generated.append(
                self._candidate_dict(
                    model_name="LinearRegression",
                    hyperparameters={"fit_intercept": fit_intercept},
                )
            )

        # RandomForest
        for n_estimators, max_depth in itertools.product([100, 200, 400], [5, 10, 20]):
            generated.append(
                self._candidate_dict(
                    model_name="RandomForest",
                    hyperparameters={
                        "n_estimators": int(n_estimators),
                        "max_depth": int(max_depth),
                        "random_state": 42,
                        "n_jobs": -1,
                    },
                )
            )

        # LightGBM
        for num_leaves, learning_rate in itertools.product([31, 64, 128], [0.01, 0.05, 0.1]):
            generated.append(
                self._candidate_dict(
                    model_name="LightGBM",
                    hyperparameters={
                        "num_leaves": int(num_leaves),
                        "learning_rate": float(learning_rate),
                        "random_state": 42,
                        "verbosity": -1,
                    },
                )
            )

        # Optional XGBoost
        if XGBOOST_AVAILABLE and XGBRegressor is not None:
            generated.append(
                self._candidate_dict(
                    model_name="XGBoost",
                    hyperparameters={
                        "n_estimators": 200,
                        "max_depth": 6,
                        "learning_rate": 0.05,
                        "random_state": 42,
                        "n_jobs": -1,
                        "verbosity": 0,
                    },
                )
            )
        else:
            generated.append(
                self._candidate_dict(
                    model_name="XGBoost",
                    hyperparameters={},
                    status="skipped_optional_dependency",
                )
            )

        # Optional CatBoost
        if CATBOOST_AVAILABLE and CatBoostRegressor is not None:
            generated.append(
                self._candidate_dict(
                    model_name="CatBoost",
                    hyperparameters={
                        "iterations": 300,
                        "depth": 6,
                        "learning_rate": 0.05,
                        "random_seed": 42,
                        "verbose": False,
                    },
                )
            )
        else:
            generated.append(
                self._candidate_dict(
                    model_name="CatBoost",
                    hyperparameters={},
                    status="skipped_optional_dependency",
                )
            )

        generated = generated[: self.max_trials]

        for idx, candidate in enumerate(generated, start=1):
            candidate["iteration"] = idx

        self.candidates = generated
        return generated

    def evaluate_candidates(self) -> list[dict[str, Any]]:
        if self._train_df.empty:
            raise ValueError("train_df is empty. Call run_search(train_df) with valid training data.")

        X_train, y_train = self._prepare_xy(self._train_df)
        trials: list[dict[str, Any]] = []

        for candidate in self.candidates:
            model_name = str(candidate["model_name"])
            candidate_id = str(candidate["candidate_id"])
            status = str(candidate.get("status", "ready"))

            trial_record: dict[str, Any] = {
                "candidate_id": candidate_id,
                "iteration": int(candidate.get("iteration", 0)),
                "model_name": model_name,
                "hyperparameters": dict(candidate.get("hyperparameters", {})),
                "ensemble_enabled": bool(candidate.get("ensemble_enabled", False)),
                "dataset_mode": self.dataset_mode,
                "status": status,
                "validation_mae": None,
                "validation_rmse": None,
            }

            if status == "skipped_optional_dependency":
                trials.append(trial_record)
                continue

            params = dict(candidate.get("hyperparameters", {}))
            if model_name == "LightGBM":
                model = train_lightgbm(X_train, y_train, params=params)
            else:
                model = self._build_model(model_name, params)
                model.fit(X_train, y_train)

            pred_mw = self._forecast_in_mw(model)
            metrics = evaluate(self.y_true_mw, pred_mw)

            trial_record["status"] = "evaluated"
            trial_record["validation_mae"] = float(metrics["mae"])
            trial_record["validation_rmse"] = float(metrics["rmse"])
            trials.append(trial_record)

            model_key = f"AutoML::{candidate_id}"
            self._candidate_models[model_key] = model
            self._candidate_predictions_mw[model_key] = pred_mw.reset_index(drop=True)
            self._candidate_metrics[model_key] = {
                "mae": float(metrics["mae"]),
                "rmse": float(metrics["rmse"]),
            }

        self.trials = trials
        self._append_ensemble_trials()
        return self.trials

    def select_best_model(self) -> dict[str, Any] | None:
        valid_trials = [
            trial
            for trial in self.trials
            if trial.get("status") == "evaluated"
            and trial.get("validation_mae") is not None
            and trial.get("validation_rmse") is not None
        ]
        if not valid_trials:
            return None

        return min(
            valid_trials,
            key=lambda trial: (
                float(trial["validation_mae"]),
                float(trial["validation_rmse"]),
                str(trial["candidate_id"]),
            ),
        )

    def _candidate_dict(
        self,
        *,
        model_name: str,
        hyperparameters: dict[str, Any],
        status: str = "ready",
        ensemble_enabled: bool = False,
    ) -> dict[str, Any]:
        param_repr = ";".join(f"{key}={hyperparameters[key]}" for key in sorted(hyperparameters.keys()))
        candidate_id = f"{model_name}::{param_repr}" if param_repr else f"{model_name}::default"
        return {
            "candidate_id": candidate_id,
            "model_name": model_name,
            "hyperparameters": hyperparameters,
            "status": status,
            "ensemble_enabled": bool(ensemble_enabled),
        }

    def _prepare_xy(self, train_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        if self.target_column not in train_df.columns:
            raise ValueError(f"Missing target column '{self.target_column}' in train_df.")

        X_train = train_df[self.feature_columns].apply(pd.to_numeric, errors="coerce")
        y_train = pd.to_numeric(train_df[self.target_column], errors="coerce")

        valid_mask = y_train.notna()
        for col in self.feature_columns:
            valid_mask &= X_train[col].notna()

        X_train = X_train.loc[valid_mask].reset_index(drop=True)
        y_train = y_train.loc[valid_mask].reset_index(drop=True)
        if X_train.empty or y_train.empty:
            raise ValueError("No valid train rows after numeric coercion in AutoML search.")
        return X_train, y_train

    def _build_model(self, model_name: str, params: dict[str, Any]) -> Any:
        if model_name == "LinearRegression":
            return LinearRegression(fit_intercept=bool(params.get("fit_intercept", True)))

        if model_name == "RandomForest":
            return RandomForestRegressor(
                n_estimators=int(params.get("n_estimators", 200)),
                max_depth=int(params.get("max_depth", 10)),
                random_state=42,
                n_jobs=-1,
            )

        if model_name == "XGBoost":
            if not XGBOOST_AVAILABLE or XGBRegressor is None:
                raise RuntimeError("XGBoost dependency unavailable.")
            return XGBRegressor(**params)

        if model_name == "CatBoost":
            if not CATBOOST_AVAILABLE or CatBoostRegressor is None:
                raise RuntimeError("CatBoost dependency unavailable.")
            return CatBoostRegressor(**params)

        raise ValueError(f"Unsupported model name: {model_name}")

    def _forecast_in_mw(self, model: Any) -> pd.Series:
        pred_normalized = recursive_forecast(
            model=model,
            history_df=self.history_df,
            horizon=self.horizon,
            feature_columns=self.feature_columns,
            target_column=self.target_column,
        ).reset_index(drop=True)

        region_peaks = self.region_peaks_test.copy()
        fallback_peak = float(region_peaks.max()) if not region_peaks.empty else 1.0
        if not np.isfinite(fallback_peak) or fallback_peak <= 0:
            fallback_peak = 1.0
        region_peaks = region_peaks.fillna(fallback_peak)
        region_peaks.loc[region_peaks <= 0] = fallback_peak
        if len(region_peaks) != len(pred_normalized):
            region_peaks = pd.Series([fallback_peak] * len(pred_normalized))
        return pd.to_numeric(pred_normalized, errors="coerce").reset_index(drop=True) * region_peaks.reset_index(
            drop=True
        )

    def _append_ensemble_trials(self) -> None:
        successful = sorted(
            [
                trial
                for trial in self.trials
                if trial.get("status") == "evaluated"
                and not bool(trial.get("ensemble_enabled", False))
                and trial.get("validation_mae") is not None
            ],
            key=lambda trial: (
                float(trial["validation_mae"]),
                float(trial["validation_rmse"] or np.inf),
                str(trial["candidate_id"]),
            ),
        )
        if len(successful) < 2:
            return

        top_trials = successful[: min(self.top_k_models, len(successful))]
        prediction_map: dict[str, pd.Series] = {}
        metric_map: dict[str, dict[str, float]] = {}
        for trial in top_trials:
            key = f"AutoML::{trial['candidate_id']}"
            if key not in self._candidate_predictions_mw:
                continue
            prediction_map[key] = self._candidate_predictions_mw[key]
            metric_map[key] = {
                "mae": float(trial["validation_mae"]),
                "rmse": float(trial["validation_rmse"]),
            }
        if len(prediction_map) < 2:
            return

        base_models = sorted(prediction_map.keys())
        inverse = {
            name: 1.0 / (float(metric_map[name]["mae"]) + 1e-9)
            for name in base_models
        }
        weight_sum = float(sum(inverse.values()))
        if weight_sum <= 0:
            weighted = {name: 1.0 / len(base_models) for name in base_models}
        else:
            weighted = {name: float(inverse[name] / weight_sum) for name in base_models}

        mean_pred = combine_predictions(prediction_map, method="mean")
        weighted_pred = combine_predictions(prediction_map, method="weighted", weights=weighted)
        mean_metrics = evaluate(self.y_true_mw, mean_pred)
        weighted_metrics = evaluate(self.y_true_mw, weighted_pred)

        start_iteration = len(self.trials) + 1
        self.trials.extend(
            [
                {
                    "candidate_id": "Ensemble::mean",
                    "iteration": start_iteration,
                    "model_name": "Ensemble",
                    "hyperparameters": {"method": "mean", "base_models": base_models},
                    "ensemble_enabled": True,
                    "dataset_mode": self.dataset_mode,
                    "status": "evaluated",
                    "validation_mae": float(mean_metrics["mae"]),
                    "validation_rmse": float(mean_metrics["rmse"]),
                },
                {
                    "candidate_id": "Ensemble::weighted",
                    "iteration": start_iteration + 1,
                    "model_name": "Ensemble",
                    "hyperparameters": {
                        "method": "weighted",
                        "weights": weighted,
                        "base_models": base_models,
                    },
                    "ensemble_enabled": True,
                    "dataset_mode": self.dataset_mode,
                    "status": "evaluated",
                    "validation_mae": float(weighted_metrics["mae"]),
                    "validation_rmse": float(weighted_metrics["rmse"]),
                },
            ]
        )

    def _build_top_candidate_pool(self) -> dict[str, dict[str, Any]]:
        successful = sorted(
            self._candidate_metrics.items(),
            key=lambda item: (
                float(item[1]["mae"]),
                float(item[1]["rmse"]),
                str(item[0]),
            ),
        )
        top = successful[: self.top_k_models]

        models: dict[str, Any] = {}
        predictions_mw: dict[str, pd.Series] = {}
        metrics: dict[str, dict[str, float]] = {}

        for key, metric in top:
            model = self._candidate_models.get(key)
            prediction = self._candidate_predictions_mw.get(key)
            if model is None or prediction is None:
                continue
            models[key] = model
            predictions_mw[key] = prediction.reset_index(drop=True)
            metrics[key] = {"mae": float(metric["mae"]), "rmse": float(metric["rmse"])}

        return {
            "models": models,
            "predictions_mw": predictions_mw,
            "metrics": metrics,
        }

    def _json_safe(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {str(key): self._json_safe(value) for key, value in obj.items()}
        if isinstance(obj, list):
            return [self._json_safe(item) for item in obj]
        if isinstance(obj, tuple):
            return [self._json_safe(item) for item in obj]
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, Path):
            return str(obj)
        return obj
