from __future__ import annotations

from datetime import datetime

import pytest
import polars as pl

from bess_model.config import PreprocessingConfig
from bess_model.data.preprocessing import align_generation_to_minute


def test_align_generation_to_minute_interpolates_short_gaps_and_zero_fills_long_gaps() -> None:
    solar = pl.DataFrame(
        {
            "timestamp": [
                datetime(2025, 1, 1, 0, 0),
                datetime(2025, 1, 1, 0, 2),
                datetime(2025, 1, 1, 0, 20),
            ],
            "solar_kw": [0.0, 120.0, 300.0],
        }
    )
    wind = pl.DataFrame(
        {
            "timestamp": [datetime(2025, 1, 1, 0, 1), datetime(2025, 1, 1, 0, 2)],
            "wind_kw": [100.0, 200.0],
        }
    )

    result = align_generation_to_minute(
        solar,
        wind,
        PreprocessingConfig(max_interpolation_gap_minutes=3),
    )

    assert result.filter(pl.col("timestamp") == datetime(2025, 1, 1, 0, 1))[0, "solar_kw"] == pytest.approx(60.0)
    assert result.filter(pl.col("timestamp") == datetime(2025, 1, 1, 0, 10))[0, "solar_kw"] == pytest.approx(0.0)
    assert result.filter(pl.col("timestamp") == datetime(2025, 1, 1, 0, 0))[0, "wind_kw"] == pytest.approx(0.0)
    assert result.filter(pl.col("timestamp") == datetime(2025, 1, 1, 0, 2))[0, "total_generation_kw"] == pytest.approx(320.0)
