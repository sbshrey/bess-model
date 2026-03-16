"""CSV loaders for solar and wind generation data."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from bess_model.config import SimulationConfig


SOLAR_TIMESTAMP_COLUMN = "timestamp"
SOLAR_POWER_COLUMN = "Power in KW"
WIND_TIMESTAMP_COLUMN = "time stamp"
WIND_POWER_COLUMN = "Power in KW"

# Hardcoded filenames under data_dir (paths are not user-editable)
SOLAR_FILENAME = "Solar_2025-01-01_data_.csv"
WIND_FILENAME = "Wind_2025_01-01_data_.csv"


def load_generation_data(config: SimulationConfig) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Load solar and/or wind from hardcoded paths under config.data.data_dir (or overrides for tests)."""
    data_dir = config.data.data_dir or "data"
    solar_path = config.data.solar_path_override or f"{data_dir.rstrip('/')}/{SOLAR_FILENAME}"
    wind_path = config.data.wind_path_override or f"{data_dir.rstrip('/')}/{WIND_FILENAME}"
    load_solar = config.data.solar_enabled
    load_wind = config.data.wind_enabled

    if not load_solar and not load_wind:
        raise ValueError("At least one of solar_enabled or wind_enabled must be True.")

    if load_solar and load_wind:
        solar = _load_source_csv(
            path=solar_path,
            timestamp_column=SOLAR_TIMESTAMP_COLUMN,
            power_column=SOLAR_POWER_COLUMN,
            timestamp_format="%d/%m/%Y %H:%M",
            source_name="solar",
        )
        wind = _load_source_csv(
            path=wind_path,
            timestamp_column=WIND_TIMESTAMP_COLUMN,
            power_column=WIND_POWER_COLUMN,
            timestamp_format="%Y-%m-%d %H:%M",
            source_name="wind",
        )
        return solar, wind

    if load_solar:
        solar = _load_source_csv(
            path=solar_path,
            timestamp_column=SOLAR_TIMESTAMP_COLUMN,
            power_column=SOLAR_POWER_COLUMN,
            timestamp_format="%d/%m/%Y %H:%M",
            source_name="solar",
        )
        wind = solar.select("timestamp").with_columns(pl.lit(0.0).cast(pl.Float32).alias("wind_kw"))
        return solar, wind

    # Wind only
    wind = _load_source_csv(
        path=wind_path,
        timestamp_column=WIND_TIMESTAMP_COLUMN,
        power_column=WIND_POWER_COLUMN,
        timestamp_format="%Y-%m-%d %H:%M",
        source_name="wind",
    )
    solar = wind.select("timestamp").with_columns(pl.lit(0.0).cast(pl.Float32).alias("solar_kw"))
    return solar, wind


def _load_source_csv(
    *,
    path: str,
    timestamp_column: str,
    power_column: str,
    timestamp_format: str,
    source_name: str,
) -> pl.DataFrame:
    """Load a source CSV and normalize timestamp/power columns."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"{source_name} file not found: {csv_path}")

    frame = pl.read_csv(csv_path)
    missing_columns = {timestamp_column, power_column}.difference(frame.columns)
    if missing_columns:
        joined = ", ".join(sorted(missing_columns))
        raise ValueError(f"{source_name} file is missing columns: {joined}")

    normalized = (
        frame.select(
            pl.col(timestamp_column).cast(pl.String).str.strip_chars().alias("timestamp_raw"),
            pl.col(power_column).cast(pl.Float32).alias(f"{source_name}_kw"),
        )
        .filter(pl.col("timestamp_raw") != "")
        .with_columns(
            pl.col("timestamp_raw")
            .str.strptime(pl.Datetime, format=timestamp_format, strict=True)
            .alias("timestamp"),
            pl.col(f"{source_name}_kw").alias(f"{source_name}_kw"),
        )
        .select("timestamp", f"{source_name}_kw")
        .sort("timestamp")
    )

    _validate_source_frame(normalized, source_name)
    return normalized


def _validate_source_frame(frame: pl.DataFrame, source_name: str) -> None:
    """Reject null timestamps, null powers, or duplicate timestamps."""
    if frame.height == 0:
        raise ValueError(f"{source_name} dataset is empty after parsing.")
    null_count = frame.select(
            pl.sum_horizontal(
                pl.col("timestamp").is_null().cast(pl.Int64),
                pl.col(f"{source_name}_kw").is_null().cast(pl.Int64),
            ).sum()
        ).item()
    if null_count:
        raise ValueError(f"{source_name} dataset contains null timestamps or power values.")
    duplicate_count = frame.select(pl.col("timestamp").is_duplicated().sum()).item()
    if duplicate_count:
        raise ValueError(f"{source_name} dataset contains duplicate timestamps.")
