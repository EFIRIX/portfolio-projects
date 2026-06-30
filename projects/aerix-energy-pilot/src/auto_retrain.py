from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.activity_log import log_training_event
from src.data_ingestion import DEFAULT_TRAINING_POOL_FILE, scan_for_new_data
from src.pipeline import run_pipeline


DEFAULT_AUTO_RETRAIN_STATE = Path("models") / "auto_retrain_state.json"
DEFAULT_AUTO_RETRAIN_STATUS = Path("models") / "auto_retrain_status.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _resolve_base_dir(base_dir: str | Path | None) -> Path:
    if base_dir is None:
        return Path(__file__).resolve().parents[1]
    return Path(base_dir)


def _registry_path(base_dir: Path, dataset_override: str) -> Path:
    if dataset_override == "building":
        return base_dir / "models" / "model_registry_building.json"
    return base_dir / "models" / "model_registry.json"


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _read_registry_entries(registry_path: Path) -> list[dict[str, Any]]:
    payload = _load_json(registry_path, default=[])
    return payload if isinstance(payload, list) else []


def _latest_registry_metrics(registry_entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not registry_entries:
        return {"model_name": None, "mae": None, "rmse": None, "timestamp": None}
    latest = registry_entries[-1]
    return {
        "model_name": latest.get("model_name"),
        "mae": _to_float(latest.get("MAE")),
        "rmse": _to_float(latest.get("RMSE")),
        "timestamp": latest.get("timestamp"),
    }


def _training_pool_info(training_pool_file: Path) -> dict[str, int]:
    if not training_pool_file.exists():
        return {"training_dataset_size": 0, "dataset_count": 0}
    try:
        pool_df = pd.read_csv(training_pool_file)
    except Exception:
        return {"training_dataset_size": 0, "dataset_count": 0}

    row_count = int(len(pool_df))
    if "source" in pool_df.columns:
        dataset_count = int(pool_df["source"].astype(str).nunique())
    else:
        dataset_count = 1 if row_count > 0 else 0
    return {"training_dataset_size": row_count, "dataset_count": dataset_count}


def _enrich_latest_registry_entry(
    registry_path: Path,
    training_dataset_size: int,
    dataset_count: int,
    dataset_quality_score: float | None = None,
) -> None:
    entries = _read_registry_entries(registry_path)
    if not entries:
        return

    latest = dict(entries[-1])
    latest["training_dataset_size"] = int(training_dataset_size)
    latest["dataset_count"] = int(dataset_count)
    latest["training_dataset_count"] = int(dataset_count)
    if dataset_quality_score is not None:
        latest["dataset_quality_score"] = float(dataset_quality_score)
    latest["training_timestamp"] = _utc_now_iso()
    entries[-1] = latest
    _save_json(registry_path, entries)


def _status_payload_path(base_dir: Path) -> Path:
    return base_dir / DEFAULT_AUTO_RETRAIN_STATUS


def _state_payload_path(base_dir: Path) -> Path:
    return base_dir / DEFAULT_AUTO_RETRAIN_STATE


def _write_status(base_dir: Path, payload: dict[str, Any]) -> None:
    status_path = _status_payload_path(base_dir)
    _save_json(status_path, payload)


def load_auto_retrain_status(base_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_base = _resolve_base_dir(base_dir)
    payload = _load_json(_status_payload_path(resolved_base), default={})
    return payload if isinstance(payload, dict) else {}


def check_for_new_data(
    base_dir: str | Path | None = None,
    dataset_override: str = "grid",
) -> dict[str, Any]:
    resolved_base = _resolve_base_dir(base_dir)
    sources_config = resolved_base / "data_sources" / "sources.json"
    target_dir = resolved_base / "data_sources"
    training_pool_file = resolved_base / DEFAULT_TRAINING_POOL_FILE
    grid_export_file = resolved_base / "data" / "grid_training_pool.csv"
    log_path = resolved_base / "logs" / "training_activity.log"

    summary = scan_for_new_data(
        sources_config=sources_config,
        target_dir=target_dir,
        training_pool_file=training_pool_file,
        grid_export_file=grid_export_file,
        dataset_registry_path=resolved_base / "data" / "dataset_registry.json",
        log_path=log_path,
    )
    summary["dataset_override"] = dataset_override
    summary["checked_at"] = _utc_now_iso()

    _write_status(
        resolved_base,
        {
            "last_scan": summary,
            "last_update": _utc_now_iso(),
        },
    )
    return summary


def compare_models(previous_metrics: dict[str, Any], new_metrics: dict[str, Any]) -> dict[str, Any]:
    prev_mae = _to_float(previous_metrics.get("mae"))
    new_mae = _to_float(new_metrics.get("mae"))
    prev_rmse = _to_float(previous_metrics.get("rmse"))
    new_rmse = _to_float(new_metrics.get("rmse"))

    improved = bool(
        prev_mae is not None
        and new_mae is not None
        and new_mae < prev_mae
    )

    mae_delta = (new_mae - prev_mae) if (prev_mae is not None and new_mae is not None) else None
    rmse_delta = (new_rmse - prev_rmse) if (prev_rmse is not None and new_rmse is not None) else None

    return {
        "improved": improved,
        "previous_mae": prev_mae,
        "new_mae": new_mae,
        "previous_rmse": prev_rmse,
        "new_rmse": new_rmse,
        "mae_delta": mae_delta,
        "rmse_delta": rmse_delta,
        "previous_model": previous_metrics.get("model_name"),
        "new_model": new_metrics.get("model_name"),
    }


def deployment_logic(comparison_result: dict[str, Any]) -> dict[str, Any]:
    if comparison_result.get("improved"):
        return {
            "deployed": True,
            "action": "replace_best_model",
            "reason": "new_model_mae_better",
        }
    return {
        "deployed": False,
        "action": "keep_current_model",
        "reason": "no_mae_improvement",
    }


def trigger_retraining(
    base_dir: str | Path | None = None,
    dataset_override: str = "grid",
    emit_plots: bool = True,
    ingestion_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_base = _resolve_base_dir(base_dir)
    registry_path = _registry_path(resolved_base, dataset_override)
    log_path = resolved_base / "logs" / "training_activity.log"

    before_entries = _read_registry_entries(registry_path)
    previous_metrics = _latest_registry_metrics(before_entries)

    log_training_event("training started", details=f"dataset={dataset_override}", log_path=log_path)
    started_at = _utc_now()
    run_pipeline(
        base_dir=resolved_base,
        dataset_override=dataset_override,
        emit_report=False,
        emit_plots=emit_plots,
        run_data_ingestion=False,
        run_kaggle_download=False,
    )
    duration_sec = (_utc_now() - started_at).total_seconds()

    after_entries = _read_registry_entries(registry_path)
    if len(after_entries) == len(before_entries):
        fallback_model_name = (
            previous_metrics.get("model_name")
            or "UnknownModel"
        )
        fallback_mae = _to_float(previous_metrics.get("mae"))
        fallback_rmse = _to_float(previous_metrics.get("rmse"))
        after_entries.append(
            {
                "model_name": fallback_model_name,
                "MAE": float(fallback_mae) if fallback_mae is not None else None,
                "RMSE": float(fallback_rmse) if fallback_rmse is not None else None,
                "timestamp": _utc_now_iso(),
                "dataset_mode": "factory" if dataset_override == "building" else "grid",
            }
        )
        _save_json(registry_path, after_entries)

    new_metrics = _latest_registry_metrics(after_entries)
    comparison = compare_models(previous_metrics, new_metrics)
    deployment = deployment_logic(comparison)

    training_pool_info = _training_pool_info(resolved_base / DEFAULT_TRAINING_POOL_FILE)
    quality_score = None
    if isinstance(ingestion_summary, dict):
        quality_score = _to_float(ingestion_summary.get("dataset_quality_score"))

    _enrich_latest_registry_entry(
        registry_path=registry_path,
        training_dataset_size=training_pool_info["training_dataset_size"],
        dataset_count=training_pool_info["dataset_count"],
        dataset_quality_score=quality_score,
    )

    if comparison.get("improved"):
        log_training_event(
            "model improved",
            details=f"prev_mae={comparison.get('previous_mae')}; new_mae={comparison.get('new_mae')}",
            log_path=log_path,
        )
        log_training_event(
            "model deployed",
            details=f"model={new_metrics.get('model_name')}; mae={comparison.get('new_mae')}",
            log_path=log_path,
        )
    else:
        log_training_event(
            "model rejected",
            details=f"prev_mae={comparison.get('previous_mae')}; new_mae={comparison.get('new_mae')}",
            log_path=log_path,
        )

    return {
        "started_at": started_at.isoformat(),
        "duration_sec": duration_sec,
        "previous_metrics": previous_metrics,
        "new_metrics": new_metrics,
        "comparison": comparison,
        "deployment": deployment,
        "training_pool_info": training_pool_info,
    }


def run_auto_retrain_cycle(
    base_dir: str | Path | None = None,
    dataset_override: str = "grid",
    interval_hours: int = 24,
    force: bool = False,
) -> dict[str, Any]:
    resolved_base = _resolve_base_dir(base_dir)
    state_path = _state_payload_path(resolved_base)
    state_payload = _load_json(state_path, default={})
    if not isinstance(state_payload, dict):
        state_payload = {}

    now = _utc_now()
    last_run_raw = state_payload.get("last_cycle_at")
    last_run_at: datetime | None = None
    if isinstance(last_run_raw, str):
        try:
            last_run_at = datetime.fromisoformat(last_run_raw)
        except Exception:
            last_run_at = None

    if not force and last_run_at is not None:
        due_at = last_run_at + timedelta(hours=max(1, int(interval_hours)))
        if now < due_at:
            payload = {
                "status": "skipped",
                "reason": "interval_not_elapsed",
                "last_cycle_at": last_run_at.isoformat(),
                "next_cycle_at": due_at.isoformat(),
            }
            _write_status(resolved_base, {"last_cycle": payload, "last_update": _utc_now_iso()})
            return payload

    ingestion = check_for_new_data(base_dir=resolved_base, dataset_override=dataset_override)
    if not ingestion.get("new_data_found"):
        state_payload["last_cycle_at"] = now.isoformat()
        state_payload["last_new_data"] = False
        _save_json(state_path, state_payload)
        payload = {
            "status": "ok",
            "reason": "no_new_data",
            "ingestion": ingestion,
            "retraining": None,
            "last_cycle_at": now.isoformat(),
        }
        _write_status(resolved_base, {"last_cycle": payload, "last_update": _utc_now_iso()})
        return payload

    if int(ingestion.get("datasets_accepted", 0)) <= 0:
        state_payload["last_cycle_at"] = now.isoformat()
        state_payload["last_new_data"] = False
        _save_json(state_path, state_payload)
        payload = {
            "status": "ok",
            "reason": "no_accepted_data",
            "ingestion": ingestion,
            "retraining": None,
            "last_cycle_at": now.isoformat(),
        }
        _write_status(resolved_base, {"last_cycle": payload, "last_update": _utc_now_iso()})
        return payload

    retraining = trigger_retraining(
        base_dir=resolved_base,
        dataset_override=dataset_override,
        emit_plots=True,
        ingestion_summary=ingestion,
    )

    state_payload["last_cycle_at"] = now.isoformat()
    state_payload["last_new_data"] = True
    state_payload["last_deployed"] = bool(retraining.get("deployment", {}).get("deployed"))
    _save_json(state_path, state_payload)

    payload = {
        "status": "ok",
        "reason": "retrained",
        "ingestion": ingestion,
        "retraining": retraining,
        "last_cycle_at": now.isoformat(),
    }
    _write_status(resolved_base, {"last_cycle": payload, "last_update": _utc_now_iso()})
    return payload


def auto_retrain_loop(
    base_dir: str | Path | None = None,
    dataset_override: str = "grid",
    interval_hours: int = 24,
    max_cycles: int | None = None,
) -> None:
    """
    Background loop for periodic auto retraining.
    """
    cycles = 0
    while True:
        run_auto_retrain_cycle(
            base_dir=base_dir,
            dataset_override=dataset_override,
            interval_hours=interval_hours,
            force=True,
        )
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            break
        time.sleep(max(1, int(interval_hours * 3600)))
