from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

import main as aerix_main
from src.ensemble_engine import (
    combine_predictions,
    compute_inverse_mae_weights,
    evaluate_ensemble,
    select_best_forecast_candidate,
)


class DummyModel:
    def __init__(self, value: float) -> None:
        self.value = float(value)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.full(shape=len(X), fill_value=self.value, dtype=float)


def _bundle_for_ensemble_case() -> dict:
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


class EnsembleEngineTests(unittest.TestCase):
    def test_combine_predictions_mean(self) -> None:
        predictions = {
            "LinearRegression": pd.Series([10.0, 20.0, 30.0]),
            "RandomForest": pd.Series([20.0, 30.0, 40.0]),
            "LightGBM": pd.Series([30.0, 40.0, 50.0]),
        }
        combined = combine_predictions(predictions, method="mean")
        expected = pd.Series([20.0, 30.0, 40.0])
        self.assertTrue(np.allclose(combined.values, expected.values))

    def test_weighted_ensemble_weights_are_deterministic(self) -> None:
        metrics = {
            "LinearRegression": {"mae": 2.0},
            "RandomForest": {"mae": 1.0},
            "LightGBM": {"mae": 1.0},
        }
        w1 = compute_inverse_mae_weights(metrics)
        w2 = compute_inverse_mae_weights(metrics)
        self.assertEqual(w1, w2)
        self.assertAlmostEqual(sum(w1.values()), 1.0, places=9)
        self.assertGreater(w1["RandomForest"], w1["LinearRegression"])
        self.assertAlmostEqual(w1["RandomForest"], w1["LightGBM"], places=9)

    def test_evaluate_ensemble_metrics(self) -> None:
        y_true = pd.Series([10.0, 12.0, 14.0])
        y_pred = pd.Series([11.0, 12.0, 13.0])
        metrics = evaluate_ensemble(y_true, y_pred)
        self.assertAlmostEqual(metrics["mae"], 2.0 / 3.0, places=8)
        self.assertAlmostEqual(metrics["rmse"], np.sqrt(2.0 / 3.0), places=8)

    def test_candidate_is_deterministic_and_beats_worst_base(self) -> None:
        y_true = pd.Series([9.0, 9.0, 9.0])
        bundle = _bundle_for_ensemble_case()
        first = select_best_forecast_candidate(
            y_true=y_true,
            predictions_mw=bundle["predictions_mw"],
            base_metrics=bundle["metrics"],
            base_models=bundle["models"],
        )
        second = select_best_forecast_candidate(
            y_true=y_true,
            predictions_mw=bundle["predictions_mw"],
            base_metrics=bundle["metrics"],
            base_models=bundle["models"],
        )

        self.assertEqual(first["selected_model_name"], second["selected_model_name"])
        self.assertEqual(first["ensemble_method"], second["ensemble_method"])
        self.assertTrue(np.allclose(first["selected_prediction"].values, second["selected_prediction"].values))

        worst_base_mae = max(metric["mae"] for metric in bundle["metrics"].values())
        self.assertLessEqual(first["ensemble_selected_metrics"]["mae"], worst_base_mae)

    def test_run_modeling_no_loaded_best_model_can_select_ensemble(self) -> None:
        y_true = pd.Series([9.0, 9.0, 9.0])
        bundle = _bundle_for_ensemble_case()

        history_df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=8, freq="h"),
                "feature1": np.arange(8),
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
        X_train = pd.DataFrame({"feature1": [1.0, 2.0, 3.0, 4.0]})
        y_train = pd.Series([9.0, 9.0, 9.0, 9.0])

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            with mock.patch("main.train_automl_models", side_effect=[bundle, bundle]), mock.patch(
                "main.load_best_model", return_value=None
            ), mock.patch("main.run_time_series_cv", return_value={"status": "ok"}), mock.patch(
                "main.save_best_model"
            ) as mocked_save, mock.patch("main.append_model_registry") as mocked_registry, mock.patch(
                "main.log_training_event"
            ):
                results, loaded = aerix_main.run_modeling(
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
                )

        self.assertFalse(loaded)
        self.assertEqual(results.ensemble_selected_source, "ensemble")
        self.assertTrue(results.selected_model_name.startswith("Ensemble("))
        self.assertTrue(mocked_save.called)
        self.assertTrue(mocked_registry.called)
        save_kwargs = mocked_save.call_args.kwargs
        self.assertEqual(save_kwargs.get("ensemble_enabled"), True)
        self.assertIn(save_kwargs.get("ensemble_method"), {"mean", "weighted", "none"})
        self.assertIn("ensemble_mae", save_kwargs)

    def test_run_modeling_with_loaded_model_keeps_loaded_when_better(self) -> None:
        y_true = pd.Series([9.0, 9.0, 9.0])
        bundle = _bundle_for_ensemble_case()

        history_df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=8, freq="h"),
                "feature1": np.arange(8),
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
        X_train = pd.DataFrame({"feature1": [1.0, 2.0, 3.0, 4.0]})
        y_train = pd.Series([9.0, 9.0, 9.0, 9.0])
        loaded_payload = {"model": DummyModel(9.1), "model_name": "LoadedRF"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            with mock.patch("main.train_automl_models", return_value=bundle), mock.patch(
                "main.load_best_model", return_value=loaded_payload
            ), mock.patch(
                "main._forecast_model_in_mw", return_value=pd.Series([9.05, 9.05, 9.05])
            ), mock.patch("main.run_time_series_cv", return_value={"status": "ok"}), mock.patch(
                "main.save_best_model"
            ) as mocked_save, mock.patch("main.append_model_registry") as mocked_registry, mock.patch(
                "main.log_training_event"
            ):
                results, loaded = aerix_main.run_modeling(
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
                )

        self.assertTrue(loaded)
        self.assertEqual(results.selected_model_name, "LoadedRF")
        self.assertFalse(mocked_save.called)
        self.assertFalse(mocked_registry.called)


if __name__ == "__main__":
    unittest.main()

