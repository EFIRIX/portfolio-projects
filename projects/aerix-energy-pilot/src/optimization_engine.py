from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.plant_graph import build_plant_graph
from src.precision import round_df, round_float

try:
    import networkx as nx  # type: ignore[import]
except Exception:
    nx = None  # type: ignore[assignment]


PRIORITY_SCORE = {"high": 0, "medium": 1, "low": 2}
OUTPUT_COLUMNS = [
    "timestamp",
    "machine_id",
    "action",
    "target_timestamp",
    "reduction_pct",
    "power_impact_mw",
    "reason",
    "confidence",
]


@dataclass
class CandidateAction:
    timestamp: pd.Timestamp
    machine_id: str
    action: str
    target_timestamp: pd.Timestamp
    reduction_pct: float
    power_impact_mw: float
    reason: str
    confidence: float
    peak_impact: float
    price_impact: float
    flexibility_score: int
    priority_score: int


def _prepare_forecast(forecast_df: pd.DataFrame) -> pd.DataFrame:
    if forecast_df is None or forecast_df.empty:
        return pd.DataFrame(columns=["timestamp", "predicted_consumption"])

    if {"timestamp", "predicted_consumption"}.issubset(forecast_df.columns):
        prepared = forecast_df[["timestamp", "predicted_consumption"]].copy()
    elif {"timestamp", "consumption"}.issubset(forecast_df.columns):
        prepared = forecast_df[["timestamp", "consumption"]].rename(columns={"consumption": "predicted_consumption"})
    else:
        prepared = forecast_df.copy()
        if "timestamp" not in prepared.columns:
            index_name = prepared.index.name or "timestamp"
            prepared = prepared.reset_index().rename(columns={index_name: "timestamp"})
        value_cols = [col for col in prepared.columns if col != "timestamp"]
        if not value_cols:
            prepared["predicted_consumption"] = 0.0
        else:
            prepared = prepared[["timestamp", value_cols[0]]].rename(columns={value_cols[0]: "predicted_consumption"})

    prepared["timestamp"] = pd.to_datetime(prepared["timestamp"], errors="coerce")
    prepared["predicted_consumption"] = pd.to_numeric(prepared["predicted_consumption"], errors="coerce")
    prepared = prepared.dropna(subset=["timestamp", "predicted_consumption"])
    prepared = prepared.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
    return prepared


def _prepare_equipment(equipment_df: pd.DataFrame) -> pd.DataFrame:
    if equipment_df is None or equipment_df.empty:
        return pd.DataFrame(
            columns=[
                "machine_id",
                "power_mw",
                "flexibility",
                "priority",
                "shift_window_hours",
                "max_reduction",
                "min_runtime",
                "availability",
            ]
        )

    prepared = equipment_df.copy()
    prepared["machine_id"] = prepared["machine_id"].astype(str).str.strip()
    prepared = prepared[prepared["machine_id"] != ""]
    if "power_mw" not in prepared.columns:
        prepared["power_mw"] = 1.0
    prepared["power_mw"] = pd.to_numeric(prepared["power_mw"], errors="coerce").fillna(1.0).clip(lower=0.0)

    if "flexibility" not in prepared.columns:
        prepared["flexibility"] = False
    prepared["flexibility"] = prepared["flexibility"].astype(bool)

    if "priority" not in prepared.columns:
        prepared["priority"] = "medium"
    prepared["priority"] = prepared["priority"].fillna("medium").astype(str).str.lower()
    prepared["priority"] = prepared["priority"].map(lambda value: value if value in PRIORITY_SCORE else "medium")

    if "shift_window_hours" not in prepared.columns:
        prepared["shift_window_hours"] = 1
    prepared["shift_window_hours"] = (
        pd.to_numeric(prepared["shift_window_hours"], errors="coerce").fillna(1).astype(int).clip(lower=0)
    )

    if "max_reduction" not in prepared.columns:
        prepared["max_reduction"] = 0.20
    prepared["max_reduction"] = (
        pd.to_numeric(prepared["max_reduction"], errors="coerce").fillna(0.20).clip(lower=0.0, upper=1.0)
    )

    if "min_runtime" not in prepared.columns:
        prepared["min_runtime"] = 1
    prepared["min_runtime"] = (
        pd.to_numeric(prepared["min_runtime"], errors="coerce").fillna(1).astype(int).clip(lower=1)
    )

    if "availability" not in prepared.columns:
        prepared["availability"] = True
    prepared["availability"] = prepared["availability"].astype(bool)
    if "dependencies" not in prepared.columns:
        prepared["dependencies"] = [[] for _ in range(len(prepared))]
    prepared = prepared.sort_values("machine_id").drop_duplicates(subset=["machine_id"], keep="first").reset_index(drop=True)
    return prepared


def _prepare_price(price_df: pd.DataFrame | None) -> pd.DataFrame | None:
    if price_df is None or price_df.empty:
        return None

    if {"timestamp", "price_per_mwh"}.issubset(price_df.columns):
        prepared = price_df[["timestamp", "price_per_mwh"]].copy()
    else:
        return None

    prepared["timestamp"] = pd.to_datetime(prepared["timestamp"], errors="coerce")
    prepared["price_per_mwh"] = pd.to_numeric(prepared["price_per_mwh"], errors="coerce")
    prepared = prepared.dropna(subset=["timestamp", "price_per_mwh"])
    if prepared.empty:
        return None

    prepared = prepared.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    return prepared.reset_index(drop=True)


def _get_price_at(timestamp: pd.Timestamp, price_df: pd.DataFrame | None) -> float:
    if price_df is None or price_df.empty:
        return 0.0
    exact = price_df.loc[price_df["timestamp"] == timestamp, "price_per_mwh"]
    if not exact.empty:
        return float(exact.iloc[-1])
    previous = price_df.loc[price_df["timestamp"] <= timestamp, "price_per_mwh"]
    if not previous.empty:
        return float(previous.iloc[-1])
    return float(price_df["price_per_mwh"].iloc[0])


def _peak_threshold(forecast_df: pd.DataFrame, peak_threshold: float | None = None) -> float:
    if peak_threshold is not None:
        return float(peak_threshold)
    return float(forecast_df["predicted_consumption"].quantile(0.9))


def _calc_confidence(
    peak_severity: float,
    price_severity: float,
    flexibility: bool,
    priority: str,
    dependency_penalty: float = 0.0,
) -> float:
    priority_penalty = {"high": 0.15, "medium": 0.08, "low": 0.04}.get(priority, 0.08)
    confidence = 0.45 + (0.28 * peak_severity) + (0.12 * price_severity) + (0.1 if flexibility else 0.0)
    confidence = confidence - priority_penalty - dependency_penalty
    confidence = max(0.05, min(confidence, 0.99))
    return round_float(confidence)


def _select_shift_target(
    timestamp: pd.Timestamp,
    shift_window: int,
    load_series: pd.Series,
    threshold: float,
    price_df: pd.DataFrame | None,
) -> pd.Timestamp | None:
    candidates: list[tuple[pd.Timestamp, float, float]] = []
    for step in range(1, max(shift_window, 0) + 1):
        target_timestamp = timestamp + pd.Timedelta(hours=int(step))
        if target_timestamp not in load_series.index:
            continue
        target_load = float(load_series.loc[target_timestamp])
        target_price = _get_price_at(target_timestamp, price_df)
        candidates.append((target_timestamp, target_load, target_price))

    if not candidates:
        return None

    sorted_candidates = sorted(candidates, key=lambda item: (item[1] > threshold, item[1], item[2], item[0]))
    return sorted_candidates[0][0]


def generate_optimization_plan(
    forecast_df: pd.DataFrame,
    equipment_df: pd.DataFrame,
    peak_threshold: float | None = None,
    price_df: pd.DataFrame | None = None,
    graph: Any | None = None,
) -> pd.DataFrame:
    """Deterministic equipment-level optimization plan generation."""
    forecast = _prepare_forecast(forecast_df)
    equipment = _prepare_equipment(equipment_df)
    prices = _prepare_price(price_df)
    if forecast.empty or equipment.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    threshold = _peak_threshold(forecast, peak_threshold=peak_threshold)
    load_series = forecast.set_index("timestamp")["predicted_consumption"].astype(float).copy()
    graph = graph if graph is not None else build_plant_graph(equipment)

    max_price = float(prices["price_per_mwh"].max()) if prices is not None else 1.0
    if max_price <= 0:
        max_price = 1.0

    peak_timestamps = [ts for ts in load_series.index if float(load_series.loc[ts]) > threshold]
    peak_timestamps = sorted(pd.to_datetime(peak_timestamps))

    plan_rows: list[CandidateAction] = []
    selected_targets: dict[tuple[pd.Timestamp, str], pd.Timestamp] = {}

    for timestamp in peak_timestamps:
        current_load = float(load_series.loc[timestamp])
        if current_load <= threshold:
            continue

        candidate_rows: list[CandidateAction] = []
        for row in equipment.itertuples(index=False):
            machine_id = str(row.machine_id)
            if not bool(row.availability):
                continue

            power_mw = float(row.power_mw)
            if power_mw <= 0:
                continue

            flexibility = bool(row.flexibility)
            priority = str(row.priority)
            max_reduction = float(row.max_reduction)
            shift_window = int(row.shift_window_hours)
            origin_price = _get_price_at(timestamp, prices)

            action = "reduce"
            target_timestamp = timestamp
            reduction_pct = max_reduction
            power_impact = power_mw * max_reduction
            reason = "peak load mitigation"

            if flexibility and shift_window > 0:
                proposed_target = _select_shift_target(
                    timestamp=timestamp,
                    shift_window=shift_window,
                    load_series=load_series,
                    threshold=threshold,
                    price_df=prices,
                )
                if proposed_target is not None:
                    dependency_penalty = 0.0
                    if hasattr(graph, "nodes"):
                        if isinstance(getattr(graph, "nodes"), dict):
                            in_graph = machine_id in graph.nodes
                        else:
                            in_graph = machine_id in list(graph.nodes)
                    else:
                        in_graph = False

                    upstream_machines = (
                        sorted(str(node) for node in graph.predecessors(machine_id))
                        if in_graph and hasattr(graph, "predecessors")
                        else []
                    )
                    for upstream in upstream_machines:
                        upstream_target = selected_targets.get((timestamp, upstream), timestamp)
                        if proposed_target < upstream_target:
                            proposed_target = upstream_target
                            dependency_penalty = 0.08

                    latest_allowed = timestamp + pd.Timedelta(hours=shift_window)
                    if proposed_target <= latest_allowed:
                        action = f"shift +{int((proposed_target - timestamp).total_seconds() // 3600)} hour"
                        target_timestamp = proposed_target
                        reduction_pct = 1.0
                        power_impact = power_mw
                        reason = "peak load mitigation"
                        if prices is not None:
                            reason = "peak and cost optimization"
                    else:
                        dependency_penalty = 0.15
                else:
                    dependency_penalty = 0.1
            else:
                dependency_penalty = 0.0

            target_price = _get_price_at(target_timestamp, prices) if action.startswith("shift") else origin_price
            price_impact = max(0.0, origin_price - target_price) * power_impact
            peak_impact = power_impact
            peak_severity = max(0.0, (current_load - threshold) / max(threshold, 1.0))
            price_severity = max(0.0, origin_price / max_price)
            confidence = _calc_confidence(
                peak_severity=peak_severity,
                price_severity=price_severity,
                flexibility=flexibility,
                priority=priority,
                dependency_penalty=dependency_penalty,
            )

            candidate_rows.append(
                CandidateAction(
                    timestamp=timestamp,
                    machine_id=machine_id,
                    action=action,
                    target_timestamp=target_timestamp,
                    reduction_pct=reduction_pct,
                    power_impact_mw=power_impact,
                    reason=reason,
                    confidence=confidence,
                    peak_impact=peak_impact,
                    price_impact=price_impact,
                    flexibility_score=1 if flexibility else 0,
                    priority_score=PRIORITY_SCORE.get(priority, 1),
                )
            )

        candidate_rows = sorted(
            candidate_rows,
            key=lambda item: (
                -item.peak_impact,
                -item.price_impact,
                -item.flexibility_score,
                -item.priority_score,
                item.machine_id,
                item.timestamp,
            ),
        )

        for candidate in candidate_rows:
            current_load = float(load_series.loc[timestamp])
            if current_load <= threshold:
                break

            load_series.loc[timestamp] = max(0.0, current_load - candidate.power_impact_mw)
            if candidate.action.startswith("shift"):
                if candidate.target_timestamp not in load_series.index:
                    load_series.loc[candidate.target_timestamp] = 0.0
                load_series.loc[candidate.target_timestamp] = float(load_series.loc[candidate.target_timestamp]) + candidate.power_impact_mw
                selected_targets[(timestamp, candidate.machine_id)] = candidate.target_timestamp

            plan_rows.append(candidate)

    if not plan_rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    plan_df = pd.DataFrame(
        [
            {
                "timestamp": row.timestamp,
                "machine_id": row.machine_id,
                "action": row.action,
                "target_timestamp": row.target_timestamp,
                "reduction_pct": row.reduction_pct,
                "power_impact_mw": row.power_impact_mw,
                "reason": row.reason,
                "confidence": row.confidence,
                "_peak_impact": row.peak_impact,
                "_price_impact": row.price_impact,
                "_flexibility_score": row.flexibility_score,
                "_priority_score": row.priority_score,
            }
            for row in plan_rows
        ]
    )

    plan_df = plan_df.sort_values(
        by=["_peak_impact", "_price_impact", "_flexibility_score", "_priority_score", "machine_id", "timestamp"],
        ascending=[False, False, False, False, True, True],
    ).reset_index(drop=True)

    plan_df = round_df(plan_df, numeric_only=True)
    plan_df = plan_df[OUTPUT_COLUMNS]
    return plan_df


def apply_optimization_plan(forecast_df: pd.DataFrame, plan_df: pd.DataFrame) -> pd.DataFrame:
    forecast = _prepare_forecast(forecast_df)
    if forecast.empty or plan_df is None or plan_df.empty:
        return forecast

    load_series = forecast.set_index("timestamp")["predicted_consumption"].astype(float).copy()

    ordered_plan = plan_df.copy()
    ordered_plan["timestamp"] = pd.to_datetime(ordered_plan["timestamp"], errors="coerce")
    ordered_plan["target_timestamp"] = pd.to_datetime(ordered_plan["target_timestamp"], errors="coerce")
    ordered_plan["power_impact_mw"] = pd.to_numeric(ordered_plan["power_impact_mw"], errors="coerce").fillna(0.0)
    ordered_plan = ordered_plan.dropna(subset=["timestamp"]).sort_values(["timestamp", "machine_id", "action"])

    for row in ordered_plan.itertuples(index=False):
        timestamp = pd.Timestamp(row.timestamp)
        target_timestamp = pd.Timestamp(row.target_timestamp) if pd.notna(row.target_timestamp) else timestamp
        impact = float(row.power_impact_mw)
        action = str(row.action)

        if timestamp not in load_series.index:
            load_series.loc[timestamp] = 0.0
        load_series.loc[timestamp] = max(0.0, float(load_series.loc[timestamp]) - impact)

        if action.startswith("shift"):
            if target_timestamp not in load_series.index:
                load_series.loc[target_timestamp] = 0.0
            load_series.loc[target_timestamp] = float(load_series.loc[target_timestamp]) + impact

    optimized = (
        load_series.sort_index()
        .reset_index()
        .rename(columns={"index": "timestamp", "predicted_consumption": "predicted_consumption"})
    )
    optimized = round_df(optimized, numeric_only=True)
    return optimized


def summarize_optimization(
    original_df: pd.DataFrame,
    optimized_df: pd.DataFrame,
    co2_factor: float,
    price_df: pd.DataFrame | None = None,
    default_price: float | None = None,
) -> dict[str, float]:
    original = _prepare_forecast(original_df)
    optimized = _prepare_forecast(optimized_df)

    if original.empty or optimized.empty:
        return {
            "original_peak": 0.0,
            "optimized_peak": 0.0,
            "peak_reduction_mw": 0.0,
            "peak_reduction_percent": 0.0,
            "co2_reduction": 0.0,
            "cost_before": 0.0,
            "cost_after": 0.0,
            "estimated_cost_savings": 0.0,
        }

    merged = original.merge(
        optimized,
        on="timestamp",
        how="outer",
        suffixes=("_original", "_optimized"),
    ).sort_values("timestamp")
    merged["predicted_consumption_original"] = pd.to_numeric(
        merged["predicted_consumption_original"], errors="coerce"
    ).fillna(0.0)
    merged["predicted_consumption_optimized"] = pd.to_numeric(
        merged["predicted_consumption_optimized"], errors="coerce"
    ).fillna(0.0)

    original_peak = float(merged["predicted_consumption_original"].max())
    optimized_peak = float(merged["predicted_consumption_optimized"].max())
    peak_reduction = max(0.0, original_peak - optimized_peak)
    peak_reduction_percent = (peak_reduction / original_peak * 100.0) if original_peak > 0 else 0.0
    co2_reduction = peak_reduction * float(co2_factor)

    prices = _prepare_price(price_df)
    if prices is not None:
        merged["price_per_mwh"] = merged["timestamp"].map(lambda ts: _get_price_at(pd.Timestamp(ts), prices))
    else:
        merged["price_per_mwh"] = float(default_price) if default_price is not None else 0.0

    cost_before = float((merged["predicted_consumption_original"] * merged["price_per_mwh"]).sum())
    cost_after = float((merged["predicted_consumption_optimized"] * merged["price_per_mwh"]).sum())
    estimated_savings = max(0.0, cost_before - cost_after)

    return {
        "original_peak": round_float(original_peak),
        "optimized_peak": round_float(optimized_peak),
        "peak_reduction_mw": round_float(peak_reduction),
        "peak_reduction_percent": round_float(peak_reduction_percent),
        "co2_reduction": round_float(co2_reduction),
        "cost_before": round_float(cost_before),
        "cost_after": round_float(cost_after),
        "estimated_cost_savings": round_float(estimated_savings),
    }
