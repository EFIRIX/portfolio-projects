from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
import ast
import re
import urllib.error
import urllib.request

import joblib
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import main as aerix_main
from src.activity_log import read_recent_activity
from src.anomaly_detection import run_anomaly_detection
from src.auto_retrain import load_auto_retrain_status, run_auto_retrain_cycle
from src.cost_optimizer import load_energy_price, optimize_for_cost, summarize_costs
from src.dataset_health_monitor import monitor_training_pool
from src.equipment_model import load_equipment, save_equipment_state
from src.energy_map import build_energy_map_dataframe, build_energy_map_figure
from src.i18n import DEFAULT_LANGUAGE, LANGUAGE_OPTIONS, get_translator
from src.optimization_engine import apply_optimization_plan, generate_optimization_plan, summarize_optimization
from src.pipeline import run_pipeline
from src.plant_graph import build_plant_graph, build_plant_graph_figure
from src.precision import round_float
from src.scenario_engine import compare_scenarios, run_scenario
from src.simulation import simulate_system
from src.telemetry_anomaly import detect_machine_anomalies
from src.telemetry_simulator import stream_machine_telemetry
from src.utils import format_rub


BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"
RUN_TIMEOUT_SECONDS = 1800


st.set_page_config(
    page_title="AERIX Energy Intelligence Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str
    duration_sec: float


# ---------- Styling ----------
def inject_styles() -> None:
    st.markdown(
        """
        <style>
            :root {
                --bg-0: #090C14;
                --bg-1: #0B0F1A;
                --bg-2: #121A2E;
                --text-main: #EAF0FF;
                --text-dim: #98A8C3;
                --accent-a: #4F7BFF;
                --accent-b: #8F6BFF;
                --accent-c: #00E5FF;
                --ok: #37E39A;
                --danger: #FF5F77;
            }

            .stApp {
                background:
                    radial-gradient(900px 450px at 10% -5%, rgba(79,123,255,0.22), transparent 45%),
                    radial-gradient(650px 360px at 100% 0%, rgba(143,107,255,0.20), transparent 40%),
                    linear-gradient(180deg, var(--bg-1), var(--bg-0));
                color: var(--text-main);
            }

            .block-container {
                max-width: 1540px;
                padding-top: 1rem;
                padding-bottom: 2rem;
            }

            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #0F1629 0%, #0B1020 100%);
                border-right: 1px solid rgba(255,255,255,0.08);
            }

            [data-testid="stMetric"] {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 14px;
                padding: 0.8rem 1rem;
                box-shadow: 0 12px 35px rgba(0,0,0,0.30);
            }

            [data-testid="stMetricLabel"] {
                color: var(--text-dim) !important;
            }

            [data-testid="stMetricValue"] {
                font-size: 1.95rem;
                color: #FFFFFF;
            }

            .aerix-hero {
                background:
                    radial-gradient(450px 200px at 20% 0%, rgba(0,229,255,0.18), transparent 55%),
                    linear-gradient(135deg, rgba(79,123,255,0.18), rgba(143,107,255,0.16));
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 18px;
                padding: 1rem 1.2rem;
                margin-bottom: 0.9rem;
            }

            .aerix-title {
                margin: 0;
                font-size: 2rem;
                line-height: 1.2;
                letter-spacing: 0.3px;
            }

            .aerix-subtitle {
                color: var(--text-dim);
                margin-top: 0.35rem;
                margin-bottom: 0;
            }

            .aerix-panel {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 16px;
                padding: 0.9rem 1rem;
                box-shadow: 0 10px 32px rgba(0,0,0,0.28);
            }

            .aerix-panel h3 {
                margin-top: 0.2rem;
            }

            .aerix-inline-kv {
                color: var(--text-dim);
                font-size: 0.92rem;
                line-height: 1.55;
            }

            .aerix-architecture {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 16px;
                padding: 1.05rem 1.2rem;
                font-weight: 600;
                letter-spacing: 0.35px;
                text-align: center;
            }

            .aerix-footer {
                margin-top: 1rem;
                padding: 1rem 1.2rem;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 14px;
                background: rgba(255,255,255,0.03);
                color: #DCE5FF;
            }

            .aerix-badge {
                display: inline-block;
                font-size: 0.78rem;
                padding: 0.2rem 0.55rem;
                border-radius: 999px;
                border: 1px solid rgba(255,255,255,0.18);
                color: #D7E0FF;
                margin-right: 0.35rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------- Helpers ----------
def init_state() -> None:
    st.session_state.setdefault("refresh_id", 0)
    st.session_state.setdefault("selected_profile", "grid")
    st.session_state.setdefault("selected_horizon", 72)
    st.session_state.setdefault("selected_language", DEFAULT_LANGUAGE)
    st.session_state.setdefault("selected_training_model", "RandomForest")
    st.session_state.setdefault("last_training_metrics", None)
    st.session_state.setdefault("last_auto_retrain_result", None)
    st.session_state.setdefault("last_run_result", None)


def resolve_registry_path(profile: str) -> Path:
    default_path = BASE_DIR / "models" / "model_registry.json"
    if profile == "factory":
        factory_path = BASE_DIR / "models" / "model_registry_building.json"
        if factory_path.exists():
            return factory_path
    return default_path


def profile_to_dataset(profile: str) -> str:
    return "grid" if profile == "grid" else "building"


def prepare_config(profile: str):
    dataset_override = profile_to_dataset(profile)
    config = aerix_main.load_config(BASE_DIR, dataset_override=dataset_override)

    # Backward compatibility for local file naming.
    if config.dataset == "building" and not config.data_path.exists():
        fallback = BASE_DIR / "data" / "buildingdata.csv"
        if fallback.exists():
            config.data_path = fallback

    return config


def run_model_subprocess(profile: str) -> RunResult:
    dataset_override = profile_to_dataset(profile)
    script = f"""
from pathlib import Path
import main

base = Path(r'''{BASE_DIR}''')
config = main.load_config(base, dataset_override='{dataset_override}')
if config.dataset == 'building' and not config.data_path.exists():
    fallback = base / 'data' / 'buildingdata.csv'
    if fallback.exists():
        config.data_path = fallback
main.run_single_pipeline(base, config, emit_report=True, emit_plots=True)
"""

    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        check=False,
        timeout=RUN_TIMEOUT_SECONDS,
    )
    elapsed = time.perf_counter() - started

    return RunResult(
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        duration_sec=elapsed,
    )


def execute_training_flow(profile: str, t_fn) -> dict:
    training_start = time.perf_counter()
    monitor_registry_path = resolve_registry_path(profile)
    monitor_mtime = monitor_registry_path.stat().st_mtime if monitor_registry_path.exists() else 0.0
    monitor_entries = load_registry_entries(str(monitor_registry_path), monitor_mtime)
    baseline_mae = _safe_float(monitor_entries[-1].get("MAE")) if monitor_entries else None
    baseline_dataset_size = monitor_entries[-1].get("training_dataset_size") if monitor_entries else None
    models_tested = 0
    simulated_best_mae = baseline_mae

    st.markdown(f"**{t_fn('ai_training_monitor')}**")
    mon_cols = st.columns(5)
    step_box = st.empty()
    progress = st.progress(0, text=t_fn("loading_datasets"))

    training_steps = [
        (t_fn("loading_datasets"), 12, 0),
        (t_fn("feature_engineering"), 25, 0),
        (t_fn("running_automl"), 42, 1),
        (t_fn("hyperparameter_tuning"), 64, 2),
        (t_fn("evaluating_candidates"), 84, 3),
        (t_fn("selecting_best_model"), 93, 3),
        (t_fn("saving_best_model"), 100, 3),
    ]

    with st.spinner(t_fn("training_spinner")):
        for step_name, pct, tested in training_steps:
            models_tested = max(models_tested, tested)
            if simulated_best_mae is not None and tested > 0:
                simulated_best_mae = max(0.0, simulated_best_mae * 0.997)

            elapsed = time.perf_counter() - training_start
            mon_cols[0].metric(t_fn("training_step_current"), step_name)
            mon_cols[1].metric(t_fn("elapsed_time"), f"{elapsed:.1f}s")
            mon_cols[2].metric(t_fn("models_tested"), f"{models_tested}")
            mon_cols[3].metric(
                t_fn("current_mae"),
                f"{simulated_best_mae:.3f}" if simulated_best_mae is not None else t_fn("na"),
            )
            if baseline_dataset_size is None:
                mon_cols[4].metric(t_fn("dataset_size"), t_fn("na"))
            else:
                mon_cols[4].metric(t_fn("dataset_size"), f"{int(baseline_dataset_size):,}".replace(",", " "))

            step_box.info(step_name)
            progress.progress(pct, text=step_name)
            time.sleep(0.22)

            if step_name == t_fn("evaluating_candidates"):
                run_pipeline(
                    base_dir=BASE_DIR,
                    dataset_override=profile_to_dataset(profile),
                    emit_report=False,
                    emit_plots=True,
                    run_data_ingestion=True,
                    run_kaggle_download=False,
                )

    duration_sec = time.perf_counter() - training_start
    step_box.success(t_fn("training_completed"))
    st.session_state["refresh_id"] += 1

    refreshed_mtime = monitor_registry_path.stat().st_mtime if monitor_registry_path.exists() else 0.0
    refreshed_entries = load_registry_entries(str(monitor_registry_path), refreshed_mtime)
    latest = refreshed_entries[-1] if refreshed_entries else {}
    summary = {
        "model_name": str(latest.get("model_name") or t_fn("na")),
        "mae": _safe_float(latest.get("MAE")),
        "rmse": _safe_float(latest.get("RMSE")),
        "duration_sec": duration_sec,
        "timestamp": str(latest.get("timestamp") or ""),
    }
    st.session_state["last_training_metrics"] = summary
    return summary


@st.cache_data(show_spinner=False)
def load_image_bytes(path_str: str, modified_at: float) -> bytes | None:
    _ = modified_at
    path = Path(path_str)
    if not path.exists():
        return None
    return path.read_bytes()


@st.cache_data(show_spinner=False)
def load_registry_entries(path_str: str, modified_at: float) -> list[dict]:
    _ = modified_at
    path = Path(path_str)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload
    except Exception:
        return []
    return []


@st.cache_data(show_spinner=False)
def load_automl_trials(path_str: str, modified_at: float) -> dict:
    _ = modified_at
    path = Path(path_str)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


@st.cache_data(show_spinner=False)
def load_dataset_registry_entries(path_str: str, modified_at: float) -> list[dict]:
    _ = modified_at
    path = Path(path_str)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
    except Exception:
        return []
    return []


@st.cache_data(show_spinner=False)
def load_activity_entries(path_str: str, modified_at: float, limit: int = 20) -> list[dict]:
    _ = modified_at
    lines = read_recent_activity(path_str, limit=limit)
    entries: list[dict] = []
    for line in lines:
        parts = [part.strip() for part in line.split("|", maxsplit=2)]
        if len(parts) == 1:
            entries.append({"timestamp": "", "event": parts[0], "details": ""})
        elif len(parts) == 2:
            entries.append({"timestamp": parts[0], "event": parts[1], "details": ""})
        else:
            entries.append({"timestamp": parts[0], "event": parts[1], "details": parts[2]})
    return entries


@st.cache_data(show_spinner=False)
def load_dataset_health_metrics(training_pool_path: str, baseline_path: str, refresh_id: int) -> dict:
    _ = refresh_id
    try:
        return monitor_training_pool(training_pool_path=training_pool_path, baseline_path=baseline_path)
    except Exception:
        return {
            "rows": 0,
            "schema_drift": True,
            "dataset_drift": 0.0,
            "timestamp_gap_ratio": 1.0,
            "abnormal_range_ratio": 1.0,
            "status": "health_monitor_error",
        }


@st.cache_data(show_spinner=False)
def build_dashboard_data(profile: str, refresh_id: int, forecast_horizon: int) -> dict:
    _ = refresh_id
    config = prepare_config(profile)
    config.forecast_horizon = int(forecast_horizon)

    aerix_main.ensure_runtime_dirs(BASE_DIR, config)
    clean_df = aerix_main.load_and_preprocess(config)
    dataset_summary = aerix_main.summarize_dataset(clean_df)

    train_df, test_df, X_train, y_train, _, y_test = aerix_main.split_features(
        clean_df, config.forecast_horizon
    )
    model_results, _ = aerix_main.run_modeling(
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
        log_path=BASE_DIR / "logs" / "training_activity.log",
        enable_automl_engine=getattr(config, "enable_automl_engine", False),
        automl_engine_max_trials=getattr(config, "automl_engine_max_trials", 30),
    )
    # Avoid caching bulky model objects in Streamlit cache payload.
    model_results.selected_model = None

    y_test_mw = aerix_main._restore_mw(
        y_test, pd.to_numeric(test_df.get("region_peak", 1.0), errors="coerce")
    )

    forecast_df = aerix_main.build_forecast_dataframe(test_df, model_results.y_pred_selected)
    peak_results = aerix_main.run_peak_analysis(forecast_df, config.peak_percentile)
    optimization_results = aerix_main.run_optimization(
        forecast_df,
        peak_results.peak_timestamps,
        config.shift_min,
        config.shift_max,
        config.price_per_mwh_rub,
        config.co2_factor,
    )

    aerix_main.generate_plots(
        clean_df,
        test_df,
        y_test_mw,
        model_results.y_pred_selected,
        forecast_df,
        peak_results.peak_timestamps,
    )

    actual_vs_forecast = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(test_df["timestamp"]).reset_index(drop=True),
            "actual": pd.to_numeric(y_test_mw.values, errors="coerce"),
            "forecast": pd.to_numeric(model_results.y_pred_selected.values, errors="coerce"),
        }
    ).dropna(subset=["timestamp", "actual", "forecast"])

    ensemble_compare = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(test_df["timestamp"]).reset_index(drop=True),
            "actual": pd.to_numeric(y_test_mw.values, errors="coerce"),
            "linear": pd.to_numeric(model_results.y_pred_linear.values, errors="coerce"),
            "random_forest": pd.to_numeric(model_results.y_pred_rf.values, errors="coerce"),
            "lightgbm": pd.to_numeric(model_results.y_pred_lgbm.values, errors="coerce"),
            "base_best": pd.to_numeric(
                model_results.y_pred_base_best.values if model_results.y_pred_base_best is not None else None,
                errors="coerce",
            ),
            "ensemble": pd.to_numeric(
                model_results.y_pred_ensemble.values if model_results.y_pred_ensemble is not None else None,
                errors="coerce",
            ),
            "selected": pd.to_numeric(model_results.y_pred_selected.values, errors="coerce"),
        }
    ).dropna(subset=["timestamp", "actual", "selected"])

    peaks_df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(peak_results.peak_timestamps, errors="coerce"),
            "value": pd.to_numeric(peak_results.peak_values, errors="coerce"),
        }
    ).dropna(subset=["timestamp", "value"])

    optimized_df = optimization_results.optimized_predictions.copy()
    optimized_df["timestamp"] = pd.to_datetime(optimized_df["timestamp"], errors="coerce")
    optimized_df["predicted_consumption"] = pd.to_numeric(
        optimized_df["predicted_consumption"], errors="coerce"
    )
    optimized_df = optimized_df.dropna(subset=["timestamp", "predicted_consumption"])

    # Normalize historical frame to a single timestamp column.
    if "timestamp" in clean_df.columns:
        historical_df = clean_df.copy()
    else:
        index_name = clean_df.index.name if clean_df.index.name else "index"
        historical_df = clean_df.reset_index().rename(columns={index_name: "timestamp"})

    historical_df = historical_df.loc[:, ~historical_df.columns.duplicated(keep="first")]
    historical_df["timestamp"] = pd.to_datetime(historical_df["timestamp"], errors="coerce")
    historical_df["consumption"] = pd.to_numeric(historical_df["consumption"], errors="coerce")
    historical_df = historical_df.dropna(subset=["timestamp", "consumption"])

    original_peak = float(forecast_df["predicted_consumption"].max()) if not forecast_df.empty else 0.0
    optimized_peak = (
        float(optimized_df["predicted_consumption"].max()) if not optimized_df.empty else 0.0
    )

    anomaly_result = run_anomaly_detection(clean_df, output_path=OUTPUTS_DIR / "anomalies.png")
    anomaly_timestamps = pd.to_datetime(
        pd.Series(anomaly_result.get("timestamps", []), dtype="object"),
        errors="coerce",
    ).dropna()
    anomaly_df = historical_df[historical_df["timestamp"].isin(set(anomaly_timestamps.tolist()))].copy()

    return {
        "config": config,
        "clean_df": clean_df,
        "dataset_summary": dataset_summary,
        "model_results": model_results,
        "peak_results": peak_results,
        "optimization_results": optimization_results,
        "actual_vs_forecast": actual_vs_forecast,
        "ensemble_compare": ensemble_compare,
        "forecast_df": forecast_df,
        "peaks_df": peaks_df,
        "optimized_df": optimized_df,
        "historical_df": historical_df,
        "anomaly_result": anomaly_result,
        "anomaly_df": anomaly_df,
        "original_peak": original_peak,
        "optimized_peak": optimized_peak,
    }


def style_plot(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        margin=dict(l=34, r=24, t=48, b=32),
        font=dict(color="#EAF0FF", size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.0),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.09)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.09)", zeroline=False)
    return fig


def fmt_num(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}".replace(",", " ")


def profile_label(profile: str, language: str = DEFAULT_LANGUAGE) -> str:
    translator = get_translator(language)
    if profile == "grid":
        return translator("mode_grid")
    return translator("mode_factory")


def _extract_text(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def _extract_float(pattern: str, text: str) -> float | None:
    raw = _extract_text(pattern, text)
    if raw is None:
        return None
    cleaned = (
        raw.replace("₽", "")
        .replace("%", "")
        .replace(" ", "")
        .replace(",", ".")
    )
    numeric_match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not numeric_match:
        return None
    try:
        return float(numeric_match.group(0))
    except ValueError:
        return None


def _extract_peak_hours(text: str) -> list[str]:
    raw = _extract_text(r"Часы пиков:\s*(.+)", text)
    if raw is None or raw == "Нет":
        return []
    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except Exception:
        pass
    return [raw]


def parse_run_report(stdout: str) -> dict:
    return {
        "mode": _extract_text(r"Режим:\s*(.+)", stdout),
        "rows": _extract_text(r"Строк:\s*(.+)", stdout),
        "period": _extract_text(r"Период:\s*(.+)", stdout),
        "systems_count": _extract_text(r"Количество энергосистем в обучении:\s*(.+)", stdout),
        "mae_linear": _extract_float(r"MAE \(Linear\):\s*(.+)", stdout),
        "rmse_linear": _extract_float(r"RMSE \(Linear\):\s*(.+)", stdout),
        "mae_rf": _extract_float(r"MAE \(RF\):\s*(.+)", stdout),
        "rmse_rf": _extract_float(r"RMSE \(RF\):\s*(.+)", stdout),
        "mae_lgbm": _extract_float(r"MAE \(LightGBM\):\s*(.+)", stdout),
        "rmse_lgbm": _extract_float(r"RMSE \(LightGBM\):\s*(.+)", stdout),
        "mae_ensemble_mean": _extract_float(r"MAE \(Ensemble Mean\):\s*(.+)", stdout),
        "rmse_ensemble_mean": _extract_float(r"RMSE \(Ensemble Mean\):\s*(.+)", stdout),
        "mae_ensemble_weighted": _extract_float(r"MAE \(Ensemble Weighted\):\s*(.+)", stdout),
        "rmse_ensemble_weighted": _extract_float(r"RMSE \(Ensemble Weighted\):\s*(.+)", stdout),
        "ensemble_method": _extract_text(r"Ensemble method selected:\s*(.+)", stdout),
        "selected_source": _extract_text(r"Selected source:\s*(.+)", stdout),
        "improvement_pct": _extract_float(r"Улучшение \(%\):\s*(.+)", stdout),
        "peak_threshold": _extract_float(r"Порог пика:\s*(.+)", stdout),
        "peak_hours": _extract_peak_hours(stdout),
        "peak_reduction_pct": _extract_float(r"Снижение пика \(%\):\s*(.+)", stdout),
        "mw_reduced": _extract_float(r"Снижение мощности \(МВт\):\s*(.+)", stdout),
        "savings_rub": _extract_float(r"Экономия \(₽\):\s*(.+)", stdout),
        "co2_reduction": _extract_float(r"Снижение выбросов CO2 \(тонн\):\s*(.+)", stdout),
        "selected_model": _extract_text(r"Selected model:\s*(.+)", stdout),
        "selected_mae": _extract_float(r"MAE \(Selected\):\s*(.+)", stdout),
        "selected_rmse": _extract_float(r"RMSE \(Selected\):\s*(.+)", stdout),
    }


def render_run_details_menu(run_result: RunResult) -> None:
    t_fn = get_translator(st.session_state.get("selected_language", DEFAULT_LANGUAGE))
    st.markdown("---")
    st.subheader(t_fn("run_details"))

    status_label = t_fn("status_ok") if run_result.returncode == 0 else t_fn("status_error")
    status_color = "#37E39A" if run_result.returncode == 0 else "#FF5F77"
    st.markdown(
        f"<div class='aerix-inline-kv'><b>{t_fn('status_panel')}:</b> <span style='color:{status_color}'>{status_label}</span><br>"
        f"<b>{t_fn('training_duration')}:</b> {run_result.duration_sec:.1f}s<br>"
        f"<b>Code:</b> {run_result.returncode}</div>",
        unsafe_allow_html=True,
    )

    parsed = parse_run_report(run_result.stdout)
    tabs = st.tabs(["Summary", "Data", "Model", "Peaks", "Optimization", "Diagnostics"])

    with tabs[0]:
        c1, c2 = st.columns(2)
        with c1:
            if parsed["improvement_pct"] is not None:
                st.metric(f"{t_fn('improvement')} %", f"{parsed['improvement_pct']:.2f}%")
            else:
                st.metric(f"{t_fn('improvement')} %", t_fn("na"))
        with c2:
            peak_count = len(parsed["peak_hours"])
            st.metric(t_fn("peak_detection_panel"), f"{peak_count}")
        if parsed["mode"]:
            st.caption(f"{t_fn('mode_label')}: {parsed['mode']}")
        if parsed["selected_model"]:
            st.caption(
                f"{t_fn('current_best_model')}: {parsed['selected_model']} | "
                f"MAE: {parsed['selected_mae']:.3f} | RMSE: {parsed['selected_rmse']:.3f}"
                if parsed["selected_mae"] is not None and parsed["selected_rmse"] is not None
                else f"{t_fn('current_best_model')}: {parsed['selected_model']}"
            )
        if parsed.get("ensemble_method"):
            st.caption(
                f"{t_fn('ensemble_method_selected')}: {parsed['ensemble_method']} | "
                f"{t_fn('selected_source')}: {parsed.get('selected_source') or t_fn('na')}"
            )

    with tabs[1]:
        st.markdown(
            f"<div class='aerix-inline-kv'><b>Rows:</b> {parsed['rows'] or t_fn('na')}<br>"
            f"<b>{t_fn('systems_count')}:</b> {parsed['systems_count'] or t_fn('na')}<br>"
            f"<b>{t_fn('dataset_period')}:</b> {parsed['period'] or t_fn('na')}</div>",
            unsafe_allow_html=True,
        )

    with tabs[2]:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric(
                "MAE (LinearRegression)",
                f"{parsed['mae_linear']:.3f}" if parsed["mae_linear"] is not None else t_fn("na"),
            )
            st.metric(
                "RMSE (LinearRegression)",
                f"{parsed['rmse_linear']:.3f}" if parsed["rmse_linear"] is not None else t_fn("na"),
            )
        with c2:
            st.metric(
                "MAE (RandomForest)",
                f"{parsed['mae_rf']:.3f}" if parsed["mae_rf"] is not None else t_fn("na"),
            )
            st.metric(
                "RMSE (RandomForest)",
                f"{parsed['rmse_rf']:.3f}" if parsed["rmse_rf"] is not None else t_fn("na"),
            )
        with c3:
            st.metric(
                "MAE (LightGBM)",
                f"{parsed['mae_lgbm']:.3f}" if parsed["mae_lgbm"] is not None else t_fn("na"),
            )
            st.metric(
                "RMSE (LightGBM)",
                f"{parsed['rmse_lgbm']:.3f}" if parsed["rmse_lgbm"] is not None else t_fn("na"),
            )
            st.metric(
                "MAE (Ensemble)",
                (
                    f"{parsed['mae_ensemble_weighted']:.3f}"
                    if parsed["ensemble_method"] == "weighted" and parsed["mae_ensemble_weighted"] is not None
                    else (
                        f"{parsed['mae_ensemble_mean']:.3f}"
                        if parsed["mae_ensemble_mean"] is not None
                        else t_fn("na")
                    )
                ),
            )

    with tabs[3]:
        st.metric(
            "Peak threshold",
            f"{parsed['peak_threshold']:.3f}" if parsed["peak_threshold"] is not None else t_fn("na"),
        )
        peak_hours = parsed["peak_hours"]
        if peak_hours:
            preview = peak_hours[:8]
            for hour in preview:
                st.caption(f"• {hour}")
            if len(peak_hours) > len(preview):
                st.caption(f"... +{len(peak_hours) - len(preview)}")
        else:
            st.caption(f"{t_fn('peak_detection_panel')}: {t_fn('na')}")

    with tabs[4]:
        c1, c2 = st.columns(2)
        with c1:
            st.metric(
                t_fn("kpi_peak_reduction_pct"),
                f"{parsed['peak_reduction_pct']:.2f}%"
                if parsed["peak_reduction_pct"] is not None
                else t_fn("na"),
            )
            st.metric(
                t_fn("kpi_mw_reduced"),
                fmt_num(parsed["mw_reduced"]) if parsed["mw_reduced"] is not None else t_fn("na"),
            )
        with c2:
            savings_text = format_rub(parsed["savings_rub"]) if parsed["savings_rub"] is not None else t_fn("na")
            st.metric(t_fn("kpi_savings"), savings_text)
            st.metric(
                t_fn("kpi_co2"),
                fmt_num(parsed["co2_reduction"]) if parsed["co2_reduction"] is not None else t_fn("na"),
            )

    with tabs[5]:
        if run_result.stderr.strip():
            st.warning(run_result.stderr.strip())
        else:
            st.caption(t_fn("stderr_none"))
        with st.expander(t_fn("stdout_stderr")):
            st.text_area(
                t_fn("stdout_label"),
                value=run_result.stdout.strip() or "(empty)",
                height=160,
            )


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def build_self_learning_summary(
    registry_entries: list[dict],
    profile: str,
    systems_count: int,
    fallback_model_name: str,
    fallback_mae: float,
) -> dict:
    if not registry_entries:
        return {
            "last_training_ts": "Н/Д",
            "current_best_model": fallback_model_name,
            "training_dataset_size": None,
            "datasets_used": systems_count,
            "current_mae": fallback_mae,
            "previous_mae": None,
            "improvement_pct": None,
            "history_df": pd.DataFrame(columns=["timestamp", "MAE", "model_name"]),
        }

    registry_df = pd.DataFrame(registry_entries).copy()
    if registry_df.empty:
        return {
            "last_training_ts": "Н/Д",
            "current_best_model": fallback_model_name,
            "training_dataset_size": None,
            "datasets_used": systems_count,
            "current_mae": fallback_mae,
            "previous_mae": None,
            "improvement_pct": None,
            "history_df": pd.DataFrame(columns=["timestamp", "MAE", "model_name"]),
        }

    if "dataset_mode" in registry_df.columns:
        target_mode = "factory" if profile == "factory" else "grid"
        mode_filtered = registry_df[registry_df["dataset_mode"].astype(str) == target_mode].copy()
        if not mode_filtered.empty:
            registry_df = mode_filtered

    if "timestamp" in registry_df.columns:
        registry_df["timestamp"] = pd.to_datetime(registry_df["timestamp"], errors="coerce", utc=True)
        registry_df = registry_df.dropna(subset=["timestamp"]).sort_values("timestamp")
    else:
        registry_df["timestamp"] = pd.NaT

    if "MAE" in registry_df.columns:
        registry_df["MAE"] = pd.to_numeric(registry_df["MAE"], errors="coerce")
    else:
        registry_df["MAE"] = pd.NA

    latest = registry_df.iloc[-1]
    previous_mae = None
    if len(registry_df) >= 2:
        previous_mae = _safe_float(registry_df.iloc[-2]["MAE"])

    current_mae = _safe_float(latest.get("MAE"))
    if current_mae is None:
        current_mae = fallback_mae

    improvement_pct = None
    if previous_mae is not None and previous_mae > 0 and current_mae is not None:
        improvement_pct = ((previous_mae - current_mae) / previous_mae) * 100

    training_dataset_size = latest.get("training_dataset_size")
    try:
        training_dataset_size = int(training_dataset_size) if training_dataset_size is not None else None
    except Exception:
        training_dataset_size = None

    last_ts = latest.get("timestamp")
    if pd.notna(last_ts):
        last_ts = pd.Timestamp(last_ts).tz_convert(None).strftime("%Y-%m-%d %H:%M")
    else:
        last_ts = "Н/Д"

    history_df = registry_df[["timestamp", "MAE", "model_name"]].copy()
    history_df = history_df.dropna(subset=["timestamp", "MAE"])
    if not history_df.empty:
        history_df["timestamp"] = history_df["timestamp"].dt.tz_convert(None)

    return {
        "last_training_ts": str(last_ts),
        "current_best_model": str(latest.get("model_name") or fallback_model_name),
        "training_dataset_size": training_dataset_size,
        "datasets_used": systems_count,
        "current_mae": current_mae,
        "previous_mae": previous_mae,
        "improvement_pct": improvement_pct,
        "history_df": history_df,
    }


@st.cache_data(show_spinner=False)
def build_dataset_explorer(profile: str, refresh_id: int) -> pd.DataFrame:
    _ = refresh_id
    rows: list[dict] = []
    data_dir = BASE_DIR / "data"

    if profile == "grid":
        grid_files = sorted(data_dir.glob("grid_*.csv"))
        for file_path in grid_files:
            try:
                raw = pd.read_csv(file_path)
                timestamp_col = next(
                    (
                        c
                        for c in ["Datetime", "timestamp", "datetime", "date_time", "date"]
                        if c in raw.columns
                    ),
                    None,
                )
                ts_series = pd.to_datetime(raw[timestamp_col], errors="coerce") if timestamp_col else pd.Series(dtype="datetime64[ns]")
                rows.append(
                    {
                        "dataset name": file_path.name,
                        "number of rows": int(len(raw)),
                        "date range": (
                            f"{ts_series.min()} → {ts_series.max()}"
                            if timestamp_col and ts_series.notna().any()
                            else "Н/Д"
                        ),
                        "region": file_path.stem.replace("grid_", ""),
                    }
                )
            except Exception:
                rows.append(
                    {
                        "dataset name": file_path.name,
                        "number of rows": 0,
                        "date range": "Н/Д",
                        "region": file_path.stem.replace("grid_", ""),
                    }
                )
    else:
        building_candidates = [data_dir / "building_energy.csv", data_dir / "buildingdata.csv"]
        for file_path in building_candidates:
            if not file_path.exists():
                continue
            try:
                raw = pd.read_csv(file_path)
                timestamp_col = next(
                    (
                        c
                        for c in ["timestamp", "Datetime", "datetime", "date_time", "date"]
                        if c in raw.columns
                    ),
                    None,
                )
                ts_series = pd.to_datetime(raw[timestamp_col], errors="coerce") if timestamp_col else pd.Series(dtype="datetime64[ns]")
                rows.append(
                    {
                        "dataset name": file_path.name,
                        "number of rows": int(len(raw)),
                        "date range": (
                            f"{ts_series.min()} → {ts_series.max()}"
                            if timestamp_col and ts_series.notna().any()
                            else "Н/Д"
                        ),
                        "region": "factory",
                    }
                )
            except Exception:
                rows.append(
                    {
                        "dataset name": file_path.name,
                        "number of rows": 0,
                        "date range": "Н/Д",
                        "region": "factory",
                    }
                )

    return pd.DataFrame(rows, columns=["dataset name", "number of rows", "date range", "region"])


def load_top_feature_ranking(best_model_path: Path, top_n: int = 8) -> pd.DataFrame:
    if not best_model_path.exists():
        return pd.DataFrame(columns=["feature", "importance"])

    try:
        payload = joblib.load(best_model_path)
        if not isinstance(payload, dict):
            return pd.DataFrame(columns=["feature", "importance"])
        model = payload.get("model")
        feature_columns = payload.get("feature_columns", [])
        if model is None or not isinstance(feature_columns, list) or not feature_columns:
            return pd.DataFrame(columns=["feature", "importance"])

        if hasattr(model, "feature_importances_"):
            importances = pd.Series(model.feature_importances_, index=feature_columns)
        elif hasattr(model, "coef_"):
            coef = getattr(model, "coef_")
            importances = pd.Series(pd.Series(coef).abs().values, index=feature_columns)
        else:
            return pd.DataFrame(columns=["feature", "importance"])

        rank_df = (
            importances.sort_values(ascending=False)
            .head(top_n)
            .reset_index()
            .rename(columns={"index": "feature", 0: "importance"})
        )
        rank_df["importance"] = pd.to_numeric(rank_df["importance"], errors="coerce")
        return rank_df
    except Exception:
        return pd.DataFrame(columns=["feature", "importance"])


def is_api_running(url: str = "http://localhost:8000/metrics") -> bool:
    try:
        with urllib.request.urlopen(url, timeout=0.8) as response:
            return 200 <= int(response.status) < 400
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False
    except Exception:
        return False


@st.cache_data(show_spinner=False)
def load_equipment_cached(refresh_id: int) -> pd.DataFrame:
    _ = refresh_id
    return load_equipment(BASE_DIR / "data" / "machines.json", BASE_DIR / "data" / "machines_state.json")


@st.cache_data(show_spinner=False)
def load_energy_price_cached(refresh_id: int) -> pd.DataFrame | None:
    _ = refresh_id
    return load_energy_price(BASE_DIR / "data" / "energy_price.csv")


def _ensure_machine_editor_state(equipment_df: pd.DataFrame) -> None:
    if "equipment_editor_df" not in st.session_state:
        st.session_state["equipment_editor_df"] = equipment_df.copy()
        return

    existing = st.session_state["equipment_editor_df"]
    if not isinstance(existing, pd.DataFrame) or set(existing.get("machine_id", [])) != set(equipment_df["machine_id"]):
        st.session_state["equipment_editor_df"] = equipment_df.copy()


def _render_equipment_filters(equipment_df: pd.DataFrame, t_fn) -> pd.DataFrame:
    filter_cols = st.columns(4)
    with filter_cols[0]:
        type_options = sorted(equipment_df["machine_type"].astype(str).unique().tolist())
        selected_types = st.multiselect(
            t_fn("machine_type_filter"),
            options=type_options,
            default=type_options,
        )
    with filter_cols[1]:
        priority_options = sorted(equipment_df["priority"].astype(str).unique().tolist())
        selected_priorities = st.multiselect(
            t_fn("priority_filter"),
            options=priority_options,
            default=priority_options,
        )
    with filter_cols[2]:
        flexibility_filter = st.selectbox(
            t_fn("flexibility_filter"),
            options=[t_fn("all"), t_fn("flexible"), t_fn("non_flexible")],
            index=0,
        )
    with filter_cols[3]:
        availability_filter = st.selectbox(
            t_fn("availability_filter"),
            options=[t_fn("all"), t_fn("available"), t_fn("unavailable")],
            index=0,
        )

    filtered = equipment_df.copy()
    filtered = filtered[filtered["machine_type"].astype(str).isin(selected_types)]
    filtered = filtered[filtered["priority"].astype(str).isin(selected_priorities)]

    if flexibility_filter == t_fn("flexible"):
        filtered = filtered[filtered["flexibility"] == True]  # noqa: E712
    elif flexibility_filter == t_fn("non_flexible"):
        filtered = filtered[filtered["flexibility"] == False]  # noqa: E712

    if availability_filter == t_fn("available"):
        filtered = filtered[filtered["availability"] == True]  # noqa: E712
    elif availability_filter == t_fn("unavailable"):
        filtered = filtered[filtered["availability"] == False]  # noqa: E712

    return filtered.reset_index(drop=True)


# ---------- App ----------
init_state()
inject_styles()

lang_reverse = {code: label for label, code in LANGUAGE_OPTIONS.items()}
lang_codes = list(LANGUAGE_OPTIONS.values())
current_lang_code = st.session_state.get("selected_language", DEFAULT_LANGUAGE)
if current_lang_code not in lang_codes:
    current_lang_code = DEFAULT_LANGUAGE
lang_t = get_translator(current_lang_code)

lang_cols = st.columns([6.2, 1.6], gap="small")
with lang_cols[1]:
    selected_lang_label = st.selectbox(
        lang_t("language"),
        options=list(LANGUAGE_OPTIONS.keys()),
        index=list(LANGUAGE_OPTIONS.keys()).index(lang_reverse.get(current_lang_code, "English")),
        key="language_selector",
    )
selected_lang_code = LANGUAGE_OPTIONS[selected_lang_label]
if selected_lang_code != st.session_state.get("selected_language"):
    st.session_state["selected_language"] = selected_lang_code
    st.rerun()

t = get_translator(st.session_state.get("selected_language", DEFAULT_LANGUAGE))

st.markdown(
    f"""
    <div class="aerix-hero">
      <p class="aerix-title">{t("app_title")}</p>
      <p class="aerix-subtitle">{t("app_subtitle")}</p>
      <div style="margin-top:0.55rem;">
        <span class="aerix-badge">{t("badge_realtime")}</span>
        <span class="aerix-badge">{t("badge_peak")}</span>
        <span class="aerix-badge">{t("badge_optimization")}</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

current_profile = st.session_state.get("selected_profile", "grid")
current_horizon = int(st.session_state.get("selected_horizon", 72))

st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("system_overview"))
st.markdown(f"**{t('control_center')}**")

control_cols = st.columns([1.0, 1.0, 1.1, 1.0, 1.0, 1.0], gap="small")
with control_cols[0]:
    mode_value = st.selectbox(
        t("mode"),
        options=["grid", "factory"],
        index=0 if current_profile == "grid" else 1,
        key="cc_mode",
        help=t("tooltip_mode"),
    )
with control_cols[1]:
    horizon_value = int(
        st.selectbox(
            t("forecast_horizon"),
            options=[24, 48, 72, 168],
            index=[24, 48, 72, 168].index(current_horizon) if current_horizon in [24, 48, 72, 168] else 2,
            key="cc_horizon",
            help=t("tooltip_horizon"),
        )
    )
with control_cols[2]:
    train_clicked = st.button(t("train_retrain_model"), use_container_width=True)
with control_cols[3]:
    run_forecast_clicked = st.button(t("run_forecast"), use_container_width=True)
with control_cols[4]:
    detect_anomalies_clicked = st.button(t("detect_anomalies"), use_container_width=True)
with control_cols[5]:
    refresh_clicked = st.button(t("refresh_dashboard"), use_container_width=True)

st.session_state["selected_profile"] = mode_value
st.session_state["selected_horizon"] = horizon_value

if train_clicked:
    execute_training_flow(mode_value, t)
    st.success(t("train_completed_success"))
    st.rerun()

if run_forecast_clicked:
    progress = st.progress(0, text=t("loading_datasets"))
    with st.spinner(t("forecast_spinner")):
        progress.progress(35, text=t("feature_engineering"))
        forecast_config = prepare_config(mode_value)
        forecast_config.forecast_horizon = int(horizon_value)
        progress.progress(70, text=t("run_forecast"))
        aerix_main.run_single_pipeline(BASE_DIR, forecast_config, emit_report=False, emit_plots=True)
        progress.progress(100, text=t("training_completed"))
    st.session_state["refresh_id"] += 1
    st.success(t("forecast_completed_success"))
    st.rerun()

if detect_anomalies_clicked:
    with st.spinner(t("anomaly_spinner")):
        anomaly_config = prepare_config(mode_value)
        anomaly_df = aerix_main.load_and_preprocess(anomaly_config)
        anomaly_result = run_anomaly_detection(anomaly_df, output_path=OUTPUTS_DIR / "anomalies.png")
        st.session_state["last_anomaly_result"] = anomaly_result
    st.session_state["refresh_id"] += 1
    st.success(t("anomalies_completed_success", count=len(anomaly_result.get("timestamps", []))))
    st.rerun()

if refresh_clicked:
    st.session_state["refresh_id"] += 1
    st.rerun()

status_registry_path = resolve_registry_path(mode_value)
status_mtime = status_registry_path.stat().st_mtime if status_registry_path.exists() else 0.0
status_entries = load_registry_entries(str(status_registry_path), status_mtime)
status_latest = status_entries[-1] if status_entries else {}
status_ts = pd.to_datetime(status_latest.get("timestamp"), errors="coerce")
status_ts_str = status_ts.strftime("%Y-%m-%d %H:%M") if pd.notna(status_ts) else t("na")
status_dataset_size = status_latest.get("training_dataset_size")
status_datasets_count = len(list((BASE_DIR / "data").glob("grid_*.csv"))) if mode_value == "grid" else 1

st.markdown(f"**{t('status_panel')}**")
status_cols = st.columns(6)
with status_cols[0]:
    st.metric(t("current_best_model"), str(status_latest.get("model_name") or t("na")))
with status_cols[1]:
    mae_value = _safe_float(status_latest.get("MAE"))
    st.metric(t("current_mae"), f"{mae_value:.3f}" if mae_value is not None else t("na"))
with status_cols[2]:
    rmse_value = _safe_float(status_latest.get("RMSE"))
    st.metric(t("current_rmse"), f"{rmse_value:.3f}" if rmse_value is not None else t("na"))
with status_cols[3]:
    if status_dataset_size is None:
        st.metric(t("dataset_size"), t("na"))
    else:
        st.metric(t("dataset_size"), f"{int(status_dataset_size):,}".replace(",", " "))
with status_cols[4]:
    st.metric(t("number_of_datasets"), f"{status_datasets_count}")
with status_cols[5]:
    st.metric(t("last_training_timestamp"), status_ts_str)
st.markdown("</div>", unsafe_allow_html=True)
st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("ai_model_training"))
train_cols = st.columns([1.2, 1.1, 1.3], gap="small")
with train_cols[0]:
    selected_training_model = st.selectbox(
        t("model_type"),
        options=["RandomForest", "LightGBM", "LinearRegression"],
        index=["RandomForest", "LightGBM", "LinearRegression"].index(
            st.session_state.get("selected_training_model", "RandomForest")
        ),
        key="training_model_selector",
        help=t("tooltip_model_type"),
    )
with train_cols[1]:
    train_model_clicked = st.button(
        t("train_model"),
        use_container_width=True,
        help=t("tooltip_train_model"),
    )
with train_cols[2]:
    st.info(t("model_type_note"))

st.session_state["selected_training_model"] = selected_training_model

if train_model_clicked:
    train_summary = execute_training_flow(mode_value, t)
    st.session_state["last_training_metrics"] = train_summary | {"requested_model": selected_training_model}
    st.success(t("train_completed_success"))
    st.rerun()

last_train_metrics = st.session_state.get("last_training_metrics")
if isinstance(last_train_metrics, dict):
    metrics_cols = st.columns(4)
    with metrics_cols[0]:
        st.metric(t("model_type"), str(last_train_metrics.get("requested_model") or t("na")))
    with metrics_cols[1]:
        mae_metric = _safe_float(last_train_metrics.get("mae"))
        st.metric(t("mae_label"), f"{mae_metric:.6f}" if mae_metric is not None else t("na"))
    with metrics_cols[2]:
        rmse_metric = _safe_float(last_train_metrics.get("rmse"))
        st.metric(t("rmse_label"), f"{rmse_metric:.6f}" if rmse_metric is not None else t("na"))
    with metrics_cols[3]:
        duration_metric = _safe_float(last_train_metrics.get("duration_sec"))
        st.metric(t("training_duration"), f"{duration_metric:.2f}s" if duration_metric is not None else t("na"))
st.markdown("</div>", unsafe_allow_html=True)
st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

with st.sidebar:
    st.header(t("sidebar_system_control"))
    selected_profile = st.selectbox(
        t("dataset_selector"),
        options=["grid", "factory"],
        index=0 if st.session_state.get("selected_profile", "grid") == "grid" else 1,
        format_func=lambda profile: profile_label(profile, st.session_state.get("selected_language", DEFAULT_LANGUAGE)),
        help=t("mode_explainer"),
    )
    st.session_state["selected_profile"] = selected_profile

    run_clicked = st.button(t("run_model_button"), type="primary", use_container_width=True)

    if run_clicked:
        progress = st.progress(0, text=t("loading_datasets"))
        phases = [
            (t("running_automl"), 20),
            (t("hyperparameter_tuning"), 45),
            (t("evaluating_candidates"), 72),
            (t("saving_best_model"), 95),
        ]
        for title, pct in phases:
            progress.progress(pct, text=title)
            time.sleep(0.25)

        with st.spinner(t("training_spinner")):
            try:
                run_result = run_model_subprocess(selected_profile)
                progress.progress(100, text=t("training_completed"))
                st.session_state["last_run_result"] = run_result
                st.session_state["selected_profile"] = selected_profile
                st.session_state["refresh_id"] += 1
                st.rerun()
            except subprocess.TimeoutExpired:
                progress.progress(100, text=t("status_error"))
                st.session_state["last_run_result"] = RunResult(
                    returncode=124,
                    stdout="",
                    stderr=f"Execution timeout exceeded: {RUN_TIMEOUT_SECONDS} seconds.",
                    duration_sec=float(RUN_TIMEOUT_SECONDS),
                )
                st.session_state["selected_profile"] = selected_profile
                st.rerun()

# Always render dashboard for current selection.
selected_profile = st.session_state.get("selected_profile", "grid")
selected_horizon = int(st.session_state.get("selected_horizon", 72))
selected_dataset_override = profile_to_dataset(selected_profile)

auto_retrain_enabled = True
auto_retrain_interval = 24
try:
    runtime_cfg = prepare_config(selected_profile)
    auto_retrain_enabled = bool(getattr(runtime_cfg, "enable_auto_retrain", True))
    auto_retrain_interval = int(getattr(runtime_cfg, "auto_retrain_interval_hours", 24))
except Exception:
    auto_retrain_enabled = True
    auto_retrain_interval = 24

if auto_retrain_enabled:
    try:
        auto_retrain_result = run_auto_retrain_cycle(
            base_dir=BASE_DIR,
            dataset_override=selected_dataset_override,
            interval_hours=auto_retrain_interval,
            force=False,
        )
        st.session_state["last_auto_retrain_result"] = auto_retrain_result
    except Exception as auto_exc:
        st.session_state["last_auto_retrain_result"] = {
            "status": "failed",
            "reason": str(auto_exc),
            "last_cycle_at": None,
        }

try:
    with st.spinner(t("dashboard_load_spinner")):
        data = build_dashboard_data(selected_profile, st.session_state["refresh_id"], selected_horizon)
except Exception as exc:
    st.error(t("dashboard_load_error", error=exc))
    last_run = st.session_state.get("last_run_result")
    if last_run is not None:
        render_run_details_menu(last_run)
    st.stop()

config = data["config"]
dataset_summary = data["dataset_summary"]
model_results = data["model_results"]
peak_results = data["peak_results"]
optimization_results = data["optimization_results"]
systems_count = dataset_summary.grid_systems_count or 1

registry_path = resolve_registry_path(selected_profile)
registry_mtime = registry_path.stat().st_mtime if registry_path.exists() else 0.0
registry_entries = load_registry_entries(str(registry_path), registry_mtime)
registry_latest = registry_entries[-1] if registry_entries else {}

automl_trials_path = OUTPUTS_DIR / "automl_trials.json"
automl_trials_mtime = automl_trials_path.stat().st_mtime if automl_trials_path.exists() else 0.0
automl_trials_payload = load_automl_trials(str(automl_trials_path), automl_trials_mtime)

activity_log_path = BASE_DIR / "logs" / "training_activity.log"
activity_mtime = activity_log_path.stat().st_mtime if activity_log_path.exists() else 0.0
activity_entries = load_activity_entries(str(activity_log_path), activity_mtime, limit=25)
auto_retrain_status = load_auto_retrain_status(BASE_DIR)
dataset_registry_path = BASE_DIR / "data" / "dataset_registry.json"
dataset_registry_mtime = dataset_registry_path.stat().st_mtime if dataset_registry_path.exists() else 0.0
dataset_registry_entries = load_dataset_registry_entries(str(dataset_registry_path), dataset_registry_mtime)
dataset_health_metrics = load_dataset_health_metrics(
    training_pool_path=str(BASE_DIR / "data" / "training_pool" / "global_training_pool.csv"),
    baseline_path=str(BASE_DIR / "data" / "grid_training_pool.csv"),
    refresh_id=st.session_state["refresh_id"],
)

self_learning = build_self_learning_summary(
    registry_entries=registry_entries,
    profile=selected_profile,
    systems_count=systems_count,
    fallback_model_name=model_results.selected_model_name,
    fallback_mae=float(model_results.metrics_selected["mae"]),
)

energy_map_df = build_energy_map_dataframe(
    clean_df=data["clean_df"],
    forecast_df=data["forecast_df"],
    peak_threshold=peak_results.threshold,
)
energy_map_fig = build_energy_map_figure(energy_map_df)
dataset_explorer_df = build_dataset_explorer(selected_profile, st.session_state["refresh_id"])
top_features_df = load_top_feature_ranking(Path(config.best_model_path))

equipment_df = load_equipment_cached(st.session_state["refresh_id"])
_ensure_machine_editor_state(equipment_df)
price_df = load_energy_price_cached(st.session_state["refresh_id"])
plant_graph = build_plant_graph(equipment_df)
plant_graph_fig = build_plant_graph_figure(plant_graph)

industrial_plan = generate_optimization_plan(
    forecast_df=data["forecast_df"],
    equipment_df=equipment_df,
    peak_threshold=float(peak_results.threshold),
    price_df=price_df,
    graph=plant_graph,
)
industrial_plan_cost = optimize_for_cost(industrial_plan, price_df=price_df)
industrial_optimized = apply_optimization_plan(data["forecast_df"], industrial_plan_cost)
industrial_summary = summarize_optimization(
    original_df=data["forecast_df"],
    optimized_df=industrial_optimized,
    co2_factor=float(config.co2_factor),
    price_df=price_df,
    default_price=float(config.price_per_mwh_rub),
)
industrial_cost_summary = summarize_costs(
    original_df=data["forecast_df"],
    optimized_df=industrial_optimized,
    price_df=price_df,
    default_price=float(config.price_per_mwh_rub),
)

baseline_scenario_result = run_scenario(
    baseline_forecast=data["forecast_df"],
    equipment_df=equipment_df,
    energy_price_df=price_df,
    params={},
    graph=plant_graph,
    co2_factor=float(config.co2_factor),
    default_price=float(config.price_per_mwh_rub),
)

st.caption(
    t(
        "selected_model_caption",
        model=model_results.selected_model_name,
        mae=model_results.metrics_selected["mae"],
        rmse=model_results.metrics_selected["rmse"],
    )
)

with st.sidebar:
    st.markdown("---")
    st.subheader(t("system_info"))
    mode_label = profile_label(config.mode if config.mode in {"grid", "factory"} else selected_profile, st.session_state.get("selected_language", DEFAULT_LANGUAGE))

    st.markdown(
        f"<div class='aerix-inline-kv'><b>{t('mode_label')}:</b> {mode_label}<br>"
        f"<b>{t('systems_count')}:</b> {systems_count}<br>"
        f"<b>{t('dataset_period')}:</b><br>{dataset_summary.start_timestamp} → {dataset_summary.end_timestamp}</div>",
        unsafe_allow_html=True,
    )

    last_run = st.session_state.get("last_run_result")
    if last_run is not None:
        render_run_details_menu(last_run)

# KPI row
kpi_cols = st.columns(4)
with kpi_cols[0]:
    st.metric(
        t("kpi_peak_reduction_pct"),
        f"{optimization_results.peak_reduction_percent:,.2f}%",
        help=t("tooltip_peak_load"),
    )
with kpi_cols[1]:
    st.metric(
        t("kpi_mw_reduced"),
        f"{fmt_num(optimization_results.peak_reduction_mw)}",
        help=t("tooltip_optimization_plan"),
    )
with kpi_cols[2]:
    st.metric(
        t("kpi_savings"),
        format_rub(optimization_results.cost_savings_rub),
        help=t("tooltip_energy_cost_impact"),
    )
with kpi_cols[3]:
    st.metric(t("kpi_co2"), f"{fmt_num(optimization_results.co2_reduction)}")

st.markdown("<div style='height:0.45rem;'></div>", unsafe_allow_html=True)

# Industrial Energy Control
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("industrial_control"))

if equipment_df.empty:
    st.info(t("equipment_unavailable"))
else:
    editor_base_df = st.session_state["equipment_editor_df"].copy()
    equipment_editor = st.data_editor(
        editor_base_df[
            ["machine_id", "machine_type", "power_mw", "priority", "flexibility", "availability"]
        ],
        use_container_width=True,
        hide_index=True,
        disabled=["machine_id", "machine_type", "power_mw", "priority", "flexibility"],
        key="industrial_equipment_editor",
    )

    if st.button(t("save_equipment_state"), key="save_equipment_availability"):
        updated = st.session_state["equipment_editor_df"].copy()
        availability_map = {
            str(row.machine_id): bool(row.availability)
            for row in equipment_editor[["machine_id", "availability"]].itertuples(index=False)
        }
        updated["availability"] = updated["machine_id"].astype(str).map(availability_map).fillna(
            updated["availability"]
        )
        updated["availability"] = updated["availability"].astype(bool)
        save_equipment_state(updated, BASE_DIR / "data" / "machines_state.json")
        st.session_state["equipment_editor_df"] = updated
        st.session_state["refresh_id"] += 1
        st.success(t("equipment_saved"))
        st.rerun()

recommendation_cols = [
    "timestamp",
    "machine_id",
    "action",
    "power_impact_mw",
    "reason",
    "confidence",
    "energy_price",
    "cost_impact",
    "economic_reason",
]
if industrial_plan_cost.empty:
    st.info(t("no_optimization_actions"))
else:
    st.markdown(f"**{t('optimization_recommendations')}**")
    present_cols = [column for column in recommendation_cols if column in industrial_plan_cost.columns]
    st.dataframe(industrial_plan_cost[present_cols], use_container_width=True, hide_index=True)

if st.button(t("apply_optimization"), key="apply_industrial_optimization", help=t("tooltip_optimization_plan")):
    st.session_state["industrial_apply_requested"] = True

if st.session_state.get("industrial_apply_requested", False):
    summary_cols = st.columns(4)
    with summary_cols[0]:
        st.metric(t("peak_before"), f"{round_float(industrial_summary.get('original_peak', 0.0)):.6f}")
    with summary_cols[1]:
        st.metric(t("peak_after"), f"{round_float(industrial_summary.get('optimized_peak', 0.0)):.6f}")
    with summary_cols[2]:
        st.metric(
            t("energy_saved_cost"),
            format_rub(round_float(industrial_cost_summary.get("estimated_cost_savings", 0.0))),
        )
    with summary_cols[3]:
        st.metric(t("co2_reduction"), f"{round_float(industrial_summary.get('co2_reduction', 0.0)):.6f}")

    optimization_preview = go.Figure()
    optimization_preview.add_trace(
        go.Scatter(
            x=data["forecast_df"]["timestamp"],
            y=data["forecast_df"]["predicted_consumption"],
            mode="lines",
            name=t("artifact_history"),
            line=dict(color="#5A7DFF", width=2),
        )
    )
    optimization_preview.add_trace(
        go.Scatter(
            x=industrial_optimized["timestamp"],
            y=industrial_optimized["predicted_consumption"],
            mode="lines",
            name=t("badge_optimization"),
            line=dict(color="#37E39A", width=2),
        )
    )
    optimization_preview = style_plot(optimization_preview, height=320)
    optimization_preview.update_layout(title=t("peak_reduction_preview"))
    st.plotly_chart(optimization_preview, use_container_width=True)

st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Energy Cost Impact
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("energy_cost_impact"), help=t("tooltip_energy_cost_impact"))
cost_cols = st.columns(3)
with cost_cols[0]:
    st.metric(t("cost_before_opt"), format_rub(round_float(industrial_cost_summary.get("cost_before", 0.0))))
with cost_cols[1]:
    st.metric(t("cost_after_opt"), format_rub(round_float(industrial_cost_summary.get("cost_after", 0.0))))
with cost_cols[2]:
    st.metric(
        t("estimated_savings"),
        format_rub(round_float(industrial_cost_summary.get("estimated_cost_savings", 0.0))),
    )
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Optimization Explanation
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("optimization_explanation"), help=t("tooltip_optimization_plan"))
if industrial_plan_cost.empty:
    st.info(t("no_explanation"))
else:
    explain_columns = ["machine_id", "action", "reason", "confidence", "economic_reason"]
    explain_columns = [column for column in explain_columns if column in industrial_plan_cost.columns]
    st.dataframe(industrial_plan_cost[explain_columns], use_container_width=True, hide_index=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Energy Grid Map
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("energy_grid_map"))
st.plotly_chart(energy_map_fig, use_container_width=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Simulation mode
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("energy_system_simulation"), help=t("tooltip_scenario_simulation"))
sim_ctrl_cols = st.columns([1, 1, 1], gap="large")
with sim_ctrl_cols[0]:
    sim_peak_reduction = st.slider(t("peak_reduction_slider"), min_value=5, max_value=30, value=15, step=1)
with sim_ctrl_cols[1]:
    sim_load_shift = st.slider(t("load_shift_slider"), min_value=0, max_value=25, value=10, step=1)
with sim_ctrl_cols[2]:
    run_sim_clicked = st.button(t("run_simulation"), use_container_width=True)

if run_sim_clicked or "simulation_result" not in st.session_state:
    st.session_state["simulation_result"] = simulate_system(
        forecast=data["forecast_df"]["predicted_consumption"],
        peak_threshold=peak_results.threshold,
        peak_reduction_percent=float(sim_peak_reduction) / 100.0,
        load_shift_percent=float(sim_load_shift) / 100.0,
        price_per_mwh=config.price_per_mwh_rub,
        co2_factor=config.co2_factor,
    )

simulation_result = st.session_state.get("simulation_result", {})
sim_metrics = st.columns(3)
with sim_metrics[0]:
    st.metric(
        t("sim_peak_load"),
        f"{simulation_result.get('simulated_peak_load', 0.0):,.2f}".replace(",", " "),
    )
with sim_metrics[1]:
    st.metric(
        t("sim_savings"),
        format_rub(float(simulation_result.get("simulated_savings", 0.0))),
    )
with sim_metrics[2]:
    st.metric(
        t("sim_co2"),
        f"{float(simulation_result.get('simulated_co2_reduction', 0.0)):.2f}",
    )

sim_chart = go.Figure()
orig_series = simulation_result.get("original_series", pd.Series(dtype=float))
opt_series = simulation_result.get("optimized_series", pd.Series(dtype=float))
sim_x = list(range(len(orig_series)))
sim_chart.add_trace(
    go.Scatter(
        x=sim_x,
        y=orig_series,
        mode="lines",
        name=t("artifact_history"),
        line=dict(color="#5A7DFF", width=2),
    )
)
sim_chart.add_trace(
    go.Scatter(
        x=list(range(len(opt_series))),
        y=opt_series,
        mode="lines",
        name=t("badge_optimization"),
        line=dict(color="#37E39A", width=2),
    )
)
sim_chart = style_plot(sim_chart, height=320)
sim_chart.update_layout(title=t("sim_chart_title"))
st.plotly_chart(sim_chart, use_container_width=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Scenario Lab
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("scenario_lab"), help=t("tooltip_scenario_simulation"))

active_equipment_df = st.session_state.get("equipment_editor_df", equipment_df).copy()
machine_ids = active_equipment_df["machine_id"].astype(str).tolist() if not active_equipment_df.empty else []

scenario_ctrl_cols = st.columns([1.1, 1.1, 1.1, 1.1], gap="large")
with scenario_ctrl_cols[0]:
    scenario_price_multiplier = st.slider(
        t("energy_price_multiplier"),
        min_value=0.50,
        max_value=2.00,
        value=1.00,
        step=0.05,
    )
with scenario_ctrl_cols[1]:
    scenario_disabled = st.multiselect(
        t("machine_disable_list"),
        options=machine_ids,
        default=[],
    )
with scenario_ctrl_cols[2]:
    scenario_additional_load = st.number_input(
        t("additional_load_mw"),
        min_value=-50.0,
        max_value=200.0,
        value=0.0,
        step=1.0,
    )
with scenario_ctrl_cols[3]:
    run_scenario_clicked = st.button(t("run_scenario"), use_container_width=True)

if "scenario_shift_editor_df" not in st.session_state or set(st.session_state["scenario_shift_editor_df"]["machine_id"]) != set(machine_ids):
    st.session_state["scenario_shift_editor_df"] = pd.DataFrame(
        {"machine_id": machine_ids, "shift_hours": [0 for _ in machine_ids]}
    )

st.markdown(f"**{t('shift_overrides')}**")
shift_editor_df = st.data_editor(
    st.session_state["scenario_shift_editor_df"],
    use_container_width=True,
    hide_index=True,
    column_config={
        "machine_id": st.column_config.TextColumn(disabled=True),
        "shift_hours": st.column_config.NumberColumn(min_value=-6, max_value=6, step=1),
    },
    key="scenario_shift_overrides_editor",
)
st.session_state["scenario_shift_editor_df"] = shift_editor_df.copy()

if run_scenario_clicked or "scenario_lab_result" not in st.session_state:
    shift_overrides = {
        str(row.machine_id): int(row.shift_hours)
        for row in shift_editor_df.itertuples(index=False)
        if int(row.shift_hours) != 0
    }
    scenario_params = {
        "energy_price_multiplier": float(scenario_price_multiplier),
        "machine_disable_list": [str(machine_id) for machine_id in scenario_disabled],
        "machine_shift_overrides": shift_overrides,
        "additional_load_mw": float(scenario_additional_load),
    }
    with st.spinner(t("scenario_spinner")):
        scenario_result = run_scenario(
            baseline_forecast=data["forecast_df"],
            equipment_df=active_equipment_df,
            energy_price_df=price_df,
            params=scenario_params,
            graph=plant_graph,
            co2_factor=float(config.co2_factor),
            default_price=float(config.price_per_mwh_rub),
        )
        scenario_delta = compare_scenarios(base_result=baseline_scenario_result, scenario_result=scenario_result)
    st.session_state["scenario_lab_result"] = scenario_result
    st.session_state["scenario_lab_delta"] = scenario_delta

scenario_result = st.session_state.get("scenario_lab_result", baseline_scenario_result)
scenario_delta = st.session_state.get("scenario_lab_delta", {"peak_delta": 0.0, "cost_delta": 0.0, "co2_delta": 0.0})

scenario_cards = st.columns(3)
with scenario_cards[0]:
    st.metric(t("peak_delta"), f"{round_float(scenario_delta.get('peak_delta', 0.0)):.6f}")
with scenario_cards[1]:
    st.metric(t("cost_delta"), format_rub(round_float(scenario_delta.get("cost_delta", 0.0))))
with scenario_cards[2]:
    st.metric(t("co2_delta"), f"{round_float(scenario_delta.get('co2_delta', 0.0)):.6f}")

scenario_forecast_df = scenario_result.get("scenario_forecast", pd.DataFrame(columns=["timestamp", "predicted_consumption"]))
scenario_compare_fig = go.Figure()
scenario_compare_fig.add_trace(
    go.Scatter(
        x=data["forecast_df"]["timestamp"],
        y=data["forecast_df"]["predicted_consumption"],
        mode="lines",
        name=t("artifact_history"),
        line=dict(color="#5A7DFF", width=2),
    )
)
scenario_compare_fig.add_trace(
    go.Scatter(
        x=scenario_forecast_df.get("timestamp", pd.Series(dtype="datetime64[ns]")),
        y=scenario_forecast_df.get("predicted_consumption", pd.Series(dtype=float)),
        mode="lines",
        name=t("scenario_lab"),
        line=dict(color="#FF9F43", width=2),
    )
)
scenario_compare_fig = style_plot(scenario_compare_fig, height=330)
scenario_compare_fig.update_layout(title=t("scenario_compare_title"))
st.plotly_chart(scenario_compare_fig, use_container_width=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Machine Telemetry
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("machine_telemetry"))

if hasattr(st, "fragment"):

    @st.fragment(run_every="3s")
    def _telemetry_fragment() -> None:
        telemetry_df = stream_machine_telemetry(active_equipment_df, seed=None)
        anomalies_df = detect_machine_anomalies(telemetry_df)
        telemetry_display = telemetry_df.copy()
        anomaly_ids = set(anomalies_df["machine_id"].tolist()) if not anomalies_df.empty else set()
        telemetry_display["anomaly_flag"] = telemetry_display["machine_id"].map(
            lambda machine_id: "⚠" if str(machine_id) in anomaly_ids else ""
        )
        st.dataframe(telemetry_display, use_container_width=True, hide_index=True)

        telemetry_fig = go.Figure()
        telemetry_fig.add_trace(
            go.Bar(
                x=telemetry_display["machine_id"],
                y=telemetry_display["current_load_mw"],
                marker_color=["#FF5F77" if machine_id in anomaly_ids else "#37E39A" for machine_id in telemetry_display["machine_id"]],
                name=t("kpi_mw_reduced"),
            )
        )
        telemetry_fig = style_plot(telemetry_fig, height=300)
        telemetry_fig.update_layout(title=t("machine_telemetry"))
        st.plotly_chart(telemetry_fig, use_container_width=True)

        if anomalies_df.empty:
            st.caption(t("telemetry_anomalies_none"))
        else:
            st.markdown(f"**{t('telemetry_anomalies')}**")
            st.dataframe(anomalies_df, use_container_width=True, hide_index=True)

    _telemetry_fragment()
else:
    st.info(t("auto_refresh_unavailable"))
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Plant Energy Graph
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("plant_energy_graph"))
st.plotly_chart(plant_graph_fig, use_container_width=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Equipment Explorer
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("equipment_explorer"))
if active_equipment_df.empty:
    st.info(t("no_equipment_data"))
else:
    filtered_equipment_df = _render_equipment_filters(active_equipment_df, t)
    display_columns = ["machine_id", "machine_type", "power_mw", "priority", "flexibility", "availability"]
    st.dataframe(filtered_equipment_df[display_columns], use_container_width=True, hide_index=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Model intelligence
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("model_intelligence"))
mi_cols = st.columns([1, 1], gap="large")
with mi_cols[0]:
    if top_features_df.empty:
        st.info(t("top_features_unavailable"))
    else:
        st.markdown(f"**{t('top_features')}**")
        st.dataframe(top_features_df, use_container_width=True, hide_index=True)
with mi_cols[1]:
    shap_importance_path = OUTPUTS_DIR / "shap_feature_importance.png"
    shap_mtime = shap_importance_path.stat().st_mtime if shap_importance_path.exists() else 0.0
    shap_bytes = load_image_bytes(str(shap_importance_path), shap_mtime)
    if shap_bytes is not None:
        st.image(shap_bytes, caption=t("shap_feature_ranking"), use_container_width=True)
    else:
        st.info(t("shap_not_found"))
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Training evolution
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("model_improvement"))
training_history_df = self_learning["history_df"].copy()
if not training_history_df.empty:
    evolution_fig = go.Figure()
    evolution_fig.add_trace(
        go.Scatter(
            x=training_history_df["timestamp"],
            y=training_history_df["MAE"],
            mode="lines+markers",
            name="MAE",
            line=dict(color="#00E5FF", width=2),
            marker=dict(size=7, color="#8F6BFF"),
        )
    )
    evolution_fig = style_plot(evolution_fig, height=320)
    evolution_fig.update_layout(title=t("training_evolution"))
    st.plotly_chart(evolution_fig, use_container_width=True)
else:
    st.info(t("training_history_unavailable"))
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# System health
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("system_health"))
health_cols = st.columns(4)
model_loaded = Path(config.best_model_path).exists()
api_ok = is_api_running()
ingestion_ok = bool(getattr(config, "enable_data_ingestion_scan", False))
monitoring_path = BASE_DIR / "models" / "monitoring_metrics.json"
monitoring_ok = False
if monitoring_path.exists():
    try:
        payload = json.loads(monitoring_path.read_text(encoding="utf-8"))
        monitoring_ok = isinstance(payload, list) and len(payload) > 0
    except Exception:
        monitoring_ok = False

status_meta = [
    (t("model_loaded"), model_loaded),
    (t("api_running"), api_ok),
    (t("data_ingestion_active"), ingestion_ok),
    (t("monitoring_active"), monitoring_ok),
]

for col, (label, state) in zip(health_cols, status_meta):
    if state:
        color = "#37E39A"
        icon = "🟢"
        status_text = t("status_ok")
    elif label in {t("model_loaded"), t("api_running")}:
        color = "#FF5F77"
        icon = "🔴"
        status_text = t("status_error")
    else:
        color = "#FFD166"
        icon = "🟡"
        status_text = t("status_warning")
    col.markdown(
        f"<span style='color:{color};font-weight:700'>{icon} {label}: {status_text}</span>",
        unsafe_allow_html=True,
    )

st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Self-learning section
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("ai_self_learning"))

if st.button(t("run_self_learning_cycle"), key="run_self_learning_cycle_btn", use_container_width=True):
    with st.spinner(t("auto_retrain_spinner")):
        forced_cycle = run_auto_retrain_cycle(
            base_dir=BASE_DIR,
            dataset_override=selected_dataset_override,
            interval_hours=24,
            force=True,
        )
    st.session_state["last_auto_retrain_result"] = forced_cycle
    st.session_state["refresh_id"] += 1
    st.rerun()

last_cycle = auto_retrain_status.get("last_cycle", {}) if isinstance(auto_retrain_status, dict) else {}
if not isinstance(last_cycle, dict):
    last_cycle = {}
ingestion_snapshot = last_cycle.get("ingestion", {}) if isinstance(last_cycle.get("ingestion"), dict) else {}
retraining_snapshot = last_cycle.get("retraining", {}) if isinstance(last_cycle.get("retraining"), dict) else {}

self_learning_kpis = st.columns(6)
with self_learning_kpis[0]:
    st.metric(t("datasets_discovered"), f"{int(ingestion_snapshot.get('datasets_discovered', 0))}")
with self_learning_kpis[1]:
    st.metric(t("datasets_accepted"), f"{int(ingestion_snapshot.get('datasets_accepted', 0))}")
with self_learning_kpis[2]:
    st.metric(t("datasets_rejected"), f"{int(ingestion_snapshot.get('datasets_rejected', 0))}")
with self_learning_kpis[3]:
    st.metric(
        t("dataset_quality_score"),
        f"{float(ingestion_snapshot.get('dataset_quality_score', 0.0)):.3f}",
    )
with self_learning_kpis[4]:
    st.metric(t("training_pool_size"), f"{int(ingestion_snapshot.get('training_pool_size', 0))}")
with self_learning_kpis[5]:
    last_retrain_ts = (
        retraining_snapshot.get("started_at")
        or last_cycle.get("last_cycle_at")
        or t("na")
    )
    st.metric(t("last_retraining_time"), str(last_retrain_ts))

sl_cols = st.columns(4)
with sl_cols[0]:
    st.metric(t("last_training"), self_learning["last_training_ts"])
    st.metric(t("current_best_model"), self_learning["current_best_model"])
with sl_cols[1]:
    ds_size = self_learning["training_dataset_size"] or ingestion_snapshot.get("training_pool_size")
    st.metric(t("dataset_train_size"), f"{ds_size:,}".replace(",", " ") if ds_size else t("na"))
    st.metric(
        t("datasets_used"),
        f"{int(ingestion_snapshot.get('dataset_count', self_learning['datasets_used']))}",
    )
with sl_cols[2]:
    current_mae = self_learning["current_mae"]
    previous_mae = self_learning["previous_mae"]
    improvement_pct = self_learning["improvement_pct"]
    st.metric(t("current_mae"), f"{current_mae:.3f}" if current_mae is not None else t("na"))
    st.metric(t("previous_mae"), f"{previous_mae:.3f}" if previous_mae is not None else t("na"))
    st.metric(
        t("improvement"),
        f"{improvement_pct:.2f}%" if improvement_pct is not None else t("na"),
    )
with sl_cols[3]:
    cycle_status = str(last_cycle.get("status", t("self_learning_idle")))
    cycle_reason = str(last_cycle.get("reason", ""))
    st.metric(t("cycle_status"), cycle_status)
    st.caption(cycle_reason if cycle_reason else t("self_learning_idle"))

history_df = self_learning["history_df"]
if not history_df.empty:
    history_fig = go.Figure()
    history_fig.add_trace(
        go.Scatter(
            x=history_df["timestamp"],
            y=history_df["MAE"],
            mode="lines+markers",
            name="MAE",
            line=dict(color="#00E5FF", width=2),
            marker=dict(size=7, color="#8F6BFF"),
            customdata=history_df["model_name"],
            hovertemplate=f"{t('last_training')}: %{{x}}<br>MAE: %{{y:.3f}}<br>{t('model_type')}: %{{customdata}}<extra></extra>",
        )
    )
    history_fig = style_plot(history_fig, height=320)
    history_fig.update_layout(title=t("model_improvement"))
    st.plotly_chart(history_fig, use_container_width=True)
else:
    st.info(t("history_unavailable"))

st.markdown(f"**{t('training_activity_log')}**")
if activity_entries:
    activity_df = pd.DataFrame(activity_entries)
    activity_df = activity_df.rename(columns={"timestamp": "timestamp", "event": "event", "details": "details"})
    st.dataframe(activity_df, use_container_width=True, hide_index=True)
else:
    st.caption(t("training_events_empty"))

st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("training_activity_log"))
recent_lines = read_recent_activity(str(activity_log_path), limit=50)
if recent_lines:
    log_df = pd.DataFrame({"log": recent_lines})
    st.dataframe(log_df, use_container_width=True, hide_index=True)
else:
    st.caption(t("training_events_empty"))
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("dataset_intelligence"))

dataset_intel_cols = st.columns(6)
with dataset_intel_cols[0]:
    st.metric(t("datasets_discovered"), f"{int(ingestion_snapshot.get('datasets_discovered', 0))}")
with dataset_intel_cols[1]:
    st.metric(t("datasets_validated"), f"{int(ingestion_snapshot.get('datasets_validated', 0))}")
with dataset_intel_cols[2]:
    st.metric(t("datasets_accepted"), f"{int(ingestion_snapshot.get('datasets_accepted', 0))}")
with dataset_intel_cols[3]:
    st.metric(t("datasets_rejected"), f"{int(ingestion_snapshot.get('datasets_rejected', 0))}")
with dataset_intel_cols[4]:
    st.metric(
        t("dataset_quality_score"),
        f"{float(ingestion_snapshot.get('dataset_quality_score', 0.0)):.3f}",
    )
with dataset_intel_cols[5]:
    st.metric(t("training_pool_growth"), f"{int(ingestion_snapshot.get('appended_rows', 0))}")

source_cols = st.columns(2)
with source_cols[0]:
    st.metric(t("dataset_sources"), f"{int(ingestion_snapshot.get('dataset_count', 0))}")
with source_cols[1]:
    st.metric(t("training_pool_size"), f"{int(ingestion_snapshot.get('training_pool_size', 0))}")

health_cols = st.columns(4)
with health_cols[0]:
    st.metric(t("dataset_drift"), f"{float(dataset_health_metrics.get('dataset_drift', 0.0)):.4f}")
with health_cols[1]:
    st.metric(t("schema_drift"), str(bool(dataset_health_metrics.get("schema_drift", False))))
with health_cols[2]:
    st.metric(
        t("timestamp_gap_ratio"),
        f"{float(dataset_health_metrics.get('timestamp_gap_ratio', 0.0)):.4f}",
    )
with health_cols[3]:
    st.metric(
        t("abnormal_range_ratio"),
        f"{float(dataset_health_metrics.get('abnormal_range_ratio', 0.0)):.4f}",
    )

st.markdown(f"**{t('dataset_registry_viewer')}**")
if dataset_registry_entries:
    registry_df = pd.DataFrame(dataset_registry_entries)
    if "ingestion_timestamp" in registry_df.columns and "timestamp" not in registry_df.columns:
        registry_df["timestamp"] = registry_df["ingestion_timestamp"]
    if "quality_score" not in registry_df.columns and "score" in registry_df.columns:
        registry_df["quality_score"] = registry_df["score"]
    if "score" not in registry_df.columns and "quality_score" in registry_df.columns:
        registry_df["score"] = registry_df["quality_score"]
    display_cols = [
        "dataset_name",
        "source",
        "quality_score",
        "accepted",
        "timestamp",
    ]
    present_cols = [col for col in display_cols if col in registry_df.columns]
    registry_df = registry_df[present_cols].copy()
    rename_map = {
        "dataset_name": t("dataset_name_col"),
        "source": t("dataset_source_col"),
        "quality_score": t("dataset_score_col"),
        "accepted": t("dataset_accepted_col"),
        "timestamp": t("dataset_timestamp_col"),
    }
    registry_df = registry_df.rename(columns=rename_map)
    st.dataframe(registry_df.tail(200), use_container_width=True, hide_index=True)
else:
    st.caption(t("self_learning_idle"))

st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Main analytics layout
left_col, right_col = st.columns([1.1, 1], gap="large")

with left_col:
    st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
    st.subheader(t("model_performance"))

    perf_fig = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "xy"}, {"type": "indicator"}]],
        column_widths=[0.66, 0.34],
        horizontal_spacing=0.18,
    )
    perf_fig.add_trace(
        go.Bar(
            x=["MAE (Linear)", "MAE (RandomForest)"],
            y=[model_results.metrics_linear["mae"], model_results.metrics_rf["mae"]],
            marker_color=["#4F7BFF", "#00E5FF"],
            text=[
                f"{model_results.metrics_linear['mae']:.1f}",
                f"{model_results.metrics_rf['mae']:.1f}",
            ],
            textposition="outside",
            showlegend=False,
        ),
        row=1,
        col=1,
    )
    perf_fig.add_trace(
        go.Indicator(
            mode="number+delta",
            value=model_results.metrics_rf["mae"],
            number={"suffix": " MAE"},
            delta={
                "reference": model_results.metrics_linear["mae"],
                "relative": True,
                "valueformat": ".2%",
            },
            title={"text": "RF vs Linear"},
        ),
        row=1,
        col=2,
    )
    perf_fig = style_plot(perf_fig, height=360)
    perf_fig.update_layout(title=t("model_performance"))
    st.plotly_chart(perf_fig, use_container_width=True)

    st.markdown(
        f"**{t('improvement')} %:** <span style='color:#00E5FF; font-weight:700'>{model_results.improvement_percent:.2f}%</span>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

    st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
    st.subheader(t("forecast_ensemble"))
    ensemble_compare_df = data.get("ensemble_compare", pd.DataFrame())
    method_metrics = model_results.ensemble_method_metrics or {}
    mean_metrics = method_metrics.get("mean", {})
    weighted_metrics = method_metrics.get("weighted", {})

    base_kpis = st.columns(3)
    base_kpis[0].metric("MAE (Linear)", f"{model_results.metrics_linear['mae']:.3f}")
    base_kpis[1].metric("MAE (RandomForest)", f"{model_results.metrics_rf['mae']:.3f}")
    base_kpis[2].metric("MAE (LightGBM)", f"{model_results.metrics_lgbm['mae']:.3f}")

    ensemble_kpis = st.columns(4)
    ensemble_kpis[0].metric(
        t("ensemble_mean_mae"),
        f"{float(mean_metrics.get('mae')):.3f}" if mean_metrics.get("mae") is not None else t("na"),
    )
    ensemble_kpis[1].metric(
        t("ensemble_weighted_mae"),
        f"{float(weighted_metrics.get('mae')):.3f}" if weighted_metrics.get("mae") is not None else t("na"),
    )
    ensemble_kpis[2].metric(t("ensemble_method_selected"), str(model_results.ensemble_method_selected))
    ensemble_kpis[3].metric(t("selected_model"), str(model_results.selected_model_name))

    ensemble_meta_cols = st.columns(2)
    ensemble_meta_cols[0].caption(
        f"{t('selected_source')}: {model_results.ensemble_selected_source}"
    )
    ensemble_meta_cols[1].caption(
        f"{t('base_models')}: {', '.join(model_results.base_models or []) or t('na')}"
    )

    if not ensemble_compare_df.empty:
        ensemble_fig = go.Figure()
        ensemble_fig.add_trace(
            go.Scatter(
                x=ensemble_compare_df["timestamp"],
                y=ensemble_compare_df["actual"],
                mode="lines",
                name=t("actual_load"),
                line=dict(color="#00E5FF", width=2),
            )
        )

        if "base_best" in ensemble_compare_df.columns and ensemble_compare_df["base_best"].notna().any():
            ensemble_fig.add_trace(
                go.Scatter(
                    x=ensemble_compare_df["timestamp"],
                    y=ensemble_compare_df["base_best"],
                    mode="lines",
                    name=t("base_best_prediction"),
                    line=dict(color="#4F7BFF", width=1.5, dash="dot"),
                )
            )

        if "ensemble" in ensemble_compare_df.columns and ensemble_compare_df["ensemble"].notna().any():
            ensemble_fig.add_trace(
                go.Scatter(
                    x=ensemble_compare_df["timestamp"],
                    y=ensemble_compare_df["ensemble"],
                    mode="lines",
                    name=t("ensemble_prediction"),
                    line=dict(color="#8F6BFF", width=2),
                )
            )

        ensemble_fig.add_trace(
            go.Scatter(
                x=ensemble_compare_df["timestamp"],
                y=ensemble_compare_df["selected"],
                mode="lines",
                name=t("selected_prediction"),
                line=dict(color="#37E39A", width=2),
            )
        )
        ensemble_fig = style_plot(ensemble_fig, height=360)
        ensemble_fig.update_layout(title=t("ensemble_comparison_chart"))
        st.plotly_chart(ensemble_fig, use_container_width=True)
    else:
        st.caption(t("history_unavailable"))

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

    st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
    st.subheader(t("automl_search"))

    trials_payload = automl_trials_payload if isinstance(automl_trials_payload, dict) else {}
    trials_raw = trials_payload.get("trials", [])
    if not isinstance(trials_raw, list):
        trials_raw = []

    trial_df = pd.DataFrame([row for row in trials_raw if isinstance(row, dict)])
    if not trial_df.empty:
        if "iteration" in trial_df.columns:
            trial_df["iteration"] = pd.to_numeric(trial_df["iteration"], errors="coerce")
        if "validation_mae" in trial_df.columns:
            trial_df["validation_mae"] = pd.to_numeric(trial_df["validation_mae"], errors="coerce")
        if "validation_rmse" in trial_df.columns:
            trial_df["validation_rmse"] = pd.to_numeric(trial_df["validation_rmse"], errors="coerce")

    evaluated_df = trial_df.copy()
    if not evaluated_df.empty:
        if "status" in evaluated_df.columns:
            evaluated_df = evaluated_df[evaluated_df["status"].astype(str) == "evaluated"]
        required_cols = [col for col in ["iteration", "validation_mae"] if col in evaluated_df.columns]
        if len(required_cols) < 2:
            evaluated_df = pd.DataFrame(columns=["iteration", "validation_mae"])
        else:
            evaluated_df = evaluated_df.dropna(subset=["iteration", "validation_mae"]).sort_values("iteration")

    best_trial = trials_payload.get("best_trial")
    if not isinstance(best_trial, dict):
        best_trial = {}

    trials_count = int(
        trials_payload.get("trial_count")
        or registry_latest.get("automl_trials")
        or len(trials_raw)
        or 0
    )

    best_model_name = (
        str(best_trial.get("candidate_id"))
        if best_trial.get("candidate_id")
        else str(best_trial.get("model_name") or registry_latest.get("model_name") or t("na"))
    )
    best_params = best_trial.get("hyperparameters")
    if not isinstance(best_params, dict):
        best_params = registry_latest.get("best_trial_params")
    if not isinstance(best_params, dict):
        best_params = {}

    best_mae = _safe_float(best_trial.get("validation_mae"))
    if best_mae is None and not evaluated_df.empty:
        best_mae = _safe_float(evaluated_df["validation_mae"].min())
    if best_mae is None:
        best_mae = _safe_float(registry_latest.get("MAE"))

    automl_kpis = st.columns(4)
    automl_kpis[0].metric(t("automl_trials_count"), f"{trials_count}")
    automl_kpis[1].metric(t("automl_best_model"), best_model_name)
    automl_kpis[2].metric(
        t("automl_best_mae"),
        f"{best_mae:.6f}" if best_mae is not None else t("na"),
    )
    automl_kpis[3].metric(
        t("automl_best_params"),
        str(len(best_params)) if best_params else t("na"),
    )

    if best_params:
        st.caption(f"{t('automl_best_params')}: `{json.dumps(best_params, ensure_ascii=False, sort_keys=True)}`")

    if evaluated_df.empty:
        st.info(t("automl_unavailable"))
    else:
        automl_fig = go.Figure()
        automl_fig.add_trace(
            go.Scatter(
                x=evaluated_df["iteration"],
                y=evaluated_df["validation_mae"],
                mode="lines+markers",
                name="MAE",
                line=dict(color="#00E5FF", width=2),
                marker=dict(size=6, color="#8F6BFF"),
                hovertemplate="Iter: %{x}<br>MAE: %{y:.6f}<extra></extra>",
            )
        )
        automl_fig = style_plot(automl_fig, height=320)
        automl_fig.update_layout(title=t("automl_chart_title"), xaxis_title=t("automl_iteration"), yaxis_title="MAE")
        st.plotly_chart(automl_fig, use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

    st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
    st.subheader(t("forecast_visualization"))
    forecast_df = data["actual_vs_forecast"]

    forecast_fig = go.Figure()
    forecast_fig.add_trace(
        go.Scatter(
            x=forecast_df["timestamp"],
            y=forecast_df["actual"],
            mode="lines",
            name="Actual",
            line=dict(color="#00E5FF", width=2),
        )
    )
    forecast_fig.add_trace(
        go.Scatter(
            x=forecast_df["timestamp"],
            y=forecast_df["forecast"],
            mode="lines",
            name="Forecast",
            line=dict(color="#8F6BFF", width=2),
        )
    )
    forecast_fig = style_plot(forecast_fig, height=390)
    forecast_fig.update_layout(title=t("forecast_visualization"), yaxis_title="Load (MW)")
    st.plotly_chart(forecast_fig, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

with right_col:
    st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
    st.subheader(t("peak_detection_panel"), help=t("tooltip_peak_load"))

    peak_chart = go.Figure()
    peak_chart.add_trace(
        go.Scatter(
            x=data["forecast_df"]["timestamp"],
            y=data["forecast_df"]["predicted_consumption"],
            mode="lines",
            name="Forecast",
            line=dict(color="#5A7DFF", width=2),
        )
    )
    peak_chart.add_trace(
        go.Scatter(
            x=data["forecast_df"]["timestamp"],
            y=[peak_results.threshold] * len(data["forecast_df"]),
            mode="lines",
            name="Peak threshold",
            line=dict(color="#FF9F43", width=1.7, dash="dash"),
        )
    )
    peak_chart.add_trace(
        go.Scatter(
            x=data["peaks_df"]["timestamp"],
            y=data["peaks_df"]["value"],
            mode="markers",
            name="Detected peaks",
            marker=dict(color="#FF4D4D", size=9, line=dict(width=1, color="#FFD1D1")),
        )
    )
    peak_chart = style_plot(peak_chart, height=360)
    peak_chart.update_layout(title=t("peak_detection_panel"), yaxis_title="Load (MW)")
    st.plotly_chart(peak_chart, use_container_width=True)

    peak_count = len(data["peaks_df"])
    st.caption(f"{t('peak_detection_panel')}: {peak_count}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

    st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
    st.subheader(t("optimization_effect"), help=t("tooltip_optimization_plan"))

    reduction_abs = max(0.0, data["original_peak"] - data["optimized_peak"])
    reduction_pct = (
        (reduction_abs / data["original_peak"]) * 100 if data["original_peak"] > 0 else 0.0
    )

    impact_fig = go.Figure(
        data=[
            go.Bar(
                x=[t("peak_before"), t("peak_after")],
                y=[data["original_peak"], data["optimized_peak"]],
                marker_color=["#FF7A7A", "#37E39A"],
                text=[f"{data['original_peak']:.1f}", f"{data['optimized_peak']:.1f}"],
                textposition="outside",
                showlegend=False,
            )
        ]
    )
    impact_fig = style_plot(impact_fig, height=360)
    impact_fig.update_layout(title=t("optimization_effect"), yaxis_title="Load (MW)")
    st.plotly_chart(impact_fig, use_container_width=True)
    st.caption(f"{t('improvement')}: {reduction_abs:.1f} MW ({reduction_pct:.2f}%)")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

aux_col1, aux_col2 = st.columns(2, gap="large")

with aux_col1:
    st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
    st.subheader(t("anomaly_detection"))
    anomaly_fig = go.Figure()
    anomaly_fig.add_trace(
        go.Scatter(
            x=data["historical_df"]["timestamp"],
            y=data["historical_df"]["consumption"],
            mode="lines",
            name="Load",
            line=dict(color="#6E8BFF", width=1.5),
        )
    )
    anomaly_fig.add_trace(
        go.Scatter(
            x=data["anomaly_df"]["timestamp"],
            y=data["anomaly_df"]["consumption"],
            mode="markers",
            name="Anomalies",
            marker=dict(color="#FF4D4D", size=8),
        )
    )
    anomaly_fig = style_plot(anomaly_fig, height=330)
    anomaly_fig.update_layout(title=t("anomaly_detection"), yaxis_title="Load (MW)")
    st.plotly_chart(anomaly_fig, use_container_width=True)
    st.caption(f"{t('anomaly_detection')}: {len(data['anomaly_df'])}")
    st.markdown("</div>", unsafe_allow_html=True)

with aux_col2:
    st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
    st.subheader(t("explainability"))
    shap_summary_path = OUTPUTS_DIR / "shap_summary.png"
    shap_importance_path = OUTPUTS_DIR / "shap_feature_importance.png"

    summary_mtime = shap_summary_path.stat().st_mtime if shap_summary_path.exists() else 0.0
    summary_bytes = load_image_bytes(str(shap_summary_path), summary_mtime)
    if summary_bytes is not None:
        st.image(summary_bytes, caption="SHAP Summary", use_container_width=True)
    else:
        st.info(t("shap_summary_unavailable"))

    importance_mtime = shap_importance_path.stat().st_mtime if shap_importance_path.exists() else 0.0
    importance_bytes = load_image_bytes(str(shap_importance_path), importance_mtime)
    if importance_bytes is not None:
        st.image(importance_bytes, caption="SHAP Feature Importance", use_container_width=True)
    else:
        st.info(t("shap_not_found"))
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Historical section
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("historical_consumption"))

historical_fig = go.Figure()
historical_fig.add_trace(
    go.Scatter(
        x=data["historical_df"]["timestamp"],
        y=data["historical_df"]["consumption"],
        mode="lines",
        name=t("historical_consumption"),
        line=dict(color="#7AA2FF", width=1.7),
    )
)
historical_fig = style_plot(historical_fig, height=420)
historical_fig.update_layout(title=t("historical_consumption"), yaxis_title="Load (MW)")
historical_fig.update_xaxes(
    rangeslider_visible=True,
    rangeselector=dict(
        buttons=list(
            [
                dict(count=7, label="7d", step="day", stepmode="backward"),
                dict(count=30, label="30d", step="day", stepmode="backward"),
                dict(count=6, label="6m", step="month", stepmode="backward"),
                dict(step="all", label="All"),
            ]
        )
    ),
)
st.plotly_chart(historical_fig, use_container_width=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Dataset Explorer
st.markdown("<div class='aerix-panel'>", unsafe_allow_html=True)
st.subheader(t("dataset_explorer"))
if dataset_explorer_df.empty:
    st.info(t("dataset_metadata_unavailable"))
else:
    st.dataframe(dataset_explorer_df, use_container_width=True, hide_index=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

# Architecture + artifacts
arch_col, img_col = st.columns([1, 1.55], gap="large")

with arch_col:
    st.subheader(t("system_architecture"))
    st.markdown(
        f"""
        <div class="aerix-architecture">
            {t("architecture_flow")}
        </div>
        """,
        unsafe_allow_html=True,
    )

with img_col:
    st.subheader(t("artifacts"))
    image_specs = [
        (OUTPUTS_DIR / "historical_consumption.png", t("historical_consumption")),
        (OUTPUTS_DIR / "forecast_vs_actual.png", t("forecast_visualization")),
        (OUTPUTS_DIR / "detected_peaks.png", t("peak_detection_panel")),
    ]

    tabs = st.tabs([t("artifact_history"), t("artifact_forecast"), t("artifact_peaks")])
    for tab, (path, caption) in zip(tabs, image_specs):
        with tab:
            mtime = path.stat().st_mtime if path.exists() else 0.0
            img_bytes = load_image_bytes(str(path), mtime)
            if img_bytes is not None:
                st.image(img_bytes, caption=caption, use_container_width=True)
            else:
                st.info(t("file_not_found", name=path.name))

st.markdown(
    f"""
    <div class="aerix-footer">
        {t("footer_text")}
    </div>
    """,
    unsafe_allow_html=True,
)
