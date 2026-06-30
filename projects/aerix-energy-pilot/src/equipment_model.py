from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.precision import round_df


MACHINES_PATH = Path("data/machines.json")
MACHINES_STATE_PATH = Path("data/machines_state.json")

SUPPORTED_COLUMNS = [
    "machine_id",
    "machine_type",
    "power_mw",
    "priority",
    "flexibility",
    "dependencies",
    "max_reduction",
    "min_runtime",
    "shift_window_hours",
    "availability",
]

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _parse_dependencies(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        if not stripped:
            return []
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                pass
        return [part.strip() for part in stripped.split(",") if part.strip()]
    return []


def get_demo_equipment() -> pd.DataFrame:
    demo_rows = [
        {
            "machine_id": "furnace_1",
            "machine_type": "furnace",
            "power_mw": 5.0,
            "priority": "medium",
            "flexibility": True,
            "dependencies": [],
            "max_reduction": 0.20,
            "min_runtime": 1,
            "shift_window_hours": 2,
            "availability": True,
        },
        {
            "machine_id": "conveyor_1",
            "machine_type": "conveyor",
            "power_mw": 1.8,
            "priority": "low",
            "flexibility": True,
            "dependencies": ["furnace_1"],
            "max_reduction": 0.25,
            "min_runtime": 1,
            "shift_window_hours": 1,
            "availability": True,
        },
        {
            "machine_id": "compressor_1",
            "machine_type": "compressor",
            "power_mw": 2.5,
            "priority": "high",
            "flexibility": False,
            "dependencies": ["conveyor_1"],
            "max_reduction": 0.10,
            "min_runtime": 2,
            "shift_window_hours": 0,
            "availability": True,
        },
        {
            "machine_id": "pump_1",
            "machine_type": "pump",
            "power_mw": 1.2,
            "priority": "medium",
            "flexibility": True,
            "dependencies": ["compressor_1"],
            "max_reduction": 0.18,
            "min_runtime": 1,
            "shift_window_hours": 1,
            "availability": True,
        },
    ]
    return pd.DataFrame(demo_rows)


def _load_machines_json(path: Path) -> pd.DataFrame:
    if not path.exists():
        return get_demo_equipment()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return get_demo_equipment()

    if isinstance(payload, dict):
        rows = payload.get("machines", [])
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []

    if not isinstance(rows, list) or not rows:
        return get_demo_equipment()

    df = pd.DataFrame(rows)
    return df if not df.empty else get_demo_equipment()


def _load_state(path: Path) -> dict[str, bool]:
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(payload, dict):
        return {}

    availability = payload.get("availability", payload)
    if not isinstance(availability, dict):
        return {}

    return {str(machine_id): bool(status) for machine_id, status in availability.items()}


def _apply_defaults(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()

    if "machine_id" not in normalized.columns:
        normalized["machine_id"] = [f"machine_{idx+1}" for idx in range(len(normalized))]
    normalized["machine_id"] = normalized["machine_id"].astype(str).str.strip()
    normalized = normalized[normalized["machine_id"] != ""]

    if "machine_type" not in normalized.columns:
        normalized["machine_type"] = "generic"
    normalized["machine_type"] = normalized["machine_type"].fillna("generic").astype(str).str.strip()
    normalized.loc[normalized["machine_type"] == "", "machine_type"] = "generic"

    if "power_mw" not in normalized.columns:
        normalized["power_mw"] = 1.0
    normalized["power_mw"] = pd.to_numeric(normalized["power_mw"], errors="coerce").fillna(1.0).clip(lower=0.0)

    if "priority" not in normalized.columns:
        normalized["priority"] = "medium"
    normalized["priority"] = normalized["priority"].fillna("medium").astype(str).str.lower().str.strip()
    normalized.loc[~normalized["priority"].isin(PRIORITY_ORDER.keys()), "priority"] = "medium"

    if "flexibility" not in normalized.columns:
        normalized["flexibility"] = False
    normalized["flexibility"] = normalized["flexibility"].astype(bool)

    if "dependencies" not in normalized.columns:
        normalized["dependencies"] = [[] for _ in range(len(normalized))]
    normalized["dependencies"] = normalized["dependencies"].apply(_parse_dependencies)

    if "max_reduction" not in normalized.columns:
        normalized["max_reduction"] = 0.20
    normalized["max_reduction"] = (
        pd.to_numeric(normalized["max_reduction"], errors="coerce").fillna(0.20).clip(lower=0.0, upper=1.0)
    )

    if "min_runtime" not in normalized.columns:
        normalized["min_runtime"] = 1
    normalized["min_runtime"] = (
        pd.to_numeric(normalized["min_runtime"], errors="coerce").fillna(1).astype(int).clip(lower=1)
    )

    if "shift_window_hours" not in normalized.columns:
        normalized["shift_window_hours"] = 1
    normalized["shift_window_hours"] = (
        pd.to_numeric(normalized["shift_window_hours"], errors="coerce").fillna(1).astype(int).clip(lower=0)
    )

    if "availability" not in normalized.columns:
        normalized["availability"] = True
    normalized["availability"] = normalized["availability"].astype(bool)

    normalized = normalized[SUPPORTED_COLUMNS].drop_duplicates(subset=["machine_id"], keep="first")
    normalized = normalized.sort_values("machine_id").reset_index(drop=True)
    normalized = round_df(normalized, numeric_only=True)
    return normalized


def load_equipment(
    machines_path: str | Path = MACHINES_PATH,
    state_path: str | Path = MACHINES_STATE_PATH,
) -> pd.DataFrame:
    machines_file = Path(machines_path)
    state_file = Path(state_path)

    equipment_df = _apply_defaults(_load_machines_json(machines_file))
    state_map = _load_state(state_file)

    if state_map:
        equipment_df["availability"] = equipment_df.apply(
            lambda row: bool(state_map.get(str(row["machine_id"]), bool(row["availability"]))),
            axis=1,
        )

    return equipment_df


def save_equipment_state(
    equipment_df: pd.DataFrame,
    state_path: str | Path = MACHINES_STATE_PATH,
) -> None:
    state_file = Path(state_path)
    state_file.parent.mkdir(parents=True, exist_ok=True)

    availability_map = {
        str(row.machine_id): bool(row.availability)
        for row in equipment_df[["machine_id", "availability"]].itertuples(index=False)
    }

    payload = {"availability": availability_map}
    state_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
