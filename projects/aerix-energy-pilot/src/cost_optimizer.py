from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.precision import round_df, round_float


def load_energy_price(path: str | Path = "data/energy_price.csv") -> pd.DataFrame | None:
    price_path = Path(path)
    if not price_path.exists():
        return None

    try:
        df = pd.read_csv(price_path)
    except Exception:
        return None

    if not {"timestamp", "price_per_mwh"}.issubset(df.columns):
        return None

    df = df[["timestamp", "price_per_mwh"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["price_per_mwh"] = pd.to_numeric(df["price_per_mwh"], errors="coerce")
    df = df.dropna(subset=["timestamp", "price_per_mwh"])
    if df.empty:
        return None

    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
    return round_df(df, numeric_only=True)


def _get_price_at(timestamp: pd.Timestamp, price_df: pd.DataFrame | None, fallback_price: float = 0.0) -> float:
    if price_df is None or price_df.empty:
        return float(fallback_price)

    exact = price_df.loc[price_df["timestamp"] == timestamp, "price_per_mwh"]
    if not exact.empty:
        return float(exact.iloc[-1])

    previous = price_df.loc[price_df["timestamp"] <= timestamp, "price_per_mwh"]
    if not previous.empty:
        return float(previous.iloc[-1])

    return float(price_df["price_per_mwh"].iloc[0])


def optimize_for_cost(plan_df: pd.DataFrame, price_df: pd.DataFrame | None) -> pd.DataFrame:
    if plan_df is None or plan_df.empty:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "machine_id",
                "action",
                "target_timestamp",
                "reduction_pct",
                "power_impact_mw",
                "reason",
                "confidence",
                "energy_price",
                "cost_impact",
                "economic_reason",
            ]
        )

    enriched = plan_df.copy()
    enriched["timestamp"] = pd.to_datetime(enriched["timestamp"], errors="coerce")
    enriched["target_timestamp"] = pd.to_datetime(enriched.get("target_timestamp"), errors="coerce")
    enriched["power_impact_mw"] = pd.to_numeric(enriched["power_impact_mw"], errors="coerce").fillna(0.0)
    enriched["energy_price"] = enriched["timestamp"].map(lambda ts: _get_price_at(pd.Timestamp(ts), price_df))

    def _cost_impact(row: pd.Series) -> float:
        origin_price = float(row["energy_price"])
        impact = float(row["power_impact_mw"])
        action = str(row.get("action", ""))
        if action.startswith("shift"):
            target_ts = pd.Timestamp(row["target_timestamp"]) if pd.notna(row["target_timestamp"]) else pd.Timestamp(row["timestamp"])
            target_price = _get_price_at(target_ts, price_df, fallback_price=origin_price)
            return impact * max(0.0, origin_price - target_price)
        return impact * origin_price

    def _economic_reason(row: pd.Series) -> str:
        action = str(row.get("action", ""))
        if action.startswith("shift"):
            return "Shifted load from high-price interval."
        return "Reduced load during costly interval."

    enriched["cost_impact"] = enriched.apply(_cost_impact, axis=1)
    enriched["economic_reason"] = enriched.apply(_economic_reason, axis=1)
    enriched = round_df(enriched, numeric_only=True)
    return enriched


def summarize_costs(
    original_df: pd.DataFrame,
    optimized_df: pd.DataFrame,
    price_df: pd.DataFrame | None = None,
    default_price: float | None = None,
) -> dict[str, float]:
    if original_df is None or original_df.empty or optimized_df is None or optimized_df.empty:
        return {"cost_before": 0.0, "cost_after": 0.0, "estimated_cost_savings": 0.0}

    left = original_df.copy()
    right = optimized_df.copy()
    left["timestamp"] = pd.to_datetime(left["timestamp"], errors="coerce")
    right["timestamp"] = pd.to_datetime(right["timestamp"], errors="coerce")
    left["predicted_consumption"] = pd.to_numeric(left["predicted_consumption"], errors="coerce")
    right["predicted_consumption"] = pd.to_numeric(right["predicted_consumption"], errors="coerce")
    left = left.dropna(subset=["timestamp", "predicted_consumption"])
    right = right.dropna(subset=["timestamp", "predicted_consumption"])
    if left.empty or right.empty:
        return {"cost_before": 0.0, "cost_after": 0.0, "estimated_cost_savings": 0.0}

    merged = left.merge(
        right,
        on="timestamp",
        how="outer",
        suffixes=("_before", "_after"),
    ).sort_values("timestamp")
    merged["predicted_consumption_before"] = pd.to_numeric(
        merged["predicted_consumption_before"], errors="coerce"
    ).fillna(0.0)
    merged["predicted_consumption_after"] = pd.to_numeric(
        merged["predicted_consumption_after"], errors="coerce"
    ).fillna(0.0)

    fallback_price = float(default_price) if default_price is not None else 0.0
    merged["price_per_mwh"] = merged["timestamp"].map(
        lambda ts: _get_price_at(pd.Timestamp(ts), price_df, fallback_price=fallback_price)
    )

    cost_before = float((merged["predicted_consumption_before"] * merged["price_per_mwh"]).sum())
    cost_after = float((merged["predicted_consumption_after"] * merged["price_per_mwh"]).sum())
    savings = max(0.0, cost_before - cost_after)
    return {
        "cost_before": round_float(cost_before),
        "cost_after": round_float(cost_after),
        "estimated_cost_savings": round_float(savings),
    }
