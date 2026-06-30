from __future__ import annotations

from pathlib import Path
from typing import Any

import main as core_main
from src.data_ingestion import optional_kaggle_download, scan_data_sources


def run_pipeline(
    base_dir: str | Path | None = None,
    dataset_override: str | None = None,
    emit_report: bool = True,
    emit_plots: bool = True,
    run_data_ingestion: bool = True,
    run_kaggle_download: bool = False,
) -> dict[str, Any]:
    """
    Central orchestration wrapper.

    Keeps compatibility by reusing existing main.py functions.
    """
    resolved_base_dir = Path(base_dir) if base_dir is not None else Path(core_main.__file__).resolve().parent

    ingestion_summary: dict[str, Any] = {
        "scan": [],
        "kaggle": {"status": "skipped", "reason": "disabled"},
    }

    if run_data_ingestion:
        ingestion_summary["scan"] = scan_data_sources(
            resolved_base_dir / "data_sources",
            log_path=resolved_base_dir / "logs" / "training_activity.log",
        )

    if run_kaggle_download:
        ingestion_summary["kaggle"] = optional_kaggle_download(
            sources_config=resolved_base_dir / "data_sources" / "sources.json",
            target_dir=resolved_base_dir / "data_sources",
        )

    config = core_main.load_config(resolved_base_dir, dataset_override=dataset_override)
    row = core_main.run_single_pipeline(
        resolved_base_dir,
        config,
        emit_report=emit_report,
        emit_plots=emit_plots,
    )

    return {
        "status": "ok",
        "comparison_row": row,
        "config": config,
        "ingestion": ingestion_summary,
    }
