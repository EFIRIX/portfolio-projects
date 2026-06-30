from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from src.model import evaluate, train_lightgbm, train_linear_model, train_random_forest


MODEL_MAP = {
    "LinearRegression": train_linear_model,
    "RandomForest": train_random_forest,
    "LightGBM": train_lightgbm,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_time_series_cv(
    df: pd.DataFrame,
    model_name: str,
    feature_columns: list[str],
    target_column: str,
    n_splits: int = 5,
    output_path: str | Path = "models/cv_results.json",
) -> dict[str, Any]:
    """Temporal CV for robustness tracking. Runs during training only."""
    trainer = MODEL_MAP.get(model_name)
    if trainer is None:
        return {"status": "skipped", "reason": f"unsupported_model:{model_name}"}

    if df is None or len(df) < max(20, n_splits + 2):
        return {"status": "skipped", "reason": "insufficient_rows"}

    work_df = df.copy().reset_index(drop=True)
    if target_column not in work_df.columns:
        return {"status": "skipped", "reason": f"missing_target:{target_column}"}

    X = work_df[feature_columns].copy()
    y = pd.to_numeric(work_df[target_column], errors="coerce")

    valid_mask = y.notna()
    X = X[valid_mask].reset_index(drop=True)
    y = y[valid_mask].reset_index(drop=True)

    if len(X) < max(20, n_splits + 2):
        return {"status": "skipped", "reason": "insufficient_valid_rows"}

    splitter = TimeSeriesSplit(n_splits=min(n_splits, max(2, len(X) // 20)))
    mae_scores: list[float] = []
    rmse_scores: list[float] = []

    for train_idx, test_idx in splitter.split(X):
        X_train, X_val = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[test_idx]

        model = trainer(X_train, y_train)
        y_pred = model.predict(X_val)
        metrics = evaluate(y_val, y_pred)
        mae_scores.append(float(metrics["mae"]))
        rmse_scores.append(float(metrics["rmse"]))

    result = {
        "model_name": model_name,
        "MAE_mean": float(np.mean(mae_scores)) if mae_scores else None,
        "RMSE_mean": float(np.mean(rmse_scores)) if rmse_scores else None,
        "folds": int(len(mae_scores)),
        "timestamp": _utc_now_iso(),
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    result["status"] = "ok"
    return result
