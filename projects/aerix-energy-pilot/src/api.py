from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import main as core_main
from src.anomaly_detection import run_anomaly_detection
from src.model import recursive_forecast


BASE_DIR = Path(__file__).resolve().parents[1]
BEST_MODEL_PATH = BASE_DIR / "models" / "best_model.pkl"

app = FastAPI(title="AERIX Energy Pilot API", version="1.0.0")


class PredictRequest(BaseModel):
    horizon: int = 24
    dataset: str = "grid"


def _load_best_model_payload() -> dict[str, Any]:
    if not BEST_MODEL_PATH.exists():
        raise HTTPException(status_code=404, detail="best_model.pkl not found")

    try:
        payload = joblib.load(BEST_MODEL_PATH)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to load best model: {exc}") from exc

    if not isinstance(payload, dict) or "model" not in payload:
        raise HTTPException(status_code=500, detail="invalid best model payload format")
    return payload


@app.get("/metrics")
def get_metrics() -> dict[str, Any]:
    payload = _load_best_model_payload()
    return {
        "model_name": payload.get("model_name"),
        "mae": payload.get("mae"),
        "rmse": payload.get("rmse"),
        "dataset_mode": payload.get("dataset_mode"),
        "saved_at": payload.get("saved_at"),
    }


@app.post("/predict")
def predict(request: PredictRequest) -> dict[str, Any]:
    payload = _load_best_model_payload()
    model = payload["model"]
    feature_columns = payload.get("feature_columns")

    if not isinstance(feature_columns, list) or not feature_columns:
        raise HTTPException(status_code=500, detail="feature_columns are missing in best model payload")

    base_cfg = core_main.load_config(BASE_DIR, dataset_override=("building" if request.dataset == "factory" else request.dataset))
    clean_df = core_main.load_and_preprocess(base_cfg)
    featured_df = core_main.create_time_features(clean_df)

    horizon = max(1, int(request.horizon))

    region_peak_last = float(pd.to_numeric(featured_df.get("region_peak", 1.0), errors="coerce").dropna().iloc[-1])
    if region_peak_last <= 0:
        region_peak_last = 1.0

    target_column = "normalized_consumption" if "normalized_consumption" in featured_df.columns else "consumption"

    pred_norm = recursive_forecast(
        model=model,
        history_df=featured_df,
        horizon=horizon,
        feature_columns=feature_columns,
        target_column=target_column,
    ).reset_index(drop=True)

    pred_mw = pd.to_numeric(pred_norm, errors="coerce") * region_peak_last

    last_ts = pd.to_datetime(featured_df["timestamp"].iloc[-1])
    timestamps = [(last_ts + pd.Timedelta(hours=i + 1)).strftime("%Y-%m-%d %H:%M") for i in range(horizon)]

    return {
        "model_name": payload.get("model_name"),
        "horizon": horizon,
        "forecast": [float(v) for v in pred_mw.tolist()],
        "timestamps": timestamps,
    }


@app.get("/anomalies")
def get_anomalies(dataset: str = "grid") -> dict[str, Any]:
    base_cfg = core_main.load_config(BASE_DIR, dataset_override=("building" if dataset == "factory" else dataset))
    clean_df = core_main.load_and_preprocess(base_cfg)

    result = run_anomaly_detection(clean_df, output_path=BASE_DIR / "outputs" / "anomalies.png")
    return {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "timestamps": result.get("timestamps", []),
    }
