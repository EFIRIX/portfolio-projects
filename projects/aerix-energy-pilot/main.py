from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from configs import config as cfg
from src.activity_log import log_training_event
from src.anomaly_detection import run_anomaly_detection
from src.automl import append_model_registry, load_best_model, save_best_model, train_automl_models
from src.automl_engine import AutoMLEngine
from src.data_loader import load_energy_data
from src.data_ingestion import optional_kaggle_download, scan_data_sources
from src.ensemble_engine import select_best_forecast_candidate
from src.explainability import generate_shap_explainability
from src.feature_engineering import create_time_features, get_xy, train_test_split_time_series
from src.model_monitoring import record_monitoring_metrics
from src.model import evaluate, recursive_forecast
from src.optimization import optimize_peaks
from src.peak_detection import detect_peaks, get_peak_threshold
from src.preprocessing import preprocess_energy_data
from src.utils import calculate_co2_reduction, calculate_cost_savings_rub, format_rub
from src.validation import run_time_series_cv
from src.visualization import plot_detected_peaks, plot_forecast_vs_actual, plot_historical, run_eda
from src.weather_loader import load_weather_data, merge_weather_features


@dataclass
class AppConfig:
    data_path: Path
    model_path: Path
    best_model_path: Path
    model_registry_path: Path
    dataset: str
    mode: str
    unit_conversion: bool
    forecast_horizon: int
    forecast_horizons: list[int]
    peak_percentile: float
    shift_min: float
    shift_max: float
    price_per_mwh_rub: float
    co2_factor: float
    currency: str
    optuna_trials: int
    enable_explainability: bool
    enable_anomaly_detection: bool
    enable_data_ingestion_scan: bool
    enable_kaggle_download: bool
    enable_auto_retrain: bool
    auto_retrain_interval_hours: int
    enable_automl_engine: bool
    automl_engine_max_trials: int
    use_pipeline_orchestrator: bool


@dataclass
class DatasetSummary:
    rows: int
    start_timestamp: str
    end_timestamp: str
    grid_systems_count: int | None = None


@dataclass
class ModelResults:
    y_pred_linear: pd.Series
    y_pred_rf: pd.Series
    y_pred_lgbm: pd.Series
    y_pred_selected: pd.Series
    metrics_linear: dict[str, float]
    metrics_rf: dict[str, float]
    metrics_lgbm: dict[str, float]
    metrics_selected: dict[str, float]
    selected_model_name: str
    selected_model_loaded_from_disk: bool
    improvement_percent: float
    selected_model: Any | None = None
    cv_results: dict[str, Any] | None = None
    y_pred_base_best: pd.Series | None = None
    y_pred_ensemble: pd.Series | None = None
    metrics_base_best: dict[str, float] | None = None
    metrics_ensemble_selected: dict[str, float] | None = None
    ensemble_method_metrics: dict[str, dict[str, float]] | None = None
    ensemble_method_selected: str = "none"
    ensemble_enabled: bool = True
    ensemble_selected_source: str = "base"
    base_models: list[str] | None = None
    ensemble_weights: dict[str, float] | None = None
    automl_enabled: bool = False
    automl_trial_count: int = 0
    automl_best_model: str | None = None
    automl_best_params: dict[str, Any] | None = None
    automl_best_mae: float | None = None


@dataclass
class PeakResults:
    threshold: float
    peak_timestamps: list[pd.Timestamp]
    peak_values: list[float]


@dataclass
class OptimizationResults:
    optimized_predictions: pd.DataFrame
    peak_reduction_mw: float
    peak_reduction_mwh: float
    peak_reduction_percent: float
    cost_savings_rub: float
    co2_reduction: float


@dataclass
class PlotPaths:
    historical: Path
    forecast_vs_actual: Path
    detected_peaks: Path


@dataclass
class ComparisonRow:
    dataset: str
    mae: float | None
    peak_reduction_percent: float | None
    savings_rub: float | None
    status: str = "ok"


def _dataset_model_path(base_dir: Path, dataset: str) -> Path:
    model_rel_path = Path(cfg.MODEL_PATH)
    if dataset == "building":
        suffix = model_rel_path.suffix if model_rel_path.suffix else ".pkl"
        filename = f"{model_rel_path.stem}_building{suffix}"
        return base_dir / model_rel_path.parent / filename
    return base_dir / model_rel_path


def _dataset_best_model_path(base_dir: Path, dataset: str) -> Path:
    if dataset == "building":
        return base_dir / "models" / "best_model_building.pkl"
    return base_dir / "models" / "best_model.pkl"


def _dataset_registry_path(base_dir: Path, dataset: str) -> Path:
    if dataset == "building":
        return base_dir / "models" / "model_registry_building.json"
    return base_dir / "models" / "model_registry.json"



def load_config(base_dir: Path, dataset_override: str | None = None) -> AppConfig:
    dataset = str(dataset_override or getattr(cfg, "DATASET", "grid")).strip().lower()
    mode = str(getattr(cfg, "MODE", "grid")).strip().lower()

    if dataset == "building":
        mode = "factory"

    peak_percentile = 0.85 if mode == "factory" else cfg.PEAK_PERCENTILE

    if dataset == "building":
        data_path = base_dir / "data" / "building_energy.csv"
        if not data_path.exists():
            fallback = base_dir / "data" / "buildingdata.csv"
            if fallback.exists():
                data_path = fallback
        unit_conversion = bool(getattr(cfg, "UNIT_CONVERSION", True))
    else:
        data_path = base_dir / cfg.DATA_PATH
        unit_conversion = False

    if mode == "factory":
        price_per_mwh_rub = float(getattr(cfg, "PRICE_PER_MWH_FACTORY_RUB", cfg.PRICE_PER_MWH_RUB))
    else:
        price_per_mwh_rub = float(cfg.PRICE_PER_MWH_RUB)

    return AppConfig(
        data_path=data_path,
        model_path=_dataset_model_path(base_dir, dataset),
        best_model_path=_dataset_best_model_path(base_dir, dataset),
        model_registry_path=_dataset_registry_path(base_dir, dataset),
        dataset=dataset,
        mode=mode,
        unit_conversion=unit_conversion,
        forecast_horizon=cfg.FORECAST_HORIZON,
        forecast_horizons=list(getattr(cfg, "FORECAST_HORIZONS", [cfg.FORECAST_HORIZON])),
        peak_percentile=peak_percentile,
        shift_min=cfg.SHIFT_MIN,
        shift_max=cfg.SHIFT_MAX,
        price_per_mwh_rub=price_per_mwh_rub,
        co2_factor=cfg.CO2_FACTOR,
        currency=cfg.CURRENCY,
        optuna_trials=int(getattr(cfg, "AUTOML_TRIALS", 30)),
        enable_explainability=bool(getattr(cfg, "ENABLE_EXPLAINABILITY", False)),
        enable_anomaly_detection=bool(getattr(cfg, "ENABLE_ANOMALY_DETECTION", False)),
        enable_data_ingestion_scan=bool(getattr(cfg, "ENABLE_DATA_INGESTION_SCAN", False)),
        enable_kaggle_download=bool(getattr(cfg, "ENABLE_KAGGLE_DOWNLOAD", False)),
        enable_auto_retrain=bool(getattr(cfg, "ENABLE_AUTO_RETRAIN", True)),
        auto_retrain_interval_hours=int(getattr(cfg, "AUTO_RETRAIN_INTERVAL_HOURS", 24)),
        enable_automl_engine=bool(getattr(cfg, "ENABLE_AUTOML_ENGINE", True)),
        automl_engine_max_trials=int(getattr(cfg, "AUTOML_ENGINE_MAX_TRIALS", 30)),
        use_pipeline_orchestrator=bool(getattr(cfg, "USE_PIPELINE_ORCHESTRATOR", False)),
    )



def ensure_runtime_dirs(base_dir: Path, config: AppConfig) -> None:
    """Create models/ and outputs/ directories when missing."""
    config.model_path.parent.mkdir(parents=True, exist_ok=True)
    config.best_model_path.parent.mkdir(parents=True, exist_ok=True)
    config.model_registry_path.parent.mkdir(parents=True, exist_ok=True)
    (base_dir / "outputs").mkdir(parents=True, exist_ok=True)



def _ensure_normalized_columns(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    prepared["consumption"] = pd.to_numeric(prepared["consumption"], errors="coerce")

    if "region_peak" not in prepared.columns:
        peak = float(prepared["consumption"].max()) if len(prepared) else 1.0
        if not pd.notna(peak) or peak <= 0:
            peak = 1.0
        prepared["region_peak"] = peak
    else:
        prepared["region_peak"] = pd.to_numeric(prepared["region_peak"], errors="coerce")
        fallback_peak = float(prepared["consumption"].max()) if len(prepared) else 1.0
        if not pd.notna(fallback_peak) or fallback_peak <= 0:
            fallback_peak = 1.0
        prepared["region_peak"] = prepared["region_peak"].ffill().bfill().fillna(fallback_peak)
        prepared.loc[prepared["region_peak"] <= 0, "region_peak"] = fallback_peak

    if "region_name" not in prepared.columns:
        prepared["region_name"] = "default_region"
    else:
        prepared["region_name"] = prepared["region_name"].ffill().bfill().fillna("default_region")

    prepared["normalized_consumption"] = prepared["consumption"] / prepared["region_peak"]
    prepared["normalized_consumption"] = prepared["normalized_consumption"].clip(lower=0)

    return prepared



def load_and_preprocess(config: AppConfig) -> pd.DataFrame:
    raw_df = load_energy_data(
        config.data_path,
        dataset_name=config.dataset,
        unit_conversion=config.unit_conversion,
    )
    clean_df = preprocess_energy_data(raw_df)
    clean_df = _ensure_normalized_columns(clean_df)
    weather_df = load_weather_data(config.data_path.parent / "weather.csv")
    clean_df = merge_weather_features(clean_df, weather_df)

    grid_systems_count = raw_df.attrs.get("grid_file_count") if config.dataset == "grid" else None
    clean_df.attrs["grid_systems_count"] = grid_systems_count
    clean_df.attrs["region_peaks"] = raw_df.attrs.get("region_peaks", {})
    return clean_df



def summarize_dataset(clean_df: pd.DataFrame) -> DatasetSummary:
    eda = run_eda(clean_df)
    return DatasetSummary(
        rows=int(eda["rows"]),
        start_timestamp=str(eda["start_timestamp"]),
        end_timestamp=str(eda["end_timestamp"]),
        grid_systems_count=clean_df.attrs.get("grid_systems_count"),
    )



def split_features(clean_df: pd.DataFrame, forecast_horizon: int):
    featured_df = create_time_features(clean_df)
    train_df, test_df = train_test_split_time_series(featured_df, test_horizon_hours=forecast_horizon)

    X_train, y_train = get_xy(train_df)
    X_test, y_test = get_xy(test_df)
    return train_df, test_df, X_train, y_train, X_test, y_test



def _calculate_improvement(mae_linear: float, mae_rf: float) -> float:
    if mae_linear == 0:
        return 0.0
    return ((mae_linear - mae_rf) / mae_linear) * 100



def _restore_mw(values: pd.Series, region_peaks: pd.Series) -> pd.Series:
    y = pd.to_numeric(values, errors="coerce").reset_index(drop=True)
    peaks = pd.to_numeric(region_peaks, errors="coerce").reset_index(drop=True)
    fallback_peak = float(peaks.max()) if not peaks.empty else 1.0
    if not pd.notna(fallback_peak) or fallback_peak <= 0:
        fallback_peak = 1.0
    peaks = peaks.fillna(fallback_peak)
    peaks.loc[peaks <= 0] = fallback_peak
    if len(peaks) != len(y):
        peaks = pd.Series([fallback_peak] * len(y))
    return y * peaks



def _forecast_model_in_mw(
    model,
    history_df: pd.DataFrame,
    horizon: int,
    feature_columns: list[str],
    target_column: str,
    region_peaks_test: pd.Series,
) -> pd.Series:
    predicted_normalized = recursive_forecast(
        model=model,
        history_df=history_df,
        horizon=horizon,
        feature_columns=feature_columns,
        target_column=target_column,
    ).reset_index(drop=True)
    return _restore_mw(predicted_normalized, region_peaks_test)



def run_modeling(
    history_df: pd.DataFrame,
    test_df: pd.DataFrame,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    model_path: Path,
    dataset_mode: str = "grid",
    best_model_path: Path | None = None,
    model_registry_path: Path | None = None,
    optuna_trials: int = 30,
    log_path: Path | None = None,
    enable_automl_engine: bool = False,
    automl_engine_max_trials: int = 30,
) -> tuple[ModelResults, bool]:
    horizon = len(test_df)
    feature_columns = list(X_train.columns)
    target_column = "normalized_consumption" if "normalized_consumption" in history_df.columns else "consumption"
    training_dataset_size = int(len(history_df))

    region_peaks_test = pd.to_numeric(test_df.get("region_peak", 1.0), errors="coerce")
    y_test_mw = _restore_mw(y_test, region_peaks_test)

    baseline_bundle = train_automl_models(
        history_df=history_df,
        X_train=X_train,
        y_train=y_train,
        y_test_mw=y_test_mw,
        region_peaks_test=region_peaks_test,
        feature_columns=feature_columns,
        target_column=target_column,
        horizon=horizon,
        n_trials=1,
        tune_models=False,
    )

    resolved_log_path = log_path or Path("logs") / "training_activity.log"
    automl_trials_output_path = model_path.parent.parent / "outputs" / "automl_trials.json"
    automl_enabled = bool(enable_automl_engine)
    automl_trial_count = 0
    automl_best_model: str | None = None
    automl_best_params: dict[str, Any] | None = None
    automl_best_mae: float | None = None

    def _run_automl_on_training_branch() -> dict[str, Any] | None:
        nonlocal automl_trial_count
        nonlocal automl_best_model
        nonlocal automl_best_params
        nonlocal automl_best_mae

        if not automl_enabled:
            return None

        try:
            engine = AutoMLEngine(
                history_df=history_df,
                feature_columns=feature_columns,
                target_column=target_column,
                horizon=horizon,
                y_true_mw=y_test_mw,
                region_peaks_test=region_peaks_test,
                dataset_mode=dataset_mode,
                max_trials=automl_engine_max_trials,
                output_path=automl_trials_output_path,
            )
            result = engine.run_search(train_df=history_df)
            automl_trial_count = int(result.get("trial_count", 0))
            best_trial = result.get("best_trial") or {}
            if isinstance(best_trial, dict):
                automl_best_model = (
                    str(best_trial.get("candidate_id"))
                    if best_trial.get("candidate_id")
                    else str(best_trial.get("model_name") or "")
                )
                params = best_trial.get("hyperparameters")
                automl_best_params = dict(params) if isinstance(params, dict) else None
                best_mae = best_trial.get("validation_mae")
                automl_best_mae = float(best_mae) if best_mae is not None else None
            return result
        except Exception as exc:
            log_training_event(
                "automl engine skipped",
                details=f"mode={dataset_mode}; reason={exc}",
                log_path=resolved_log_path,
            )
            return None

    def _merge_automl_candidate_pool(bundle: dict[str, Any], automl_result: dict[str, Any] | None) -> dict[str, Any]:
        if automl_result is None:
            return bundle

        candidate_pool = automl_result.get("candidate_pool")
        if not isinstance(candidate_pool, dict):
            return bundle

        merged_models = dict(bundle.get("models", {}))
        merged_predictions = dict(bundle.get("predictions_mw", {}))
        merged_metrics = dict(bundle.get("metrics", {}))

        for name, model in candidate_pool.get("models", {}).items():
            merged_models[str(name)] = model
        for name, prediction in candidate_pool.get("predictions_mw", {}).items():
            merged_predictions[str(name)] = pd.to_numeric(prediction, errors="coerce").reset_index(drop=True)
        for name, metric in candidate_pool.get("metrics", {}).items():
            if isinstance(metric, dict):
                mae_value = metric.get("mae")
                rmse_value = metric.get("rmse")
                if mae_value is not None and rmse_value is not None:
                    merged_metrics[str(name)] = {"mae": float(mae_value), "rmse": float(rmse_value)}

        merged = dict(bundle)
        merged["models"] = merged_models
        merged["predictions_mw"] = merged_predictions
        merged["metrics"] = merged_metrics
        return merged

    def _candidate_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
        return select_best_forecast_candidate(
            y_true=y_test_mw.reset_index(drop=True),
            predictions_mw=bundle["predictions_mw"],
            base_metrics=bundle["metrics"],
            base_models=bundle.get("models"),
        )

    y_pred_linear = baseline_bundle["predictions_mw"]["LinearRegression"].reset_index(drop=True)
    y_pred_rf = baseline_bundle["predictions_mw"]["RandomForest"].reset_index(drop=True)
    y_pred_lgbm = baseline_bundle["predictions_mw"]["LightGBM"].reset_index(drop=True)

    metrics_linear = baseline_bundle["metrics"]["LinearRegression"]
    metrics_rf = baseline_bundle["metrics"]["RandomForest"]
    metrics_lgbm = baseline_bundle["metrics"]["LightGBM"]
    baseline_candidate = _candidate_from_bundle(baseline_bundle)

    improvement_percent = _calculate_improvement(metrics_linear["mae"], metrics_rf["mae"])

    resolved_best_model_path = best_model_path or (model_path.parent / "best_model.pkl")
    resolved_registry_path = model_registry_path or (model_path.parent / "model_registry.json")

    selected_model_name = str(baseline_candidate["selected_model_name"])
    selected_model_loaded = False
    selected_pred = baseline_candidate["selected_prediction"].reset_index(drop=True)
    selected_metrics = dict(baseline_candidate["selected_metrics"])
    selected_model_obj: Any | None = baseline_candidate.get("selected_model")
    cv_results: dict[str, Any] | None = None
    cv_model_name: str | None = str(baseline_candidate["base_best_name"])

    y_pred_base_best = baseline_candidate["base_best_prediction"].reset_index(drop=True)
    y_pred_ensemble = baseline_candidate["ensemble_selected_prediction"].reset_index(drop=True)
    metrics_base_best = dict(baseline_candidate["base_best_metrics"])
    metrics_ensemble_selected = dict(baseline_candidate["ensemble_selected_metrics"])
    ensemble_method_metrics = {
        method: dict(metrics)
        for method, metrics in baseline_candidate["ensemble_method_metrics"].items()
    }
    ensemble_method_selected = str(baseline_candidate["ensemble_method"])
    ensemble_enabled = True
    ensemble_selected_source = str(baseline_candidate["selected_source"])
    ensemble_base_models = [str(name) for name in baseline_candidate["base_models"]]
    ensemble_weights = {
        str(name): float(weight) for name, weight in baseline_candidate["ensemble_weights"].items()
    }

    def _update_candidate_diagnostics(candidate: dict[str, Any]) -> None:
        nonlocal selected_model_name
        nonlocal selected_pred
        nonlocal selected_metrics
        nonlocal selected_model_obj
        nonlocal cv_model_name
        nonlocal y_pred_base_best
        nonlocal y_pred_ensemble
        nonlocal metrics_base_best
        nonlocal metrics_ensemble_selected
        nonlocal ensemble_method_metrics
        nonlocal ensemble_method_selected
        nonlocal ensemble_selected_source
        nonlocal ensemble_base_models
        nonlocal ensemble_weights

        selected_model_name = str(candidate["selected_model_name"])
        selected_pred = candidate["selected_prediction"].reset_index(drop=True)
        selected_metrics = dict(candidate["selected_metrics"])
        selected_model_obj = candidate.get("selected_model")
        cv_model_name = str(candidate["base_best_name"])
        y_pred_base_best = candidate["base_best_prediction"].reset_index(drop=True)
        y_pred_ensemble = candidate["ensemble_selected_prediction"].reset_index(drop=True)
        metrics_base_best = dict(candidate["base_best_metrics"])
        metrics_ensemble_selected = dict(candidate["ensemble_selected_metrics"])
        ensemble_method_metrics = {
            method: dict(metrics)
            for method, metrics in candidate["ensemble_method_metrics"].items()
        }
        ensemble_method_selected = str(candidate["ensemble_method"])
        ensemble_selected_source = str(candidate["selected_source"])
        ensemble_base_models = [str(name) for name in candidate["base_models"]]
        ensemble_weights = {
            str(name): float(weight) for name, weight in candidate["ensemble_weights"].items()
        }

    def _ensemble_registry_method(candidate: dict[str, Any]) -> str:
        return str(candidate["ensemble_method"]) if str(candidate["selected_source"]) == "ensemble" else "none"

    loaded_payload = load_best_model(
        best_model_path=resolved_best_model_path,
        feature_columns=feature_columns,
        dataset_mode=dataset_mode,
    )

    if loaded_payload is not None:
        loaded_model = loaded_payload["model"]
        loaded_name = str(loaded_payload.get("model_name", "BestModel"))
        loaded_pred = _forecast_model_in_mw(
            model=loaded_model,
            history_df=history_df,
            horizon=horizon,
            feature_columns=feature_columns,
            target_column=target_column,
            region_peaks_test=region_peaks_test,
        )
        loaded_metrics = evaluate(y_test_mw.reset_index(drop=True), loaded_pred)

        selected_model_name = loaded_name
        selected_model_loaded = True
        selected_pred = loaded_pred
        selected_metrics = loaded_metrics
        selected_model_obj = loaded_model
        if loaded_name.startswith("Ensemble("):
            ensemble_selected_source = "ensemble"
        else:
            ensemble_selected_source = "base"

        payload_base_models = loaded_payload.get("base_models")
        if isinstance(payload_base_models, list) and payload_base_models:
            ensemble_base_models = [str(name) for name in payload_base_models]
        payload_ensemble_method = str(loaded_payload.get("ensemble_method") or "none")
        if payload_ensemble_method in {"mean", "weighted"}:
            ensemble_method_selected = payload_ensemble_method
        payload_automl_enabled = loaded_payload.get("automl_enabled")
        if payload_automl_enabled is not None:
            automl_enabled = bool(payload_automl_enabled)
        payload_automl_trials = loaded_payload.get("automl_trials")
        if payload_automl_trials is not None:
            automl_trial_count = int(payload_automl_trials)
        payload_best_trial_params = loaded_payload.get("best_trial_params")
        if isinstance(payload_best_trial_params, dict):
            automl_best_params = dict(payload_best_trial_params)
        payload_automl_mae = loaded_payload.get("automl_best_mae")
        if payload_automl_mae is not None:
            automl_best_mae = float(payload_automl_mae)
        payload_automl_best_model = loaded_payload.get("automl_best_model")
        if payload_automl_best_model is not None:
            automl_best_model = str(payload_automl_best_model)

        quick_best_name = str(baseline_candidate["selected_model_name"])
        quick_best_mae = float(baseline_candidate["selected_metrics"]["mae"])

        if quick_best_mae < loaded_metrics["mae"]:
            log_training_event(
                "training started",
                details=(
                    f"mode={dataset_mode}; reason=quick_candidate_beats_loaded; "
                    f"loaded_mae={loaded_metrics['mae']:.6f}; candidate_mae={quick_best_mae:.6f}"
                ),
                log_path=resolved_log_path,
            )
            log_training_event(
                "hyperparameter tuning",
                details=f"mode={dataset_mode}; models=RandomForest,LightGBM; trials={optuna_trials}",
                log_path=resolved_log_path,
            )
            tuned_bundle = train_automl_models(
                history_df=history_df,
                X_train=X_train,
                y_train=y_train,
                y_test_mw=y_test_mw,
                region_peaks_test=region_peaks_test,
                feature_columns=feature_columns,
                target_column=target_column,
                horizon=horizon,
                n_trials=optuna_trials,
                tune_models=True,
            )
            automl_result = _run_automl_on_training_branch()
            tuned_bundle = _merge_automl_candidate_pool(tuned_bundle, automl_result)
            tuned_candidate = _candidate_from_bundle(tuned_bundle)
            tuned_best_name = str(tuned_candidate["selected_model_name"])
            tuned_best_metrics = dict(tuned_candidate["selected_metrics"])

            if tuned_best_metrics["mae"] < loaded_metrics["mae"]:
                _update_candidate_diagnostics(tuned_candidate)
                selected_model_loaded = False
                save_best_model(
                    best_model_path=resolved_best_model_path,
                    model=tuned_candidate["selected_model"],
                    model_name=tuned_best_name,
                    feature_columns=feature_columns,
                    dataset_mode=dataset_mode,
                    mae=tuned_best_metrics["mae"],
                    rmse=tuned_best_metrics["rmse"],
                    ensemble_enabled=ensemble_enabled,
                    ensemble_method=_ensemble_registry_method(tuned_candidate),
                    base_models=[str(name) for name in tuned_candidate["base_models"]],
                    ensemble_mae=float(tuned_candidate["ensemble_selected_metrics"]["mae"]),
                    automl_enabled=automl_enabled,
                    automl_trials=automl_trial_count if automl_enabled else None,
                    best_trial_params=automl_best_params,
                    automl_best_mae=automl_best_mae,
                    automl_best_model=automl_best_model,
                )
                append_model_registry(
                    registry_path=resolved_registry_path,
                    model_name=tuned_best_name,
                    mae=tuned_best_metrics["mae"],
                    rmse=tuned_best_metrics["rmse"],
                    dataset_mode=dataset_mode,
                    training_dataset_size=training_dataset_size,
                    ensemble_enabled=ensemble_enabled,
                    ensemble_method=_ensemble_registry_method(tuned_candidate),
                    base_models=[str(name) for name in tuned_candidate["base_models"]],
                    ensemble_mae=float(tuned_candidate["ensemble_selected_metrics"]["mae"]),
                    automl_enabled=automl_enabled,
                    automl_trials=automl_trial_count if automl_enabled else None,
                    best_trial_params=automl_best_params,
                )
                log_training_event(
                    "model deployed",
                    details=(
                        f"mode={dataset_mode}; model={tuned_best_name}; "
                        f"mae={tuned_best_metrics['mae']:.6f}; rmse={tuned_best_metrics['rmse']:.6f}; "
                        f"source={tuned_candidate['selected_source']}"
                    ),
                    log_path=resolved_log_path,
                )
            else:
                log_training_event(
                    "model rejected",
                    details=(
                        f"mode={dataset_mode}; candidate={tuned_best_name}; "
                        f"candidate_mae={tuned_best_metrics['mae']:.6f}; kept_mae={loaded_metrics['mae']:.6f}"
                    ),
                    log_path=resolved_log_path,
                )
        else:
            log_training_event(
                "model rejected",
                details=(
                    f"mode={dataset_mode}; reason=loaded_model_better_than_quick_baselines; "
                    f"loaded_mae={loaded_metrics['mae']:.6f}; quick_best_mae={quick_best_mae:.6f}"
                ),
                log_path=resolved_log_path,
            )
    else:
        log_training_event(
            "training started",
            details=f"mode={dataset_mode}; reason=no_best_model_found",
            log_path=resolved_log_path,
        )
        log_training_event(
            "hyperparameter tuning",
            details=f"mode={dataset_mode}; models=RandomForest,LightGBM; trials={optuna_trials}",
            log_path=resolved_log_path,
        )
        tuned_bundle = train_automl_models(
            history_df=history_df,
            X_train=X_train,
            y_train=y_train,
            y_test_mw=y_test_mw,
            region_peaks_test=region_peaks_test,
            feature_columns=feature_columns,
            target_column=target_column,
            horizon=horizon,
            n_trials=optuna_trials,
            tune_models=True,
        )
        automl_result = _run_automl_on_training_branch()
        tuned_bundle = _merge_automl_candidate_pool(tuned_bundle, automl_result)
        tuned_candidate = _candidate_from_bundle(tuned_bundle)
        tuned_best_name = str(tuned_candidate["selected_model_name"])
        tuned_best_metrics = dict(tuned_candidate["selected_metrics"])
        _update_candidate_diagnostics(tuned_candidate)
        selected_model_loaded = False

        save_best_model(
            best_model_path=resolved_best_model_path,
            model=tuned_candidate["selected_model"],
            model_name=tuned_best_name,
            feature_columns=feature_columns,
            dataset_mode=dataset_mode,
            mae=tuned_best_metrics["mae"],
            rmse=tuned_best_metrics["rmse"],
            ensemble_enabled=ensemble_enabled,
            ensemble_method=_ensemble_registry_method(tuned_candidate),
            base_models=[str(name) for name in tuned_candidate["base_models"]],
            ensemble_mae=float(tuned_candidate["ensemble_selected_metrics"]["mae"]),
            automl_enabled=automl_enabled,
            automl_trials=automl_trial_count if automl_enabled else None,
            best_trial_params=automl_best_params,
            automl_best_mae=automl_best_mae,
            automl_best_model=automl_best_model,
        )
        append_model_registry(
            registry_path=resolved_registry_path,
            model_name=tuned_best_name,
            mae=tuned_best_metrics["mae"],
            rmse=tuned_best_metrics["rmse"],
            dataset_mode=dataset_mode,
            training_dataset_size=training_dataset_size,
            ensemble_enabled=ensemble_enabled,
            ensemble_method=_ensemble_registry_method(tuned_candidate),
            base_models=[str(name) for name in tuned_candidate["base_models"]],
            ensemble_mae=float(tuned_candidate["ensemble_selected_metrics"]["mae"]),
            automl_enabled=automl_enabled,
            automl_trials=automl_trial_count if automl_enabled else None,
            best_trial_params=automl_best_params,
        )
        log_training_event(
            "model deployed",
            details=(
                f"mode={dataset_mode}; model={tuned_best_name}; "
                f"mae={tuned_best_metrics['mae']:.6f}; rmse={tuned_best_metrics['rmse']:.6f}; "
                f"source={tuned_candidate['selected_source']}"
            ),
            log_path=resolved_log_path,
        )

    if cv_model_name is not None:
        cv_results = run_time_series_cv(
            df=history_df,
            model_name=cv_model_name,
            feature_columns=feature_columns,
            target_column=target_column,
            output_path=model_path.parent / "cv_results.json",
        )

    return (
        ModelResults(
            y_pred_linear=y_pred_linear,
            y_pred_rf=y_pred_rf,
            y_pred_lgbm=y_pred_lgbm,
            y_pred_selected=selected_pred,
            metrics_linear=metrics_linear,
            metrics_rf=metrics_rf,
            metrics_lgbm=metrics_lgbm,
            metrics_selected=selected_metrics,
            selected_model_name=selected_model_name,
            selected_model_loaded_from_disk=selected_model_loaded,
            improvement_percent=improvement_percent,
            selected_model=selected_model_obj,
            cv_results=cv_results,
            y_pred_base_best=y_pred_base_best,
            y_pred_ensemble=y_pred_ensemble,
            metrics_base_best=metrics_base_best,
            metrics_ensemble_selected=metrics_ensemble_selected,
            ensemble_method_metrics=ensemble_method_metrics,
            ensemble_method_selected=ensemble_method_selected,
            ensemble_enabled=ensemble_enabled,
            ensemble_selected_source=ensemble_selected_source,
            base_models=ensemble_base_models,
            ensemble_weights=ensemble_weights,
            automl_enabled=automl_enabled,
            automl_trial_count=automl_trial_count,
            automl_best_model=automl_best_model,
            automl_best_params=automl_best_params,
            automl_best_mae=automl_best_mae,
        ),
        selected_model_loaded,
    )



def build_forecast_dataframe(test_df: pd.DataFrame, y_pred_mw: pd.Series) -> pd.DataFrame:
    forecast_df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(test_df["timestamp"]).reset_index(drop=True),
            "predicted_consumption": pd.to_numeric(y_pred_mw, errors="coerce").reset_index(drop=True),
        }
    )
    return forecast_df.dropna(subset=["timestamp", "predicted_consumption"])



def run_peak_analysis(forecast_df: pd.DataFrame, percentile: float) -> PeakResults:
    threshold = get_peak_threshold(forecast_df["predicted_consumption"], percentile=percentile)
    peak_timestamps, peak_values = detect_peaks(forecast_df, threshold)

    forecast_df["is_peak"] = forecast_df["predicted_consumption"] > threshold

    return PeakResults(
        threshold=threshold,
        peak_timestamps=list(pd.to_datetime(peak_timestamps)),
        peak_values=peak_values,
    )



def run_optimization(
    forecast_df: pd.DataFrame,
    peak_timestamps: list[pd.Timestamp],
    shift_min: float,
    shift_max: float,
    price_per_mwh_rub: float,
    co2_factor: float,
) -> OptimizationResults:
    optimized_predictions, peak_reduction_mw, peak_reduction_percent = optimize_peaks(
        predictions=forecast_df,
        peaks=peak_timestamps,
        shift_min=shift_min,
        shift_max=shift_max,
    )

    # Convert MW to MWh for one peak hour before economic calculation.
    peak_reduction_mwh = peak_reduction_mw * 1.0
    cost_savings_rub = calculate_cost_savings_rub(peak_reduction_mwh, price_per_mwh_rub)
    co2_reduction = calculate_co2_reduction(peak_reduction_mw, co2_factor)

    return OptimizationResults(
        optimized_predictions=optimized_predictions,
        peak_reduction_mw=peak_reduction_mw,
        peak_reduction_mwh=peak_reduction_mwh,
        peak_reduction_percent=peak_reduction_percent,
        cost_savings_rub=cost_savings_rub,
        co2_reduction=co2_reduction,
    )



def generate_plots(
    clean_df: pd.DataFrame,
    test_df: pd.DataFrame,
    y_test: pd.Series,
    y_pred_mw: pd.Series,
    forecast_df: pd.DataFrame,
    peak_timestamps: list[pd.Timestamp],
) -> PlotPaths:
    y_test_plot = pd.Series(y_test.values, index=pd.to_datetime(test_df["timestamp"]).values)

    return PlotPaths(
        historical=plot_historical(clean_df, "historical_consumption.png"),
        forecast_vs_actual=plot_forecast_vs_actual(y_test_plot, y_pred_mw, "forecast_vs_actual.png"),
        detected_peaks=plot_detected_peaks(forecast_df, peak_timestamps, "detected_peaks.png"),
    )



def format_peak_hours(peak_timestamps: list[pd.Timestamp]) -> list[str]:
    return [ts.strftime("%Y-%m-%d %H:%M") for ts in peak_timestamps]



def print_report(
    config: AppConfig,
    dataset_summary: DatasetSummary,
    model_results: ModelResults,
    peak_results: PeakResults,
    optimization_results: OptimizationResults,
) -> None:
    peak_hours = format_peak_hours(peak_results.peak_timestamps)
    mode_label = "промышленное предприятие" if config.mode == "factory" else "энергосистема"

    print("=== AERIX Energy Pilot (РФ) ===")
    print(f"Режим: {mode_label}")
    print()
    print("Данные:")
    print(f"Строк: {dataset_summary.rows}")
    print(f"Период: {dataset_summary.start_timestamp} -> {dataset_summary.end_timestamp}")
    if config.dataset == "grid" and dataset_summary.grid_systems_count is not None:
        print(f"Количество энергосистем в обучении: {dataset_summary.grid_systems_count}")
    print()
    print("Качество модели:")
    print(f"MAE (Linear): {model_results.metrics_linear['mae']:.3f}")
    print(f"RMSE (Linear): {model_results.metrics_linear['rmse']:.3f}")
    print(f"MAE (RF): {model_results.metrics_rf['mae']:.3f}")
    print(f"RMSE (RF): {model_results.metrics_rf['rmse']:.3f}")
    print(f"MAE (LightGBM): {model_results.metrics_lgbm['mae']:.3f}")
    print(f"RMSE (LightGBM): {model_results.metrics_lgbm['rmse']:.3f}")
    mean_metrics = (model_results.ensemble_method_metrics or {}).get("mean")
    weighted_metrics = (model_results.ensemble_method_metrics or {}).get("weighted")
    if mean_metrics is not None:
        print(f"MAE (Ensemble Mean): {float(mean_metrics['mae']):.3f}")
        print(f"RMSE (Ensemble Mean): {float(mean_metrics['rmse']):.3f}")
    if weighted_metrics is not None:
        print(f"MAE (Ensemble Weighted): {float(weighted_metrics['mae']):.3f}")
        print(f"RMSE (Ensemble Weighted): {float(weighted_metrics['rmse']):.3f}")
    print(f"Ensemble method selected: {model_results.ensemble_method_selected}")
    print(f"Selected source: {model_results.ensemble_selected_source}")
    print(f"Улучшение (%): {model_results.improvement_percent:.2f}")
    print(f"Selected model: {model_results.selected_model_name}")
    print(f"MAE (Selected): {model_results.metrics_selected['mae']:.3f}")
    print(f"RMSE (Selected): {model_results.metrics_selected['rmse']:.3f}")
    if model_results.automl_enabled:
        print(f"AutoML trials: {model_results.automl_trial_count}")
        if model_results.automl_best_model is not None:
            print(f"AutoML best trial: {model_results.automl_best_model}")
        if model_results.automl_best_mae is not None:
            print(f"AutoML best MAE: {model_results.automl_best_mae:.3f}")
    print(
        "Источник выбранной модели: "
        f"{'загружена из best_model.pkl' if model_results.selected_model_loaded_from_disk else 'обучена/обновлена AutoML'}"
    )
    print()
    print("Пиковый анализ:")
    print(f"Порог пика: {peak_results.threshold:.3f}")
    print(f"Часы пиков: {peak_hours if peak_hours else 'Нет'}")
    print()
    print("Оптимизация:")
    print(f"Снижение пика (%): {optimization_results.peak_reduction_percent:.2f}")
    print(f"Снижение мощности (МВт): {optimization_results.peak_reduction_mw:.3f}")
    print(f"Экономия (₽): {format_rub(optimization_results.cost_savings_rub)}")
    print(f"Снижение выбросов CO2 (тонн): {optimization_results.co2_reduction:.3f}")
    print()

    if config.mode == "factory":
        final_message = "снижающая пиковые нагрузки: предприятие и промышленные объекты."
    else:
        final_message = "снижающая пиковые нагрузки энергосистем и промышленных предприятий."
    print(
        "AERIX — ИИ-система предиктивного управления энергопотреблением,\n"
        f"{final_message}"
    )


def run_single_pipeline(
    base_dir: Path,
    config: AppConfig,
    emit_report: bool = True,
    emit_plots: bool = True,
) -> ComparisonRow:
    ensure_runtime_dirs(base_dir, config)

    clean_df = load_and_preprocess(config)
    dataset_summary = summarize_dataset(clean_df)

    train_df, test_df, X_train, y_train, X_test, y_test = split_features(clean_df, config.forecast_horizon)
    model_results, _ = run_modeling(
        train_df,
        test_df,
        X_train,
        y_train,
        y_test,
        config.model_path,
        dataset_mode=config.mode,
        best_model_path=config.best_model_path,
        model_registry_path=config.model_registry_path,
        optuna_trials=config.optuna_trials,
        log_path=base_dir / "logs" / "training_activity.log",
        enable_automl_engine=config.enable_automl_engine,
        automl_engine_max_trials=config.automl_engine_max_trials,
    )

    forecast_df = build_forecast_dataframe(test_df, model_results.y_pred_selected)
    peak_results = run_peak_analysis(forecast_df, config.peak_percentile)
    optimization_results = run_optimization(
        forecast_df,
        peak_results.peak_timestamps,
        config.shift_min,
        config.shift_max,
        config.price_per_mwh_rub,
        config.co2_factor,
    )

    if config.enable_anomaly_detection:
        _anomaly_result = run_anomaly_detection(clean_df, output_path=base_dir / "outputs" / "anomalies.png")

    if config.enable_explainability:
        _explainability_result = generate_shap_explainability(
            model=model_results.selected_model,
            X_test=X_test,
            output_dir=base_dir / "outputs",
        )

    record_monitoring_metrics(
        mae=model_results.metrics_selected["mae"],
        rmse=model_results.metrics_selected["rmse"],
        model_name=model_results.selected_model_name,
        dataset_mode=config.mode,
        output_path=base_dir / "models" / "monitoring_metrics.json",
    )

    if emit_plots:
        y_test_mw = _restore_mw(y_test, pd.to_numeric(test_df.get("region_peak", 1.0), errors="coerce"))
        _plot_paths = generate_plots(
            clean_df,
            test_df,
            y_test_mw,
            model_results.y_pred_selected,
            forecast_df,
            peak_results.peak_timestamps,
        )

    if emit_report:
        print_report(config, dataset_summary, model_results, peak_results, optimization_results)

    return ComparisonRow(
        dataset=config.dataset,
        mae=float(model_results.metrics_selected["mae"]),
        peak_reduction_percent=float(optimization_results.peak_reduction_percent),
        savings_rub=float(optimization_results.cost_savings_rub),
    )


def print_comparison_table(rows: list[ComparisonRow]) -> None:
    print("Dataset | MAE | Peak reduction % | Savings RUB")
    for row in rows:
        mae_str = f"{row.mae:.3f}" if row.mae is not None else "N/A"
        peak_str = f"{row.peak_reduction_percent:.2f}" if row.peak_reduction_percent is not None else "N/A"
        savings_str = f"{row.savings_rub:.2f}" if row.savings_rub is not None else "N/A"
        print(f"{row.dataset} | {mae_str} | {peak_str} | {savings_str}")


def run_comparison_mode(base_dir: Path) -> None:
    comparison_rows: list[ComparisonRow] = []
    for dataset_name in ["grid", "building"]:
        config = load_config(base_dir, dataset_override=dataset_name)
        try:
            row = run_single_pipeline(base_dir, config, emit_report=False, emit_plots=False)
        except Exception:
            row = ComparisonRow(
                dataset=dataset_name,
                mae=None,
                peak_reduction_percent=None,
                savings_rub=None,
                status="error",
            )
        comparison_rows.append(row)

    print_comparison_table(comparison_rows)



def main() -> None:
    base_dir = Path(__file__).resolve().parent
    run_comparison = bool(getattr(cfg, "RUN_COMPARISON", False))

    if run_comparison:
        run_comparison_mode(base_dir)
        return

    config = load_config(base_dir)
    if config.use_pipeline_orchestrator:
        from src.pipeline import run_pipeline

        _ = run_pipeline(
            base_dir=base_dir,
            dataset_override=config.dataset,
            emit_report=True,
            emit_plots=True,
            run_data_ingestion=config.enable_data_ingestion_scan,
            run_kaggle_download=config.enable_kaggle_download,
        )
        return

    if config.enable_data_ingestion_scan:
        _ = scan_data_sources(
            base_dir / "data_sources",
            log_path=base_dir / "logs" / "training_activity.log",
        )
    if config.enable_kaggle_download:
        _ = optional_kaggle_download(
            sources_config=base_dir / "data_sources" / "sources.json",
            target_dir=base_dir / "data_sources",
        )

    _ = run_single_pipeline(base_dir, config, emit_report=True, emit_plots=True)


if __name__ == "__main__":
    main()
