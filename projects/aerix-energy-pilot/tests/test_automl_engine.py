from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

import main as aerix_main
from src.automl_engine import (
    CATBOOST_AVAILABLE,
    XGBOOST_AVAILABLE,
    AutoMLEngine,
)


def _make_history(rows: int = 72) -> pd.DataFrame:
    timestamps = pd.date_range("2025-01-01 00:00:00", periods=rows, freq="h")
    df = pd.DataFrame({"timestamp": timestamps})
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["month"] = df["timestamp"].dt.month

    # Smooth deterministic signal in normalized space.
    signal = 0.55 + 0.20 * np.sin(2 * np.pi * df["hour"] / 24.0)
    df["normalized_consumption"] = signal.astype(float)
    df["region_peak"] = 10_000.0
    return df


def _make_engine(output_path: Path, max_trials: int = 8) -> AutoMLEngine:
    history_df = _make_history(96)
    horizon = 6
    y_true_mw = pd.Series([5600.0, 5750.0, 5900.0, 6050.0, 6200.0, 6350.0])
    region_peaks_test = pd.Series([10_000.0] * horizon)

    return AutoMLEngine(
        history_df=history_df,
        feature_columns=["hour", "day_of_week", "month"],
        target_column="normalized_consumption",
        horizon=horizon,
        y_true_mw=y_true_mw,
        region_peaks_test=region_peaks_test,
        dataset_mode="grid",
        max_trials=max_trials,
        output_path=output_path,
        top_k_models=3,
    )


class DummyModel:
    def __init__(self, value: float) -> None:
        self.value = float(value)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.full(shape=len(X), fill_value=self.value, dtype=float)


def _modeling_bundle() -> dict:
    models = {
        "LinearRegression": DummyModel(12.0),
        "RandomForest": DummyModel(8.0),
        "LightGBM": DummyModel(10.0),
    }
    predictions = {
        "LinearRegression": pd.Series([12.0, 12.0, 12.0]),
        "RandomForest": pd.Series([8.0, 8.0, 8.0]),
        "LightGBM": pd.Series([10.0, 10.0, 10.0]),
    }
    metrics = {
        "LinearRegression": {"mae": 3.0, "rmse": 3.0},
        "RandomForest": {"mae": 1.0, "rmse": 1.0},
        "LightGBM": {"mae": 1.0, "rmse": 1.0},
    }
    return {
        "models": models,
        "predictions_mw": predictions,
        "metrics": metrics,
        "best_model_name": "RandomForest",
        "best_model": models["RandomForest"],
        "best_metrics": metrics["RandomForest"],
    }


class AutoMLEngineTests(unittest.TestCase):
    def test_generate_candidates_deterministic_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "automl_trials.json"
            engine_one = _make_engine(output_path=output_path, max_trials=30)
            engine_two = _make_engine(output_path=output_path, max_trials=30)

            c1 = engine_one.generate_candidates()
            c2 = engine_two.generate_candidates()

            ids1 = [str(candidate["candidate_id"]) for candidate in c1]
            ids2 = [str(candidate["candidate_id"]) for candidate in c2]
            self.assertEqual(ids1, ids2)
            self.assertLessEqual(len(ids1), 30)
            self.assertTrue(ids1[0].startswith("LinearRegression::"))

            xgb = [candidate for candidate in c1 if candidate["model_name"] == "XGBoost"]
            cat = [candidate for candidate in c1 if candidate["model_name"] == "CatBoost"]
            self.assertEqual(len(xgb), 1)
            self.assertEqual(len(cat), 1)

            xgb_status = str(xgb[0].get("status"))
            cat_status = str(cat[0].get("status"))
            if XGBOOST_AVAILABLE:
                self.assertEqual(xgb_status, "ready")
            else:
                self.assertEqual(xgb_status, "skipped_optional_dependency")
            if CATBOOST_AVAILABLE:
                self.assertEqual(cat_status, "ready")
            else:
                self.assertEqual(cat_status, "skipped_optional_dependency")

    def test_select_best_model_tie_break(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "automl_trials.json"
            engine = _make_engine(output_path=output_path, max_trials=4)

            engine.trials = [
                {
                    "candidate_id": "z_model",
                    "status": "evaluated",
                    "validation_mae": 1.0,
                    "validation_rmse": 2.0,
                },
                {
                    "candidate_id": "a_model",
                    "status": "evaluated",
                    "validation_mae": 1.0,
                    "validation_rmse": 2.0,
                },
            ]
            best = engine.select_best_model()
            self.assertIsNotNone(best)
            self.assertEqual(best["candidate_id"], "a_model")

    def test_run_search_persists_trials_and_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "automl_trials.json"

            engine_one = _make_engine(output_path=output_path, max_trials=6)
            result_one = engine_one.run_search(train_df=_make_history(96))

            self.assertTrue(output_path.exists())
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertIn("trials", payload)
            self.assertIn("best_trial", payload)
            self.assertIn("trial_count", payload)

            trials = payload.get("trials", [])
            self.assertTrue(isinstance(trials, list) and len(trials) > 0)
            required_fields = {
                "model_name",
                "hyperparameters",
                "validation_mae",
                "validation_rmse",
                "ensemble_enabled",
                "iteration",
                "dataset_mode",
                "status",
            }
            first_trial = trials[0]
            self.assertTrue(required_fields.issubset(set(first_trial.keys())))

            engine_two = _make_engine(output_path=output_path, max_trials=6)
            result_two = engine_two.run_search(train_df=_make_history(96))

            self.assertEqual(result_one["trial_count"], result_two["trial_count"])
            best_one = result_one["best_trial"] or {}
            best_two = result_two["best_trial"] or {}
            self.assertEqual(best_one.get("candidate_id"), best_two.get("candidate_id"))

            eval_one = [t for t in result_one["trials"] if t.get("status") == "evaluated"]
            eval_two = [t for t in result_two["trials"] if t.get("status") == "evaluated"]
            mae_one = [round(float(t["validation_mae"]), 10) for t in eval_one if t.get("validation_mae") is not None]
            mae_two = [round(float(t["validation_mae"]), 10) for t in eval_two if t.get("validation_mae") is not None]
            self.assertEqual(mae_one, mae_two)

    def test_run_modeling_does_not_call_automl_engine_when_disabled(self) -> None:
        y_true = pd.Series([9.0, 9.0, 9.0])
        bundle = _modeling_bundle()
        history_df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=8, freq="h"),
                "hour": [0, 1, 2, 3, 4, 5, 6, 7],
                "normalized_consumption": np.full(8, 9.0),
                "region_peak": np.ones(8),
            }
        )
        test_df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-02", periods=3, freq="h"),
                "region_peak": np.ones(3),
            }
        )
        X_train = pd.DataFrame({"hour": [1.0, 2.0, 3.0, 4.0]})
        y_train = pd.Series([9.0, 9.0, 9.0, 9.0])

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            with mock.patch("main.train_automl_models", side_effect=[bundle, bundle]), mock.patch(
                "main.load_best_model", return_value=None
            ), mock.patch("main.run_time_series_cv", return_value={"status": "ok"}), mock.patch(
                "main.save_best_model"
            ), mock.patch("main.append_model_registry"), mock.patch("main.AutoMLEngine") as mocked_engine, mock.patch(
                "main.log_training_event"
            ):
                aerix_main.run_modeling(
                    history_df=history_df,
                    test_df=test_df,
                    X_train=X_train,
                    y_train=y_train,
                    y_test=y_true,
                    model_path=tmp_root / "models" / "rf.pkl",
                    dataset_mode="grid",
                    best_model_path=tmp_root / "models" / "best_model.pkl",
                    model_registry_path=tmp_root / "models" / "model_registry.json",
                    optuna_trials=1,
                    log_path=tmp_root / "logs" / "training_activity.log",
                    enable_automl_engine=False,
                    automl_engine_max_trials=6,
                )
        self.assertFalse(mocked_engine.called)

    def test_run_modeling_calls_automl_engine_when_enabled(self) -> None:
        y_true = pd.Series([9.0, 9.0, 9.0])
        bundle = _modeling_bundle()
        history_df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=8, freq="h"),
                "hour": [0, 1, 2, 3, 4, 5, 6, 7],
                "normalized_consumption": np.full(8, 9.0),
                "region_peak": np.ones(8),
            }
        )
        test_df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-02", periods=3, freq="h"),
                "region_peak": np.ones(3),
            }
        )
        X_train = pd.DataFrame({"hour": [1.0, 2.0, 3.0, 4.0]})
        y_train = pd.Series([9.0, 9.0, 9.0, 9.0])

        automl_result = {
            "trial_count": 4,
            "best_trial": {
                "candidate_id": "RandomForest::n_estimators=200;max_depth=10",
                "hyperparameters": {"n_estimators": 200, "max_depth": 10},
                "validation_mae": 0.9,
            },
            "candidate_pool": {"models": {}, "predictions_mw": {}, "metrics": {}},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            mocked_engine_instance = mock.MagicMock()
            mocked_engine_instance.run_search.return_value = automl_result

            with mock.patch("main.train_automl_models", side_effect=[bundle, bundle]), mock.patch(
                "main.load_best_model", return_value=None
            ), mock.patch("main.run_time_series_cv", return_value={"status": "ok"}), mock.patch(
                "main.save_best_model"
            ) as mocked_save, mock.patch("main.append_model_registry"), mock.patch(
                "main.AutoMLEngine", return_value=mocked_engine_instance
            ) as mocked_engine, mock.patch("main.log_training_event"):
                aerix_main.run_modeling(
                    history_df=history_df,
                    test_df=test_df,
                    X_train=X_train,
                    y_train=y_train,
                    y_test=y_true,
                    model_path=tmp_root / "models" / "rf.pkl",
                    dataset_mode="grid",
                    best_model_path=tmp_root / "models" / "best_model.pkl",
                    model_registry_path=tmp_root / "models" / "model_registry.json",
                    optuna_trials=1,
                    log_path=tmp_root / "logs" / "training_activity.log",
                    enable_automl_engine=True,
                    automl_engine_max_trials=6,
                )

        self.assertTrue(mocked_engine.called)
        self.assertTrue(mocked_engine_instance.run_search.called)
        save_kwargs = mocked_save.call_args.kwargs
        self.assertEqual(save_kwargs.get("automl_enabled"), True)
        self.assertEqual(save_kwargs.get("automl_trials"), 4)
        self.assertEqual(save_kwargs.get("best_trial_params"), {"n_estimators": 200, "max_depth": 10})


if __name__ == "__main__":
    unittest.main()
