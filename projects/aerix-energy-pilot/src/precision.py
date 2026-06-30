from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_DIGITS = 6


def round_float(value: Any, digits: int = DEFAULT_DIGITS) -> float:
    """Round a numeric value to fixed precision using deterministic half-up rounding."""
    if value is None:
        return 0.0

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0

    if not np.isfinite(numeric):
        return 0.0

    quant = Decimal("1").scaleb(-int(digits))
    rounded = Decimal(str(numeric)).quantize(quant, rounding=ROUND_HALF_UP)
    return float(rounded)


def round_series(series: pd.Series, digits: int = DEFAULT_DIGITS) -> pd.Series:
    """Round numeric pandas Series to fixed precision."""
    rounded = pd.to_numeric(series.copy(), errors="coerce").fillna(0.0)
    return rounded.apply(lambda value: round_float(value, digits=digits))


def round_df(df: pd.DataFrame, digits: int = DEFAULT_DIGITS, numeric_only: bool = True) -> pd.DataFrame:
    """Round numeric columns in DataFrame to fixed precision."""
    rounded = df.copy()
    if rounded.empty:
        return rounded

    if numeric_only:
        numeric_columns = [
            column
            for column in rounded.select_dtypes(include=["number"]).columns
            if str(rounded[column].dtype) != "bool"
        ]
    else:
        numeric_columns = rounded.columns

    for column in numeric_columns:
        rounded[column] = pd.to_numeric(rounded[column], errors="coerce").fillna(0.0)
        rounded[column] = rounded[column].apply(lambda value: round_float(value, digits=digits))

    return rounded


def canonicalize_for_compare(obj: Any, digits: int = DEFAULT_DIGITS) -> Any:
    """Convert nested objects into deterministic, rounded, comparison-safe shape."""
    if isinstance(obj, pd.DataFrame):
        normalized = round_df(obj, digits=digits, numeric_only=True).copy()
        normalized.columns = [str(col) for col in normalized.columns]
        normalized = normalized.reindex(sorted(normalized.columns), axis=1)
        return [
            {str(key): canonicalize_for_compare(value, digits=digits) for key, value in sorted(row.items())}
            for row in normalized.to_dict(orient="records")
        ]

    if isinstance(obj, pd.Series):
        return [canonicalize_for_compare(value, digits=digits) for value in round_series(obj, digits=digits).tolist()]

    if isinstance(obj, Mapping):
        return {
            str(key): canonicalize_for_compare(value, digits=digits)
            for key, value in sorted(obj.items(), key=lambda item: str(item[0]))
        }

    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        return [canonicalize_for_compare(value, digits=digits) for value in obj]

    if isinstance(obj, (np.integer, int)):
        return int(obj)

    if isinstance(obj, (np.floating, float, Decimal)):
        return round_float(obj, digits=digits)

    if isinstance(obj, (pd.Timestamp, np.datetime64)):
        return str(pd.Timestamp(obj))

    if obj is None:
        return None

    return obj
