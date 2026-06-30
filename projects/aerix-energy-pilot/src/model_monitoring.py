from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_monitoring_metrics(
    mae: float,
    rmse: float,
    model_name: str,
    dataset_mode: str,
    output_path: str | Path = "models/monitoring_metrics.json",
) -> None:
    """Append model performance monitoring metrics without affecting predictions."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                payload = []
        except Exception:
            payload = []
    else:
        payload = []

    payload.append(
        {
            "timestamp": _utc_now_iso(),
            "model_name": model_name,
            "dataset_mode": dataset_mode,
            "MAE": float(mae),
            "RMSE": float(rmse),
        }
    )

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_monitoring_metrics(
    output_path: str | Path = "models/monitoring_metrics.json",
) -> list[dict]:
    path = Path(output_path)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload
        return []
    except Exception:
        return []
