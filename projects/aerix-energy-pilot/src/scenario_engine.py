from __future__ import annotations

from typing import Any

import pandas as pd

from src.cost_optimizer import optimize_for_cost, summarize_costs
from src.optimization_engine import apply_optimization_plan, generate_optimization_plan, summarize_optimization
from src.plant_graph import build_plant_graph
from src.precision import canonicalize_for_compare, round_df, round_float

try:
    import networkx as nx  # type: ignore[import]
except Exception:
    nx = None  # type: ignore[assignment]


def _prepare_forecast(baseline_forecast: pd.DataFrame | pd.Series) -> pd.DataFrame:
    if isinstance(baseline_forecast, pd.Series):
        if isinstance(baseline_forecast.index, pd.DatetimeIndex):
            df = pd.DataFrame({"timestamp": baseline_forecast.index, "predicted_consumption": baseline_forecast.values})
        else:
            df = pd.DataFrame({"predicted_consumption": baseline_forecast.values})
            df["timestamp"] = pd.date_range("2025-01-01", periods=len(df), freq="h")
    else:
        df = baseline_forecast.copy()

    if "timestamp" not in df.columns:
        index_name = df.index.name if df.index.name else "index"
        df = df.reset_index().rename(columns={index_name: "timestamp"})

    value_column = "predicted_consumption"
    if value_column not in df.columns:
        alternatives = [col for col in df.columns if col != "timestamp"]
        if alternatives:
            df = df.rename(columns={alternatives[0]: value_column})
        else:
            df[value_column] = 0.0

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df[value_column] = pd.to_numeric(df[value_column], errors="coerce")
    df = df.dropna(subset=["timestamp", value_column])
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
    return df[["timestamp", value_column]]


def _prepare_price(price_df: pd.DataFrame | None, multiplier: float) -> pd.DataFrame | None:
    if price_df is None or price_df.empty:
        return None
    if not {"timestamp", "price_per_mwh"}.issubset(price_df.columns):
        return None

    prepared = price_df[["timestamp", "price_per_mwh"]].copy()
    prepared["timestamp"] = pd.to_datetime(prepared["timestamp"], errors="coerce")
    prepared["price_per_mwh"] = pd.to_numeric(prepared["price_per_mwh"], errors="coerce")
    prepared = prepared.dropna(subset=["timestamp", "price_per_mwh"])
    if prepared.empty:
        return None

    prepared["price_per_mwh"] = prepared["price_per_mwh"] * float(multiplier)
    prepared = prepared.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
    return round_df(prepared, numeric_only=True)


def _apply_additional_load(forecast_df: pd.DataFrame, additional_load_mw: float) -> pd.DataFrame:
    adjusted = forecast_df.copy()
    adjusted["predicted_consumption"] = pd.to_numeric(adjusted["predicted_consumption"], errors="coerce").fillna(0.0)
    adjusted["predicted_consumption"] = adjusted["predicted_consumption"] + float(additional_load_mw)
    adjusted["predicted_consumption"] = adjusted["predicted_consumption"].clip(lower=0.0)
    return adjusted


def _apply_shift_overrides_on_plan(
    plan_df: pd.DataFrame,
    equipment_df: pd.DataFrame,
    machine_shift_overrides: dict[str, int],
    forecast_df: pd.DataFrame,
) -> pd.DataFrame:
    if plan_df is None:
        plan_df = pd.DataFrame()
    updated = plan_df.copy()
    if updated.empty:
        updated = pd.DataFrame(
            columns=[
                "timestamp",
                "machine_id",
                "action",
                "target_timestamp",
                "reduction_pct",
                "power_impact_mw",
                "reason",
                "confidence",
            ]
        )

    updated["timestamp"] = pd.to_datetime(updated.get("timestamp"), errors="coerce")
    updated["target_timestamp"] = pd.to_datetime(updated.get("target_timestamp"), errors="coerce")
    updated["reduction_pct"] = pd.to_numeric(updated.get("reduction_pct"), errors="coerce").fillna(0.0)
    updated["power_impact_mw"] = pd.to_numeric(updated.get("power_impact_mw"), errors="coerce").fillna(0.0)
    updated["confidence"] = pd.to_numeric(updated.get("confidence"), errors="coerce").fillna(0.5)

    peak_ts = forecast_df.loc[
        forecast_df["predicted_consumption"] > float(forecast_df["predicted_consumption"].quantile(0.9)),
        "timestamp",
    ]
    base_timestamp = pd.Timestamp(peak_ts.min()) if not peak_ts.empty else pd.Timestamp(forecast_df["timestamp"].iloc[0])

    for machine_id, shift_hours in sorted(machine_shift_overrides.items(), key=lambda item: str(item[0])):
        shift_hours = int(shift_hours)
        if shift_hours == 0:
            continue

        machine_rows = equipment_df[equipment_df["machine_id"].astype(str) == str(machine_id)]
        if machine_rows.empty:
            continue
        machine_power = float(machine_rows.iloc[0].get("power_mw", 0.0))
        if machine_power <= 0:
            continue

        mask = updated["machine_id"].astype(str) == str(machine_id)
        if mask.any():
            updated.loc[mask, "action"] = f"shift {shift_hours:+d} hour"
            updated.loc[mask, "target_timestamp"] = updated.loc[mask, "timestamp"] + pd.to_timedelta(shift_hours, unit="h")
            updated.loc[mask, "reduction_pct"] = 1.0
            updated.loc[mask, "reason"] = "scenario shift override"
            updated.loc[mask, "confidence"] = updated.loc[mask, "confidence"].apply(lambda value: max(0.05, min(float(value), 0.99)))
        else:
            updated = pd.concat(
                [
                    updated,
                    pd.DataFrame(
                        [
                            {
                                "timestamp": base_timestamp,
                                "machine_id": str(machine_id),
                                "action": f"shift {shift_hours:+d} hour",
                                "target_timestamp": base_timestamp + pd.to_timedelta(shift_hours, unit="h"),
                                "reduction_pct": 1.0,
                                "power_impact_mw": machine_power,
                                "reason": "scenario shift override",
                                "confidence": 0.72,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )

    updated = updated.dropna(subset=["timestamp"]).sort_values(["timestamp", "machine_id"]).reset_index(drop=True)
    return round_df(updated, numeric_only=True)


def _enforce_dependency_constraints(plan_df: pd.DataFrame, graph: nx.DiGraph | None) -> pd.DataFrame:
    if graph is None or plan_df is None or plan_df.empty:
        return plan_df

    adjusted = plan_df.copy()
    adjusted["timestamp"] = pd.to_datetime(adjusted["timestamp"], errors="coerce")
    adjusted["target_timestamp"] = pd.to_datetime(adjusted["target_timestamp"], errors="coerce")

    for idx, row in adjusted.sort_values(["timestamp", "machine_id"]).iterrows():
        machine_id = str(row["machine_id"])
        if machine_id not in graph.nodes:
            continue
        upstream = sorted(str(node) for node in graph.predecessors(machine_id))
        if not upstream:
            continue

        candidate_target = pd.Timestamp(row["target_timestamp"]) if pd.notna(row["target_timestamp"]) else pd.Timestamp(row["timestamp"])
        for upstream_machine in upstream:
            upstream_rows = adjusted[
                (adjusted["machine_id"].astype(str) == upstream_machine)
                & (adjusted["timestamp"] == row["timestamp"])
            ]
            if upstream_rows.empty:
                upstream_target = pd.Timestamp(row["timestamp"])
            else:
                upstream_target = pd.Timestamp(upstream_rows.iloc[0]["target_timestamp"])
            if candidate_target < upstream_target:
                candidate_target = upstream_target

        adjusted.at[idx, "target_timestamp"] = candidate_target

    return round_df(adjusted, numeric_only=True)


def run_scenario(
    baseline_forecast: pd.DataFrame | pd.Series,
    equipment_df: pd.DataFrame,
    energy_price_df: pd.DataFrame | None = None,
    params: dict[str, Any] | None = None,
    graph: Any | None = None,
    co2_factor: float = 0.45,
    default_price: float | None = None,
) -> dict[str, Any]:
    params = params or {}
    scenario_params = {
        "energy_price_multiplier": float(params.get("energy_price_multiplier", 1.0)),
        "machine_disable_list": list(params.get("machine_disable_list", [])),
        "machine_shift_overrides": dict(params.get("machine_shift_overrides", {})),
        "additional_load_mw": float(params.get("additional_load_mw", 0.0)),
    }

    baseline = _prepare_forecast(baseline_forecast)
    if baseline.empty:
        return {
            "scenario_forecast": pd.DataFrame(columns=["timestamp", "predicted_consumption"]),
            "scenario_peak": 0.0,
            "scenario_cost": 0.0,
            "scenario_co2": 0.0,
            "optimization_plan": pd.DataFrame(),
            "optimization_summary": {},
            "cost_summary": {},
            "params": canonicalize_for_compare(scenario_params),
        }

    equipment = equipment_df.copy()
    equipment["machine_id"] = equipment["machine_id"].astype(str)
    if "availability" not in equipment.columns:
        equipment["availability"] = True

    disabled_set = set(str(machine_id) for machine_id in scenario_params["machine_disable_list"])
    if disabled_set:
        equipment.loc[equipment["machine_id"].isin(disabled_set), "availability"] = False

    perturbed_forecast = _apply_additional_load(baseline, scenario_params["additional_load_mw"])
    graph = graph if graph is not None else build_plant_graph(equipment)
    price_df = _prepare_price(energy_price_df, scenario_params["energy_price_multiplier"])

    plan = generate_optimization_plan(
        forecast_df=perturbed_forecast,
        equipment_df=equipment,
        peak_threshold=None,
        price_df=price_df,
        graph=graph,
    )
    plan = _apply_shift_overrides_on_plan(
        plan_df=plan,
        equipment_df=equipment,
        machine_shift_overrides=scenario_params["machine_shift_overrides"],
        forecast_df=perturbed_forecast,
    )
    plan = _enforce_dependency_constraints(plan_df=plan, graph=graph)
    plan = optimize_for_cost(plan, price_df=price_df)

    optimized_forecast = apply_optimization_plan(perturbed_forecast, plan)
    optimization_summary = summarize_optimization(
        original_df=perturbed_forecast,
        optimized_df=optimized_forecast,
        co2_factor=co2_factor,
        price_df=price_df,
        default_price=default_price,
    )
    cost_summary = summarize_costs(
        original_df=perturbed_forecast,
        optimized_df=optimized_forecast,
        price_df=price_df,
        default_price=default_price,
    )

    scenario_peak = float(optimized_forecast["predicted_consumption"].max()) if not optimized_forecast.empty else 0.0
    scenario_cost = float(cost_summary.get("cost_after", 0.0))
    scenario_co2 = float(optimization_summary.get("co2_reduction", 0.0))

    return {
        "scenario_forecast": round_df(optimized_forecast, numeric_only=True),
        "scenario_peak": round_float(scenario_peak),
        "scenario_cost": round_float(scenario_cost),
        "scenario_co2": round_float(scenario_co2),
        "optimization_plan": round_df(plan, numeric_only=True),
        "optimization_summary": canonicalize_for_compare(optimization_summary),
        "cost_summary": canonicalize_for_compare(cost_summary),
        "params": canonicalize_for_compare(scenario_params),
    }


def compare_scenarios(base_result: dict[str, Any], scenario_result: dict[str, Any]) -> dict[str, float]:
    base_peak = float(base_result.get("scenario_peak", 0.0))
    base_cost = float(base_result.get("scenario_cost", 0.0))
    base_co2 = float(base_result.get("scenario_co2", 0.0))

    scenario_peak = float(scenario_result.get("scenario_peak", 0.0))
    scenario_cost = float(scenario_result.get("scenario_cost", 0.0))
    scenario_co2 = float(scenario_result.get("scenario_co2", 0.0))

    return {
        "peak_delta": round_float(base_peak - scenario_peak),
        "cost_delta": round_float(base_cost - scenario_cost),
        "co2_delta": round_float(base_co2 - scenario_co2),
    }
