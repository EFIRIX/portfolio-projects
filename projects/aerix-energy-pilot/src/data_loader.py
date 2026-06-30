from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AEP_DATA_PATH = PROJECT_ROOT / "data" / "AEP_hourly.csv"
DEFAULT_BUILDING_DATA_PATH = PROJECT_ROOT / "data" / "building_energy.csv"
DEFAULT_GRID_DATA_DIR = PROJECT_ROOT / "data"
AEP_REQUIRED_COLUMNS = ["Datetime", "AEP_MW"]


def _validate_aep_columns(df: pd.DataFrame) -> None:
    missing = [col for col in AEP_REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required columns: {missing}. Expected source columns: {AEP_REQUIRED_COLUMNS}"
        )


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    columns_map = {col.strip().lower(): col for col in df.columns}
    for candidate in candidates:
        if candidate in columns_map:
            return columns_map[candidate]
    return None


def _find_energy_column(df: pd.DataFrame, timestamp_col: str) -> str:
    search_names = ["consumption", "energy", "meter_reading", "kwh", "power"]
    search_set = set(search_names)

    def normalize(name: str) -> str:
        return name.strip().lower().replace(" ", "_").replace("-", "_")

    matched_columns = [
        col
        for col in df.columns
        if col != timestamp_col and normalize(col) in search_set
    ]

    if len(matched_columns) == 1:
        return matched_columns[0]

    if len(matched_columns) > 1:
        numeric_matches = [col for col in matched_columns if pd.api.types.is_numeric_dtype(df[col])]
        if numeric_matches:
            return numeric_matches[0]

        convertible_matches = [
            col for col in matched_columns if pd.to_numeric(df[col], errors="coerce").notna().any()
        ]
        if convertible_matches:
            return convertible_matches[0]

        return matched_columns[0]

    # Fallback for compatibility when names do not match expected list.
    numeric_candidates = [
        col for col in df.columns if col != timestamp_col and pd.api.types.is_numeric_dtype(df[col])
    ]
    if numeric_candidates:
        return numeric_candidates[0]

    raise ValueError(
        "Could not identify building energy column. Expected one of: "
        "consumption, energy, meter_reading, kwh, power."
    )


def _find_grid_datetime_column(df: pd.DataFrame) -> str:
    timestamp_col = _find_column(df, ["datetime", "timestamp", "date_time", "date"])
    if timestamp_col is None:
        raise ValueError("Grid dataset must include a Datetime/timestamp column.")
    return timestamp_col


def _find_grid_mw_column(df: pd.DataFrame, timestamp_col: str) -> str:
    candidate_cols = [col for col in df.columns if col != timestamp_col]
    if not candidate_cols:
        raise ValueError("Grid dataset has no candidate load columns.")

    mw_named_cols = [col for col in candidate_cols if "_mw" in col.strip().lower()]

    def pick_numeric_or_convertible(columns: list[str]) -> str | None:
        if not columns:
            return None

        numeric_cols = [col for col in columns if pd.api.types.is_numeric_dtype(df[col])]
        if numeric_cols:
            return numeric_cols[0]

        best_col: str | None = None
        best_score = -1
        for col in columns:
            numeric_values = pd.to_numeric(df[col], errors="coerce")
            score = int(numeric_values.notna().sum())
            if score > best_score:
                best_score = score
                best_col = col

        if best_col is not None and best_score > 0:
            return best_col
        return None

    selected = pick_numeric_or_convertible(mw_named_cols)
    if selected is not None:
        return selected

    selected = pick_numeric_or_convertible(candidate_cols)
    if selected is not None:
        return selected

    raise ValueError("Could not identify MW/load column in grid dataset.")


def _load_single_grid_file(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    timestamp_col = _find_grid_datetime_column(df)
    mw_col = _find_grid_mw_column(df, timestamp_col)

    df = df[[timestamp_col, mw_col]].copy()
    df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors="coerce")
    df[mw_col] = pd.to_numeric(df[mw_col], errors="coerce")

    df = df.rename(columns={timestamp_col: "timestamp", mw_col: "consumption"})
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

    region_name = csv_path.stem.replace("grid_", "").strip() or csv_path.stem
    region_peak = float(pd.to_numeric(df["consumption"], errors="coerce").max())
    if not pd.notna(region_peak) or region_peak <= 0:
        region_peak = 1.0

    df["region_name"] = region_name
    df["region_peak"] = region_peak
    df["normalized_consumption"] = pd.to_numeric(df["consumption"], errors="coerce") / region_peak

    df = df.set_index("timestamp")

    loaded = df[["consumption", "normalized_consumption", "region_peak", "region_name"]]
    loaded.attrs["region_name"] = region_name
    loaded.attrs["region_peak"] = region_peak
    return loaded


def _resolve_grid_files(path: Path) -> list[Path]:
    if path.exists() and path.is_dir():
        search_dir = path
    elif path.suffix.lower() == ".csv":
        search_dir = path.parent
    else:
        search_dir = DEFAULT_GRID_DATA_DIR

    files = sorted(search_dir.glob("grid_*.csv"))
    if files:
        return files

    # Backward-compatible fallback: use explicitly provided CSV or default AEP file.
    if path.exists() and path.is_file():
        return [path]
    if DEFAULT_AEP_DATA_PATH.exists():
        return [DEFAULT_AEP_DATA_PATH]
    return []


def _load_grid_data(path: Path) -> pd.DataFrame:
    grid_files = _resolve_grid_files(path)
    if not grid_files:
        raise FileNotFoundError(
            "No grid datasets found. Expected files matching data/grid_*.csv."
        )

    frames = [_load_single_grid_file(file_path) for file_path in grid_files]
    combined = pd.concat(frames, axis=0)
    combined = combined.sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]

    region_peaks = {
        str(file_path.stem.replace("grid_", "").strip() or file_path.stem): float(frame.attrs.get("region_peak", 1.0))
        for file_path, frame in zip(grid_files, frames)
    }

    combined.attrs["grid_file_count"] = len(grid_files)
    combined.attrs["grid_files"] = [str(p) for p in grid_files]
    combined.attrs["region_peaks"] = region_peaks
    return combined


def _load_aep_data(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    _validate_aep_columns(df)

    df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce")
    df = df.rename(columns={"Datetime": "timestamp", "AEP_MW": "consumption"})
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    df["consumption"] = pd.to_numeric(df["consumption"], errors="coerce")
    df = df.set_index("timestamp")
    return df[["consumption"]]


def _load_building_data(csv_path: Path, unit_conversion: bool = False) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    timestamp_col = _find_column(df, ["timestamp", "datetime", "date_time", "date"])
    if timestamp_col is None:
        raise ValueError("Building dataset must include a 'timestamp' (or datetime-like) column.")

    energy_col = _find_energy_column(df, timestamp_col)
    normalized_energy_col = energy_col.strip().lower().replace(" ", "_").replace("-", "_")

    # Keep only timestamp and selected energy column to avoid duplicate "consumption" labels.
    df = df[[timestamp_col, energy_col]].copy()

    df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors="coerce")
    df[energy_col] = pd.to_numeric(df[energy_col], errors="coerce")

    df = df.rename(columns={timestamp_col: "timestamp", energy_col: "consumption"})
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    df = df.set_index("timestamp")

    # Resample to hourly totals for sub-hourly building meter data.
    try:
        inferred = pd.infer_freq(df.index)
    except ValueError:
        inferred = None
    if inferred is None or inferred.lower() not in {"h"}:
        df = df[["consumption"]].resample("h").sum(min_count=1)
    else:
        df = df[["consumption"]]

    # Building mode: convert kWh per hour to MW-equivalent if enabled.
    if unit_conversion and "kwh" in normalized_energy_col:
        df["consumption"] = df["consumption"] / 1000.0

    return df


def load_energy_data(
    file_path: str | Path | None = None,
    dataset_name: str | None = None,
    unit_conversion: bool = False,
) -> pd.DataFrame:
    """
    Load energy data for the selected dataset.

    Supported datasets:
    - "grid": loads and combines files matching data/grid_*.csv
    - "aep": expects AEP format (Datetime, AEP_MW)
    - "building": loads data/building_energy.csv with timestamp + meter/energy column

    Returns one-column DataFrame indexed by timestamp:
    - consumption
    """
    normalized_name = (dataset_name or "grid").strip().lower()

    if normalized_name == "building":
        csv_path = Path(file_path) if file_path is not None else DEFAULT_BUILDING_DATA_PATH
        return _load_building_data(csv_path, unit_conversion=unit_conversion)

    if normalized_name == "grid":
        base_path = Path(file_path) if file_path is not None else DEFAULT_GRID_DATA_DIR
        return _load_grid_data(base_path)

    csv_path = Path(file_path) if file_path is not None else DEFAULT_AEP_DATA_PATH
    return _load_aep_data(csv_path)
