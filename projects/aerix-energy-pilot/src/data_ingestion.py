from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.activity_log import log_training_event
from src.data_utils import deduplicate_timeseries, normalize_timestamp, validate_numeric_columns
from src.data_discovery_engine import discover_energy_datasets
from src.dataset_evaluator import evaluate_dataset_for_training, should_accept_dataset


DEFAULT_SOURCES_DIR = Path("data_sources")
DEFAULT_SOURCES_CONFIG = DEFAULT_SOURCES_DIR / "sources.json"
DEFAULT_TRAINING_POOL_DIR = Path("data") / "training_pool"
DEFAULT_TRAINING_POOL_FILE = DEFAULT_TRAINING_POOL_DIR / "global_training_pool.csv"
DEFAULT_GRID_POOL_EXPORT = Path("data") / "grid_training_pool.csv"
DEFAULT_DATASET_REGISTRY = Path("data") / "dataset_registry.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    mapping = {str(col).strip().lower(): str(col) for col in df.columns}
    for candidate in candidates:
        hit = mapping.get(candidate.strip().lower())
        if hit:
            return hit
    return None


def _load_sources_config(path: str | Path = DEFAULT_SOURCES_CONFIG) -> dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        return {}
    try:
        payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _kaggle_credentials_available() -> bool:
    env_ok = bool(os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY"))
    file_ok = Path.home().joinpath(".kaggle", "kaggle.json").exists()
    return env_ok or file_ok


def _normalize_source_item(item: dict[str, Any], index: int) -> dict[str, Any]:
    source = dict(item)
    source.setdefault("name", f"source_{index}")
    source.setdefault("type", "http")
    source["name"] = str(source["name"]).strip() or f"source_{index}"
    source["type"] = str(source["type"]).strip().lower() or "http"
    return source


def _load_json_list(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [entry for entry in payload if isinstance(entry, dict)]


def _append_dataset_registry(
    record: dict[str, Any],
    registry_path: str | Path = DEFAULT_DATASET_REGISTRY,
) -> None:
    normalized_record = dict(record)
    schema_raw = normalized_record.get("schema", [])
    if isinstance(schema_raw, dict):
        schema_list = [str(value) for value in schema_raw.values() if value is not None]
        normalized_record.setdefault("schema_detail", schema_raw)
    elif isinstance(schema_raw, list):
        schema_list = [str(value) for value in schema_raw]
    else:
        schema_list = []

    try:
        quality_score = float(normalized_record.get("quality_score", normalized_record.get("score", 0.0)))
    except Exception:
        quality_score = 0.0

    timestamp_value = str(
        normalized_record.get("timestamp")
        or normalized_record.get("ingestion_timestamp")
        or _utc_now_iso()
    )

    normalized_record.update(
        {
            "dataset_name": str(normalized_record.get("dataset_name", "unknown_dataset")),
            "source": str(normalized_record.get("source", "unknown_source")),
            "schema": schema_list,
            "quality_score": quality_score,
            "accepted": bool(normalized_record.get("accepted", False)),
            "rejected_reason": str(normalized_record.get("rejected_reason", "")),
            "timestamp": timestamp_value,
            # Compatibility aliases used by existing GUI/consumers.
            "score": quality_score,
            "ingestion_timestamp": timestamp_value,
        }
    )

    path = Path(registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_json_list(path)
    existing.append(normalized_record)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def discover_datasets(sources_config: str | Path = DEFAULT_SOURCES_CONFIG) -> list[dict[str, Any]]:
    """
    Read configured dataset sources.

    Supports:
    - modern format: {"datasets": [{...}]}
    - backward format: {"grid_sources": [...], "building_sources": [...]}
    """
    ranked = discover_energy_datasets(sources_config=sources_config)
    actionable: list[dict[str, Any]] = []
    for idx, item in enumerate(ranked):
        raw = item.get("raw", {})
        if not isinstance(raw, dict):
            continue
        normalized = _normalize_source_item(raw, idx)
        normalized["rank_score"] = float(item.get("rank_score", 0.0))
        normalized["download_url"] = str(item.get("download_url", ""))
        download_enabled = bool(raw.get("download_enabled", True))
        if not download_enabled:
            continue

        source_type = str(normalized.get("type", "")).lower()
        has_locator = bool(
            str(normalized.get("dataset", "")).strip()
            or str(normalized.get("url", "")).strip()
            or str(normalized.get("endpoint", "")).strip()
        )
        if source_type in {"kaggle", "http", "api"} and has_locator:
            actionable.append(normalized)

    # Backward-compatible fallback to explicit legacy config list.
    if actionable:
        return actionable

    payload = _load_sources_config(sources_config)
    discovered: list[dict[str, Any]] = []
    merged_ids: list[str] = []
    for key in ("grid_sources", "building_sources"):
        values = payload.get(key, [])
        if isinstance(values, list):
            merged_ids.extend([str(v).strip() for v in values if str(v).strip()])
    for idx, dataset_id in enumerate(merged_ids):
        discovered.append(
            _normalize_source_item(
                {"name": dataset_id.replace("/", "_"), "type": "kaggle", "dataset": dataset_id},
                idx,
            )
        )
    return discovered


def _download_kaggle_dataset(source: dict[str, Any], target_dir: Path) -> dict[str, Any]:
    dataset_id = str(source.get("dataset", "")).strip()
    if not dataset_id:
        return {"status": "skipped", "reason": "missing_kaggle_dataset_id", "files": []}

    if not _kaggle_credentials_available():
        return {"status": "skipped", "reason": "kaggle_credentials_missing", "files": []}

    destination = target_dir / source["name"]
    destination.mkdir(parents=True, exist_ok=True)

    cmd = [
        "kaggle",
        "datasets",
        "download",
        "-d",
        dataset_id,
        "-p",
        str(destination),
        "--unzip",
        "-q",
    ]

    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return {"status": "skipped", "reason": "kaggle_cli_not_installed", "files": []}
    except Exception as exc:
        return {"status": "failed", "reason": f"kaggle_exception:{exc}", "files": []}

    if completed.returncode != 0:
        reason = (completed.stderr or completed.stdout or "kaggle_download_failed").strip()[:600]
        return {"status": "failed", "reason": reason, "files": []}

    csv_files = sorted(destination.rglob("*.csv"))
    return {
        "status": "ok" if csv_files else "failed",
        "reason": "" if csv_files else "no_csv_files_downloaded",
        "files": [str(path) for path in csv_files],
    }


def _json_payload_to_dataframe(payload: Any) -> pd.DataFrame | None:
    if isinstance(payload, list):
        if payload and all(isinstance(item, dict) for item in payload):
            return pd.DataFrame(payload)
        return None
    if isinstance(payload, dict):
        for key in ("data", "results", "items", "hourly"):
            values = payload.get(key)
            if isinstance(values, list) and values and all(isinstance(item, dict) for item in values):
                return pd.DataFrame(values)
        return pd.DataFrame([payload])
    return None


def _download_http_or_api(source: dict[str, Any], target_dir: Path) -> dict[str, Any]:
    url = str(source.get("url") or source.get("endpoint") or "").strip()
    if not url:
        return {"status": "skipped", "reason": "missing_url_or_endpoint", "files": []}

    destination = target_dir / source["name"]
    destination.mkdir(parents=True, exist_ok=True)

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "AERIX/1.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            content = response.read()
            content_type = str(response.headers.get("Content-Type", "")).lower()
    except urllib.error.URLError as exc:
        return {"status": "failed", "reason": f"url_error:{exc}", "files": []}
    except Exception as exc:
        return {"status": "failed", "reason": f"download_error:{exc}", "files": []}

    csv_path = destination / f"{source['name']}.csv"
    text_payload = content.decode("utf-8", errors="ignore")

    if "json" in content_type or text_payload.strip().startswith(("{", "[")):
        try:
            parsed = json.loads(text_payload)
            frame = _json_payload_to_dataframe(parsed)
            if frame is None or frame.empty:
                return {"status": "failed", "reason": "json_payload_not_tabular", "files": []}
            frame.to_csv(csv_path, index=False)
            return {"status": "ok", "reason": "", "files": [str(csv_path)]}
        except Exception as exc:
            return {"status": "failed", "reason": f"json_parse_error:{exc}", "files": []}

    try:
        csv_path.write_bytes(content)
        return {"status": "ok", "reason": "", "files": [str(csv_path)]}
    except Exception as exc:
        return {"status": "failed", "reason": f"write_error:{exc}", "files": []}


def download_dataset(
    source: dict[str, Any],
    target_dir: str | Path = DEFAULT_SOURCES_DIR,
) -> dict[str, Any]:
    target_root = Path(target_dir)
    target_root.mkdir(parents=True, exist_ok=True)

    normalized_source = _normalize_source_item(source, 0)
    source_type = normalized_source.get("type", "http")
    if source_type == "kaggle":
        result = _download_kaggle_dataset(normalized_source, target_root)
    elif source_type in {"http", "api"}:
        result = _download_http_or_api(normalized_source, target_root)
    else:
        result = {"status": "skipped", "reason": f"unsupported_source_type:{source_type}", "files": []}

    result["source"] = normalized_source
    return result


def validate_dataset(df: pd.DataFrame) -> dict[str, Any]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return {"valid": False, "reason": "empty_dataframe"}

    timestamp_col = _find_column(df, ["timestamp", "datetime", "date_time", "date", "Datetime"])
    if timestamp_col is None:
        return {"valid": False, "reason": "missing_timestamp"}

    preferred = _find_column(df, ["consumption", "load", "energy", "aep_mw", "mw"])
    numeric_candidates = [
        col
        for col in df.columns
        if col != timestamp_col and pd.to_numeric(df[col], errors="coerce").notna().any()
    ]
    consumption_col = preferred if preferred is not None else (numeric_candidates[0] if numeric_candidates else None)
    if consumption_col is None:
        return {"valid": False, "reason": "missing_consumption_or_load"}

    normalized = pd.DataFrame(
        {
            "timestamp": df[timestamp_col],
            "consumption": df[consumption_col],
        }
    )
    normalized = normalize_timestamp(normalized, timestamp_column="timestamp")
    numeric_validation = validate_numeric_columns(
        normalized,
        numeric_columns=["consumption"],
        drop_invalid_rows=True,
    )
    normalized = numeric_validation.get("dataframe", pd.DataFrame(columns=["timestamp", "consumption"]))
    normalized = normalized.dropna(subset=["timestamp"])
    normalized = deduplicate_timeseries(normalized, timestamp_column="timestamp")

    if normalized.empty:
        return {"valid": False, "reason": "no_valid_rows_after_cleaning"}

    return {
        "valid": True,
        "reason": "ok",
        "timestamp_column": str(timestamp_col),
        "consumption_column": str(consumption_col),
        "rows": int(len(normalized)),
        "dataframe": normalized.reset_index(drop=True),
    }


def validate_dataset_structure(file_path: str | Path) -> dict[str, Any]:
    """
    Backward-compatible file validator used by existing pipeline wrappers.
    """
    path = Path(file_path)
    if not path.exists() or path.suffix.lower() != ".csv":
        return {"valid": False, "reason": "not_csv_or_missing", "path": str(path)}

    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        return {"valid": False, "reason": f"read_error:{exc}", "path": str(path)}

    validation = validate_dataset(frame)
    validation["path"] = str(path)
    return validation


def evaluate_dataset_before_append(
    dataset_path: str | Path,
    baseline_path: str | Path | None = None,
) -> dict[str, Any]:
    evaluation = evaluate_dataset_for_training(dataset_path=dataset_path, baseline_path=baseline_path)
    evaluation["accepted"] = should_accept_dataset(evaluation)
    return evaluation


def _canonicalize_training_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    canonical = df.copy()
    canonical = normalize_timestamp(canonical, timestamp_column="timestamp")
    numeric_validation = validate_numeric_columns(
        canonical,
        numeric_columns=["consumption"],
        drop_invalid_rows=True,
    )
    canonical = numeric_validation.get("dataframe", pd.DataFrame(columns=["timestamp", "consumption"]))
    if "source" not in canonical.columns:
        canonical["source"] = "unknown_source"
    canonical["source"] = canonical["source"].astype(str)

    canonical = canonical.dropna(subset=["timestamp", "consumption"]).copy()
    canonical = deduplicate_timeseries(
        canonical,
        timestamp_column="timestamp",
        sort_columns=["source"],
        keep="last",
    )
    canonical = canonical.sort_values(["timestamp", "source"], kind="mergesort")
    return canonical.reset_index(drop=True)


def append_to_training_pool(
    df: pd.DataFrame,
    source_name: str = "unknown_source",
    training_pool_file: str | Path = DEFAULT_TRAINING_POOL_FILE,
    grid_export_file: str | Path = DEFAULT_GRID_POOL_EXPORT,
) -> dict[str, Any]:
    validation = validate_dataset(df)
    if not validation.get("valid"):
        return {
            "status": "rejected",
            "reason": validation.get("reason", "invalid_dataset"),
            "appended_rows": 0,
            "total_rows": 0,
            "training_pool_file": str(training_pool_file),
        }

    normalized = validation["dataframe"].copy()
    normalized["source"] = str(source_name)

    pool_path = Path(training_pool_file)
    pool_path.parent.mkdir(parents=True, exist_ok=True)

    if pool_path.exists():
        try:
            existing = pd.read_csv(pool_path)
            existing = _canonicalize_training_frame(existing)
            if "source" not in existing.columns:
                existing["source"] = "existing"
        except Exception:
            existing = pd.DataFrame(columns=["timestamp", "consumption", "source"])
    else:
        existing = pd.DataFrame(columns=["timestamp", "consumption", "source"])

    previous_unique = (
        existing.drop_duplicates(subset=["timestamp"], keep="last")
        if not existing.empty
        else pd.DataFrame(columns=existing.columns)
    )
    previous_count = int(len(previous_unique))

    if existing.empty:
        combined = normalized.copy()
    else:
        combined = pd.concat([existing, normalized], ignore_index=True)
    combined = _canonicalize_training_frame(combined)
    combined.to_csv(pool_path, index=False)

    export_path = Path(grid_export_file)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    grid_export = combined.rename(columns={"timestamp": "Datetime", "consumption": "AERIX_MW"})[
        ["Datetime", "AERIX_MW"]
    ]
    grid_export.to_csv(export_path, index=False)

    total_count = int(len(combined))
    appended_rows = max(0, total_count - previous_count)

    return {
        "status": "ok",
        "reason": "merged",
        "appended_rows": int(appended_rows),
        "total_rows": total_count,
        "training_pool_file": str(pool_path),
        "grid_export_file": str(export_path),
    }


def scan_for_new_data(
    sources_config: str | Path = DEFAULT_SOURCES_CONFIG,
    target_dir: str | Path = DEFAULT_SOURCES_DIR,
    training_pool_file: str | Path = DEFAULT_TRAINING_POOL_FILE,
    grid_export_file: str | Path = DEFAULT_GRID_POOL_EXPORT,
    dataset_registry_path: str | Path = DEFAULT_DATASET_REGISTRY,
    log_path: str | Path = "logs/training_activity.log",
) -> dict[str, Any]:
    """
    Discover, download, validate and merge new datasets into training pool.
    """
    discovered_catalog = discover_energy_datasets(sources_config=sources_config)
    sources = discover_datasets(sources_config)

    summary: dict[str, Any] = {
        "timestamp": _utc_now_iso(),
        "sources_count": len(sources),
        "discovery_catalog_count": len(discovered_catalog),
        "datasets_discovered": 0,
        "datasets_downloaded": 0,
        "datasets_validated": 0,
        "datasets_accepted": 0,
        "datasets_rejected": 0,
        "appended_rows": 0,
        "new_data_found": False,
        "dataset_names": [],
        "dataset_quality_score": 0.0,
        "details": [],
    }
    accepted_scores: list[float] = []

    for source in sources:
        source_name = str(source.get("name", "unknown_source"))
        log_training_event("dataset discovered", details=source_name, log_path=log_path)
        summary["datasets_discovered"] += 1

        download_result = download_dataset(source, target_dir=target_dir)
        source_detail = {
            "source": source_name,
            "type": source.get("type"),
            "download_status": download_result.get("status"),
            "download_reason": download_result.get("reason", ""),
            "files": download_result.get("files", []),
            "validated": 0,
            "accepted": 0,
            "rejected": 0,
            "appended_rows": 0,
        }

        if download_result.get("status") != "ok":
            summary["details"].append(source_detail)
            continue

        files = [Path(path) for path in download_result.get("files", [])]
        summary["datasets_downloaded"] += len(files)

        for file_path in files:
            try:
                raw = pd.read_csv(file_path)
            except Exception as exc:
                source_detail["rejected"] += 1
                summary["datasets_rejected"] += 1
                _append_dataset_registry(
                    {
                        "dataset_name": file_path.name,
                        "source": source_name,
                        "download_url": source.get("download_url") or source.get("url") or source.get("endpoint"),
                        "schema": [],
                        "quality_score": 0.0,
                        "accepted": False,
                        "rejected_reason": f"read_error:{exc}",
                        "timestamp": _utc_now_iso(),
                    },
                    registry_path=dataset_registry_path,
                )
                log_training_event(
                    "dataset rejected",
                    details=f"{source_name}; reason=read_error:{exc}",
                    log_path=log_path,
                )
                continue

            validation = validate_dataset(raw)
            if not validation.get("valid"):
                source_detail["rejected"] += 1
                summary["datasets_rejected"] += 1
                _append_dataset_registry(
                    {
                        "dataset_name": file_path.name,
                        "source": source_name,
                        "download_url": source.get("download_url") or source.get("url") or source.get("endpoint"),
                        "schema": list(raw.columns),
                        "quality_score": 0.0,
                        "accepted": False,
                        "rejected_reason": str(validation.get("reason")),
                        "timestamp": _utc_now_iso(),
                    },
                    registry_path=dataset_registry_path,
                )
                log_training_event(
                    "dataset rejected",
                    details=f"{source_name}; reason={validation.get('reason')}",
                    log_path=log_path,
                )
                continue

            source_detail["validated"] += 1
            summary["datasets_validated"] += 1
            log_training_event("dataset validated", details=source_name, log_path=log_path)

            evaluation = evaluate_dataset_before_append(
                dataset_path=file_path,
                baseline_path=training_pool_file,
            )
            accepted = bool(evaluation.get("accepted"))
            if not accepted:
                source_detail["rejected"] += 1
                summary["datasets_rejected"] += 1
                reject_reason = str(evaluation.get("reason", "evaluation_rejected"))
                _append_dataset_registry(
                    {
                        "dataset_name": file_path.name,
                        "source": source_name,
                        "download_url": source.get("download_url") or source.get("url") or source.get("endpoint"),
                        "schema": [
                            str(validation.get("timestamp_column", "timestamp")),
                            str(validation.get("consumption_column", "consumption")),
                        ],
                        "quality_score": float(evaluation.get("final_score", 0.0)),
                        "accepted": False,
                        "rejected_reason": reject_reason,
                        "timestamp": _utc_now_iso(),
                    },
                    registry_path=dataset_registry_path,
                )
                log_training_event(
                    "dataset rejected",
                    details=f"{source_name}; reason={reject_reason}",
                    log_path=log_path,
                )
                continue

            source_detail["accepted"] += 1
            summary["datasets_accepted"] += 1
            accepted_scores.append(float(evaluation.get("final_score", 0.0)))

            append_result = append_to_training_pool(
                validation["dataframe"],
                source_name=source_name,
                training_pool_file=training_pool_file,
                grid_export_file=grid_export_file,
            )
            appended_rows = int(append_result.get("appended_rows", 0))
            source_detail["appended_rows"] += appended_rows
            summary["appended_rows"] += appended_rows
            if appended_rows > 0:
                summary["dataset_names"].append(source_name)
            _append_dataset_registry(
                {
                    "dataset_name": file_path.name,
                    "source": source_name,
                    "download_url": source.get("download_url") or source.get("url") or source.get("endpoint"),
                    "schema": [
                        str(validation.get("timestamp_column", "timestamp")),
                        str(validation.get("consumption_column", "consumption")),
                    ],
                    "quality_score": float(evaluation.get("final_score", 0.0)),
                    "accepted": True,
                    "rejected_reason": "",
                    "timestamp": _utc_now_iso(),
                },
                registry_path=dataset_registry_path,
            )

        summary["details"].append(source_detail)

    summary["dataset_count"] = len(set(summary["dataset_names"]))
    summary["new_data_found"] = bool(summary["appended_rows"] > 0)
    if accepted_scores:
        summary["dataset_quality_score"] = float(sum(accepted_scores) / len(accepted_scores))
    summary["training_pool_file"] = str(training_pool_file)
    summary["grid_export_file"] = str(grid_export_file)
    summary["dataset_registry_path"] = str(dataset_registry_path)

    pool_path = Path(training_pool_file)
    if pool_path.exists():
        try:
            pool_df = pd.read_csv(pool_path)
            summary["training_pool_size"] = int(len(pool_df))
        except Exception:
            summary["training_pool_size"] = 0
    else:
        summary["training_pool_size"] = 0

    return summary


def scan_data_sources(
    data_sources_dir: str | Path = DEFAULT_SOURCES_DIR,
    log_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """
    Backward-compatible scanner used by existing pipeline wrappers.
    """
    root = Path(data_sources_dir)
    if not root.exists():
        return []

    validations: list[dict[str, Any]] = []
    resolved_log_path = Path(log_path) if log_path is not None else Path("logs") / "training_activity.log"
    for csv_file in sorted(root.rglob("*.csv")):
        result = validate_dataset_structure(csv_file)
        validations.append(result)
        if result.get("valid"):
            log_training_event("dataset discovered", details=str(csv_file), log_path=resolved_log_path)

    return validations


def optional_kaggle_download(
    sources_config: str | Path = DEFAULT_SOURCES_CONFIG,
    target_dir: str | Path = DEFAULT_SOURCES_DIR,
) -> dict[str, Any]:
    """
    Optional Kaggle downloader.
    Disabled unless credentials and kaggle CLI are available.
    """
    if not _kaggle_credentials_available():
        return {"status": "skipped", "reason": "kaggle_credentials_missing", "downloads": []}

    datasets = discover_datasets(sources_config)
    kaggle_sources = [src for src in datasets if str(src.get("type", "")).lower() == "kaggle"]
    if not kaggle_sources:
        return {"status": "skipped", "reason": "no_kaggle_sources", "downloads": []}

    downloads: list[dict[str, Any]] = []
    for source in kaggle_sources:
        result = download_dataset(source, target_dir=target_dir)
        downloads.append(
            {
                "dataset": str(source.get("dataset") or source.get("name")),
                "status": result.get("status"),
                "reason": result.get("reason", ""),
                "files": result.get("files", []),
            }
        )

    return {"status": "ok", "reason": "", "downloads": downloads}
