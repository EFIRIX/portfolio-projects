from __future__ import annotations

from typing import Any

import pandas as pd


def normalize_timestamp(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp",
) -> pd.DataFrame:
    """
    Normalize timestamps to naive UTC for deterministic downstream processing.
    """
    normalized = df.copy()
    if timestamp_column not in normalized.columns:
        return normalized

    normalized[timestamp_column] = pd.to_datetime(
        normalized[timestamp_column],
        errors="coerce",
        utc=True,
    )
    normalized[timestamp_column] = normalized[timestamp_column].dt.tz_convert("UTC").dt.tz_localize(None)
    return normalized


def deduplicate_timeseries(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp",
    sort_columns: list[str] | None = None,
    keep: str = "last",
) -> pd.DataFrame:
    """
    Apply stable ordering and remove duplicate timestamps deterministically.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=df.columns if isinstance(df, pd.DataFrame) else [])

    if timestamp_column not in df.columns:
        return df.copy().reset_index(drop=True)

    ordered = df.copy()
    ordering = [timestamp_column]
    if sort_columns:
        for column in sort_columns:
            if column in ordered.columns and column not in ordering:
                ordering.append(column)

    ordered = ordered.sort_values(ordering, kind="mergesort")
    ordered = ordered.drop_duplicates(subset=[timestamp_column], keep=keep)
    ordered = ordered.sort_values(ordering, kind="mergesort")
    return ordered.reset_index(drop=True)


def validate_numeric_columns(
    df: pd.DataFrame,
    numeric_columns: list[str] | tuple[str, ...],
    drop_invalid_rows: bool = True,
) -> dict[str, Any]:
    """
    Coerce selected columns to numeric and validate they contain valid values.
    """
    cleaned = df.copy()
    missing_columns = [col for col in numeric_columns if col not in cleaned.columns]
    if missing_columns:
        return {
            "valid": False,
            "reason": f"missing_columns:{','.join(missing_columns)}",
            "dataframe": cleaned,
            "rows": int(len(cleaned)),
        }

    for column in numeric_columns:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    if drop_invalid_rows:
        cleaned = cleaned.dropna(subset=list(numeric_columns))

    has_values = all(bool(cleaned[column].notna().any()) for column in numeric_columns)
    if not has_values or cleaned.empty:
        return {
            "valid": False,
            "reason": "numeric_columns_invalid",
            "dataframe": cleaned,
            "rows": int(len(cleaned)),
        }

    return {
        "valid": True,
        "reason": "ok",
        "dataframe": cleaned,
        "rows": int(len(cleaned)),
    }

