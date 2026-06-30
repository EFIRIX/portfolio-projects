from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from src.auto_retrain import compare_models, run_auto_retrain_cycle, trigger_retraining
from src.data_ingestion import evaluate_dataset_before_append, scan_for_new_data
from src.dataset_evaluator import evaluate_dataset


class DatasetIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        rng = np.random.default_rng(42)
        timestamps = pd.date_range("2024-01-01", periods=1000, freq="h")
        baseline_load = 100.0 + 10.0 * np.sin(np.linspace(0, 20, len(timestamps))) + rng.normal(0, 1.5, len(timestamps))
        self.baseline_df = pd.DataFrame({"timestamp": timestamps, "consumption": baseline_load})

    def test_dataset_evaluation_acceptance(self) -> None:
        rng = np.random.default_rng(123)
        candidate = self.baseline_df.copy()
        candidate["consumption"] = candidate["consumption"] + rng.normal(0, 1.0, len(candidate))
        score = evaluate_dataset(candidate, self.baseline_df)

        self.assertGreater(score["final_score"], 0.65)
        self.assertGreater(score["expected_model_gain"], 0.0)
        self.assertTrue(score["accepted"])

    def test_dataset_evaluation_rejection(self) -> None:
        bad = self.baseline_df.copy()
        bad["consumption"] = 0.0
        bad.loc[::3, "consumption"] = np.nan

        score = evaluate_dataset(bad, self.baseline_df)
        self.assertFalse(score["accepted"])

    def test_ingestion_evaluation_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            dataset_path = tmp_root / "candidate.csv"
            baseline_path = tmp_root / "baseline.csv"

            candidate = self.baseline_df.head(300).copy()
            candidate.to_csv(dataset_path, index=False)
            self.baseline_df.to_csv(baseline_path, index=False)

            evaluation = evaluate_dataset_before_append(dataset_path, baseline_path=baseline_path)
            self.assertIn("final_score", evaluation)
            self.assertIn("expected_model_gain", evaluation)
            self.assertIn("accepted", evaluation)
            self.assertTrue(evaluation["accepted"])

    def test_training_improvement_detection(self) -> None:
        comparison = compare_models(
            previous_metrics={"model_name": "BaselineRF", "mae": 1200.0, "rmse": 1800.0},
            new_metrics={"model_name": "CandidateLGBM", "mae": 1100.0, "rmse": 1700.0},
        )
        self.assertTrue(comparison["improved"])
        self.assertLess(comparison["mae_delta"], 0.0)

    def test_no_accepted_data_skips_retraining(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            with mock.patch(
                "src.auto_retrain.check_for_new_data",
                return_value={"new_data_found": True, "datasets_accepted": 0},
            ), mock.patch("src.auto_retrain.trigger_retraining") as mocked_trigger:
                result = run_auto_retrain_cycle(
                    base_dir=tmp_root,
                    dataset_override="grid",
                    interval_hours=24,
                    force=True,
                )

            self.assertEqual(result["reason"], "no_accepted_data")
            mocked_trigger.assert_not_called()

    def test_trigger_retraining_deploys_only_when_mae_improves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            registry_path = tmp_root / "models" / "model_registry.json"
            pool_path = tmp_root / "data" / "training_pool" / "global_training_pool.csv"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            pool_path.parent.mkdir(parents=True, exist_ok=True)

            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "model_name": "Baseline",
                            "MAE": 100.0,
                            "RMSE": 150.0,
                            "timestamp": "2026-01-01T00:00:00+00:00",
                            "dataset_mode": "grid",
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            pool_df = pd.DataFrame(
                {
                    "timestamp": pd.date_range("2024-01-01", periods=10, freq="h"),
                    "consumption": np.linspace(100.0, 120.0, 10),
                    "source": ["s1"] * 5 + ["s2"] * 5,
                }
            )
            pool_df.to_csv(pool_path, index=False)

            def improved_pipeline_side_effect(**_: object) -> None:
                entries = json.loads(registry_path.read_text(encoding="utf-8"))
                entries.append(
                    {
                        "model_name": "Candidate",
                        "MAE": 90.0,
                        "RMSE": 140.0,
                        "timestamp": "2026-01-02T00:00:00+00:00",
                        "dataset_mode": "grid",
                    }
                )
                registry_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

            with mock.patch("src.auto_retrain.run_pipeline", side_effect=improved_pipeline_side_effect):
                result = trigger_retraining(
                    base_dir=tmp_root,
                    dataset_override="grid",
                    emit_plots=False,
                    ingestion_summary={"dataset_quality_score": 0.91},
                )

            self.assertTrue(result["comparison"]["improved"])
            self.assertTrue(result["deployment"]["deployed"])

            updated_registry = json.loads(registry_path.read_text(encoding="utf-8"))
            latest = updated_registry[-1]
            self.assertIn("training_dataset_size", latest)
            self.assertIn("dataset_count", latest)
            self.assertIn("training_timestamp", latest)
            self.assertIn("dataset_quality_score", latest)

    def test_trigger_retraining_rejects_non_improved_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            registry_path = tmp_root / "models" / "model_registry.json"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "model_name": "Baseline",
                            "MAE": 100.0,
                            "RMSE": 150.0,
                            "timestamp": "2026-01-01T00:00:00+00:00",
                            "dataset_mode": "grid",
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            pool_path = tmp_root / "data" / "training_pool" / "global_training_pool.csv"
            pool_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                {
                    "timestamp": pd.date_range("2024-01-01", periods=8, freq="h"),
                    "consumption": np.linspace(10.0, 18.0, 8),
                    "source": ["s1"] * 8,
                }
            ).to_csv(pool_path, index=False)

            def worse_pipeline_side_effect(**_: object) -> None:
                entries = json.loads(registry_path.read_text(encoding="utf-8"))
                entries.append(
                    {
                        "model_name": "CandidateWorse",
                        "MAE": 105.0,
                        "RMSE": 155.0,
                        "timestamp": "2026-01-02T00:00:00+00:00",
                        "dataset_mode": "grid",
                    }
                )
                registry_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

            with mock.patch("src.auto_retrain.run_pipeline", side_effect=worse_pipeline_side_effect):
                result = trigger_retraining(
                    base_dir=tmp_root,
                    dataset_override="grid",
                    emit_plots=False,
                )

            self.assertFalse(result["comparison"]["improved"])
            self.assertFalse(result["deployment"]["deployed"])

    def test_ingestion_rejected_dataset_not_merged_and_registry_fields_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            pool_path = tmp_root / "global_training_pool.csv"
            grid_export_path = tmp_root / "grid_export.csv"
            registry_path = tmp_root / "dataset_registry.json"
            log_path = tmp_root / "training.log"

            self.baseline_df.head(24).to_csv(pool_path, index=False)
            rejected_file = tmp_root / "rejected.csv"
            pd.DataFrame({"time_value": [1, 2, 3], "load_value": [10, 11, 12]}).to_csv(rejected_file, index=False)

            before_rows = len(pd.read_csv(pool_path))
            source = {"name": "rejected_source", "type": "http", "url": "http://example.com/data.csv"}
            with mock.patch("src.data_ingestion.discover_datasets", return_value=[source]), mock.patch(
                "src.data_ingestion.download_dataset",
                return_value={"status": "ok", "reason": "", "files": [str(rejected_file)]},
            ):
                summary = scan_for_new_data(
                    sources_config=tmp_root / "sources.json",
                    target_dir=tmp_root / "downloads",
                    training_pool_file=pool_path,
                    grid_export_file=grid_export_path,
                    dataset_registry_path=registry_path,
                    log_path=log_path,
                )

            after_rows = len(pd.read_csv(pool_path))
            self.assertEqual(before_rows, after_rows)
            self.assertGreaterEqual(int(summary.get("datasets_rejected", 0)), 1)

            registry_entries = json.loads(registry_path.read_text(encoding="utf-8"))
            latest = registry_entries[-1]
            for key in (
                "dataset_name",
                "source",
                "schema",
                "quality_score",
                "accepted",
                "rejected_reason",
                "timestamp",
            ):
                self.assertIn(key, latest)
            self.assertFalse(latest["accepted"])

    def test_ingestion_accepted_dataset_merges_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            pool_path = tmp_root / "global_training_pool.csv"
            grid_export_path = tmp_root / "grid_export.csv"
            registry_path = tmp_root / "dataset_registry.json"
            log_path = tmp_root / "training.log"

            baseline = self.baseline_df.head(200).copy()
            baseline["source"] = "baseline_source"
            baseline.to_csv(pool_path, index=False)

            candidate = self.baseline_df.head(200).copy()
            candidate = pd.concat([candidate, candidate.iloc[[0]]], ignore_index=True)
            candidate.loc[len(candidate) - 1, "consumption"] = candidate["consumption"].iloc[0] + 1.0
            candidate_file = tmp_root / "accepted.csv"
            candidate.to_csv(candidate_file, index=False)

            source = {"name": "accepted_source", "type": "http", "url": "http://example.com/data.csv"}
            with mock.patch("src.data_ingestion.discover_datasets", return_value=[source]), mock.patch(
                "src.data_ingestion.download_dataset",
                return_value={"status": "ok", "reason": "", "files": [str(candidate_file)]},
            ):
                summary = scan_for_new_data(
                    sources_config=tmp_root / "sources.json",
                    target_dir=tmp_root / "downloads",
                    training_pool_file=pool_path,
                    grid_export_file=grid_export_path,
                    dataset_registry_path=registry_path,
                    log_path=log_path,
                )

            merged = pd.read_csv(pool_path)
            merged_ts = pd.to_datetime(merged["timestamp"], errors="coerce")
            self.assertTrue(merged_ts.is_monotonic_increasing)
            self.assertEqual(int(merged_ts.duplicated().sum()), 0)
            self.assertGreaterEqual(int(summary.get("datasets_accepted", 0)), 1)

            registry_entries = json.loads(registry_path.read_text(encoding="utf-8"))
            latest = registry_entries[-1]
            self.assertTrue(latest["accepted"])
            self.assertIn("quality_score", latest)


if __name__ == "__main__":
    unittest.main()
