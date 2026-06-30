from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import plotly.graph_objects as go


@dataclass
class RegionPoint:
    region: str
    lat: float
    lon: float
    peak_mw: float
    current_load_mw: float
    peak_risk: str
    color: str


RISK_COLORS = {
    "normal": "#37E39A",
    "elevated": "#FFD166",
    "peak risk": "#FF5F77",
}


def _demo_coords(index: int) -> tuple[float, float]:
    # Deterministic demo coordinates around Eurasia to keep map usable without geo data.
    base_coords = [
        (55.7558, 37.6173),   # Moscow
        (59.9343, 30.3351),   # Saint Petersburg
        (56.8389, 60.6057),   # Ekaterinburg
        (55.0084, 82.9357),   # Novosibirsk
        (43.1155, 131.8855),  # Vladivostok
        (48.7194, 44.5018),   # Volgograd
        (55.0302, 82.9204),   # Novosibirsk area
        (53.1959, 50.1008),   # Samara
    ]
    return base_coords[index % len(base_coords)]


def _risk_label(load: float, peak: float) -> str:
    if peak <= 0:
        return "normal"
    ratio = load / peak
    if ratio >= 0.9:
        return "peak risk"
    if ratio >= 0.7:
        return "elevated"
    return "normal"


def _extract_regions(clean_df: pd.DataFrame) -> tuple[list[str], dict[str, float]]:
    region_peaks = clean_df.attrs.get("region_peaks", {}) if isinstance(clean_df, pd.DataFrame) else {}
    if isinstance(region_peaks, dict) and region_peaks:
        regions = [str(name) for name in region_peaks.keys()]
        peaks = {str(k): float(v) for k, v in region_peaks.items()}
        return regions, peaks

    if "region_name" in clean_df.columns:
        regions = [str(v) for v in clean_df["region_name"].dropna().unique().tolist() if str(v).strip()]
        if regions:
            fallback_peak = float(pd.to_numeric(clean_df["consumption"], errors="coerce").max())
            if not pd.notna(fallback_peak) or fallback_peak <= 0:
                fallback_peak = 1.0
            peaks = {name: fallback_peak for name in regions}
            return regions, peaks

    fallback_peak = float(pd.to_numeric(clean_df.get("consumption", pd.Series([1.0])), errors="coerce").max())
    if not pd.notna(fallback_peak) or fallback_peak <= 0:
        fallback_peak = 1.0
    return ["System-1"], {"System-1": fallback_peak}


def build_energy_map_dataframe(
    clean_df: pd.DataFrame,
    forecast_df: pd.DataFrame | None = None,
    peak_threshold: float | None = None,
) -> pd.DataFrame:
    regions, region_peaks = _extract_regions(clean_df)
    if not regions:
        return pd.DataFrame(columns=["region", "lat", "lon", "peak_mw", "current_load_mw", "peak_risk", "color"])

    total_peak = sum(max(float(region_peaks.get(r, 1.0)), 1.0) for r in regions)
    if total_peak <= 0:
        total_peak = float(len(regions))

    current_total_load = None
    if isinstance(forecast_df, pd.DataFrame) and not forecast_df.empty and "predicted_consumption" in forecast_df.columns:
        value = pd.to_numeric(forecast_df["predicted_consumption"], errors="coerce").dropna()
        if not value.empty:
            current_total_load = float(value.iloc[-1])

    points: list[RegionPoint] = []
    for idx, region in enumerate(regions):
        peak = max(float(region_peaks.get(region, 1.0)), 1.0)
        share = peak / total_peak if total_peak > 0 else 1.0 / max(1, len(regions))
        current_load = peak * 0.65 if current_total_load is None else current_total_load * share
        risk = _risk_label(current_load, peak if peak_threshold is None else max(peak, peak_threshold))
        lat, lon = _demo_coords(idx)
        points.append(
            RegionPoint(
                region=region,
                lat=lat,
                lon=lon,
                peak_mw=peak,
                current_load_mw=current_load,
                peak_risk=risk,
                color=RISK_COLORS.get(risk, "#37E39A"),
            )
        )

    return pd.DataFrame([p.__dict__ for p in points])


def build_energy_map_figure(map_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if map_df is None or map_df.empty:
        fig.update_layout(
            title="Energy Grid Map",
            template="plotly_dark",
            annotations=[
                {
                    "text": "No region data available",
                    "x": 0.5,
                    "y": 0.5,
                    "xref": "paper",
                    "yref": "paper",
                    "showarrow": False,
                }
            ],
        )
        return fig

    fig.add_trace(
        go.Scattermapbox(
            lat=map_df["lat"],
            lon=map_df["lon"],
            mode="markers",
            marker={
                "size": 14,
                "color": map_df["color"],
            },
            text=[
                (
                    f"Region: {row.region}<br>"
                    f"Current load: {row.current_load_mw:.1f} MW<br>"
                    f"Peak level: {row.peak_mw:.1f} MW<br>"
                    f"Risk: {row.peak_risk}"
                )
                for row in map_df.itertuples(index=False)
            ],
            hovertemplate="%{text}<extra></extra>",
            name="Energy regions",
        )
    )

    fig.update_layout(
        template="plotly_dark",
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        mapbox={
            "style": "open-street-map",
            "zoom": 2.2,
            "center": {"lat": float(map_df["lat"].mean()), "lon": float(map_df["lon"].mean())},
        },
        title="Energy Grid Map",
        showlegend=False,
    )
    return fig
