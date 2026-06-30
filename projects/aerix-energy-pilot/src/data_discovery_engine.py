from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SOURCES_CONFIG = Path("data_sources") / "sources.json"


PROVIDER_CATALOG: list[dict[str, Any]] = [
    {
        "dataset_name": "Hourly Energy Consumption (PJM)",
        "source": "Kaggle",
        "provider_key": "kaggle",
        "download_url": "https://www.kaggle.com/datasets/robikscube/hourly-energy-consumption",
        "type": "kaggle",
        "dataset": "robikscube/hourly-energy-consumption",
        "freshness_year": 2018,
        "schema_hint": ["timestamp", "consumption"],
        "description": "Regional hourly load time series for PJM zones.",
        "download_enabled": False,
    },
    {
        "dataset_name": "UCI Individual Household Electric Power Consumption",
        "source": "UCI ML Repository",
        "provider_key": "uci",
        "download_url": "https://archive.ics.uci.edu/ml/datasets/individual+household+electric+power+consumption",
        "type": "http",
        "url": "https://archive.ics.uci.edu/static/public/235/individual+household+electric+power+consumption.zip",
        "freshness_year": 2012,
        "schema_hint": ["datetime", "power"],
        "description": "Household minute-level power readings.",
        "download_enabled": False,
    },
    {
        "dataset_name": "Open Power System Data - Time Series",
        "source": "Open Power System Data",
        "provider_key": "opsd",
        "download_url": "https://open-power-system-data.org/",
        "type": "http",
        "url": "https://data.open-power-system-data.org/time_series/latest/time_series_60min_singleindex.csv",
        "freshness_year": datetime.now(timezone.utc).year,
        "schema_hint": ["timestamp", "load"],
        "description": "European power system time series, load and generation.",
        "download_enabled": False,
    },
    {
        "dataset_name": "ENTSO-E Transparency Platform",
        "source": "ENTSO-E",
        "provider_key": "entsoe",
        "download_url": "https://transparency.entsoe.eu/",
        "type": "api",
        "endpoint": "https://transparency.entsoe.eu/api",
        "freshness_year": datetime.now(timezone.utc).year,
        "schema_hint": ["timestamp", "load"],
        "description": "Cross-border and national load data for Europe.",
        "download_enabled": False,
    },
    {
        "dataset_name": "EIA Hourly Electric Grid Monitor",
        "source": "US EIA",
        "provider_key": "eia",
        "download_url": "https://www.eia.gov/opendata/",
        "type": "api",
        "endpoint": "https://api.eia.gov/v2/electricity/rto/",
        "freshness_year": datetime.now(timezone.utc).year,
        "schema_hint": ["period", "value"],
        "description": "US ISO/RTO operational load and generation metrics.",
        "download_enabled": False,
    },
    {
        "dataset_name": "NASA POWER Hourly Meteorology",
        "source": "NASA POWER",
        "provider_key": "nasa_power",
        "download_url": "https://power.larc.nasa.gov/",
        "type": "api",
        "endpoint": "https://power.larc.nasa.gov/api/temporal/hourly/point",
        "freshness_year": datetime.now(timezone.utc).year,
        "schema_hint": ["timestamp", "temperature", "irradiance"],
        "description": "Hourly weather and solar resource data.",
        "download_enabled": False,
    },
    {
        "dataset_name": "Google Dataset Search - Energy Time Series",
        "source": "Google Dataset Search",
        "provider_key": "google_dataset_search",
        "download_url": "https://datasetsearch.research.google.com/",
        "type": "http",
        "url": "https://datasetsearch.research.google.com/search?query=energy%20time%20series",
        "freshness_year": datetime.now(timezone.utc).year,
        "schema_hint": ["timestamp", "consumption"],
        "description": "Discovery index for publicly available energy datasets.",
        "download_enabled": False,
    },
    {
        "dataset_name": "World Bank Energy Use Indicators",
        "source": "World Bank",
        "provider_key": "world_bank",
        "download_url": "https://databank.worldbank.org/source/world-development-indicators",
        "type": "api",
        "endpoint": "https://api.worldbank.org/v2/",
        "freshness_year": datetime.now(timezone.utc).year - 1,
        "schema_hint": ["year", "indicator", "value"],
        "description": "Country-level energy indicators and related macro metrics.",
        "download_enabled": False,
    },
    {
        "dataset_name": "AWS Open Data - Energy Datasets",
        "source": "AWS Open Data",
        "provider_key": "aws_open_data",
        "download_url": "https://registry.opendata.aws/",
        "type": "http",
        "url": "https://registry.opendata.aws/",
        "freshness_year": datetime.now(timezone.utc).year,
        "schema_hint": ["timestamp", "energy"],
        "description": "Catalog of public energy datasets hosted on AWS.",
        "download_enabled": False,
    },
]


def _load_config(path: str | Path = DEFAULT_SOURCES_CONFIG) -> dict[str, Any]:
    cfg = Path(path)
    if not cfg.exists():
        return {}
    try:
        payload = json.loads(cfg.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def fetch_dataset_metadata(dataset_source: dict[str, Any]) -> dict[str, Any]:
    item = dict(dataset_source)
    name = str(item.get("dataset_name") or item.get("name") or "dataset")
    description = str(item.get("description") or "").lower()

    energy_keywords = ("energy", "power", "load", "electric", "grid", "consumption")
    ts_keywords = ("hour", "daily", "time series", "timestamp", "datetime")

    relevance = 1.0 if any(word in description for word in energy_keywords) else 0.6
    ts_structure = 1.0 if any(word in description for word in ts_keywords) else 0.5

    freshness_year = int(item.get("freshness_year", datetime.now(timezone.utc).year - 5))
    age_years = max(0, datetime.now(timezone.utc).year - freshness_year)
    freshness = max(0.0, min(1.0, 1.0 - (age_years / 10.0)))

    schema_hint = [str(col).lower() for col in item.get("schema_hint", [])]
    schema_compat = 1.0 if ("timestamp" in schema_hint or "datetime" in schema_hint) and (
        "consumption" in schema_hint or "load" in schema_hint or "power" in schema_hint or "value" in schema_hint
    ) else 0.5

    return {
        "dataset_name": name,
        "source": str(item.get("source") or item.get("provider_key") or "unknown"),
        "type": str(item.get("type") or "http"),
        "download_url": str(item.get("download_url") or item.get("url") or item.get("endpoint") or ""),
        "relevance_score": float(relevance),
        "time_series_score": float(ts_structure),
        "freshness_score": float(freshness),
        "schema_compatibility_score": float(schema_compat),
        "download_enabled": bool(item.get("download_enabled", True)),
        "raw": item,
    }


def rank_discovered_datasets(discovered_datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for item in discovered_datasets:
        metadata = fetch_dataset_metadata(item)
        rank_score = (
            metadata["relevance_score"] * 0.35
            + metadata["time_series_score"] * 0.30
            + metadata["freshness_score"] * 0.20
            + metadata["schema_compatibility_score"] * 0.15
        )
        metadata["rank_score"] = float(rank_score)
        ranked.append(metadata)
    ranked.sort(key=lambda row: (-row.get("rank_score", 0.0), row.get("dataset_name", "")))
    return ranked


def _config_http_feeds(payload: dict[str, Any]) -> list[dict[str, Any]]:
    feeds = payload.get("datasets", [])
    if not isinstance(feeds, list):
        return []

    records: list[dict[str, Any]] = []
    for item in feeds:
        if not isinstance(item, dict):
            continue
        normalized = {
            "dataset_name": str(item.get("name") or "configured_dataset"),
            "source": str(item.get("source") or item.get("type") or "config"),
            "provider_key": str(item.get("type") or "http").lower(),
            "type": str(item.get("type") or "http").lower(),
            "download_url": str(item.get("download_url") or item.get("url") or item.get("endpoint") or ""),
            "url": item.get("url"),
            "endpoint": item.get("endpoint"),
            "dataset": item.get("dataset"),
            "schema_hint": item.get("schema_hint", ["timestamp", "consumption"]),
            "description": str(item.get("description") or "Configured data source"),
            "freshness_year": int(item.get("freshness_year", datetime.now(timezone.utc).year)),
            "download_enabled": bool(item.get("download_enabled", True)),
        }
        records.append(normalized)
    return records


def discover_energy_datasets(sources_config: str | Path = DEFAULT_SOURCES_CONFIG) -> list[dict[str, Any]]:
    payload = _load_config(sources_config)
    discovered = list(PROVIDER_CATALOG)
    discovered.extend(_config_http_feeds(payload))
    ranked = rank_discovered_datasets(discovered)
    return ranked
