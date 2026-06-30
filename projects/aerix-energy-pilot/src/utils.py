from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib


def save_model(model: Any, path: str | Path) -> None:
    """Persist a model to disk using joblib."""
    model_path = Path(path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)


def load_model(path: str | Path) -> Any | None:
    """Load a model from disk, returning None if unavailable or unreadable."""
    model_path = Path(path)
    if not model_path.exists():
        return None

    try:
        return joblib.load(model_path)
    except Exception:
        return None


def calculate_cost_savings_rub(peak_reduction_mwh: float, price_per_mwh_rub: float) -> float:
    """Calculate savings in RUB using reduced energy in MWh."""
    return peak_reduction_mwh * price_per_mwh_rub


def calculate_co2_reduction(peak_reduction_mw: float, co2_factor: float) -> float:
    """Calculate CO2 reduction from reduced peak load."""
    return peak_reduction_mw * co2_factor


def format_rub(value: float) -> str:
    """Format a monetary value with thousands separator and RUB symbol."""
    return f"{value:,.2f}".replace(",", " ") + " ₽"
