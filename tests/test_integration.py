from __future__ import annotations

from datetime import datetime

import polars as pl
import pytest

from bess_model.config import SimulationConfig
from bess_model.core.pipeline import SimulationContext, run_pipeline


def test_pipeline_energy_balance_on_synthetic_minute_data() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [
                datetime(2025, 1, 1, 0, 0),
                datetime(2025, 1, 1, 0, 1),
                datetime(2025, 1, 1, 0, 2),
            ],
            "solar_kw": [500.0, 0.0, 700.0],
            "wind_kw": [0.0, 100.0, 0.0],
            "total_generation_kw": [500.0, 100.0, 700.0],
        }
    )
    config = SimulationConfig.from_dict(
        {
            "plant_name": "synthetic",
            "data": {"solar_path": "unused.csv", "wind_path": "unused.csv"},
            "preprocessing": {"frequency": "1m", "gap_fill": "linear_interpolate", "max_interpolation_gap_minutes": 15, "align_to_full_year": False},
            "grid": {"export_limit_kw": 200.0, "import_limit_kw": 1000.0},
            "load": {"output_profile_kw": 300.0, "aux_consumption_kw": 0.0},
            "battery": {
                "capacity_kwh": 50.0,
                "max_charge_kw": 300.0,
                "max_discharge_kw": 300.0,
                "charge_efficiency": 0.95,
                "discharge_efficiency": 0.95,
                "initial_soc_kwh": 0.0,
            },
            "sizing": {"capacities_kwh": [50.0], "objective": "min_grid_import_then_smallest"},
        }
    )

    result = run_pipeline(df, SimulationContext(config=config, logger=__import__("logging").getLogger("test")))

    assert result.select(pl.col("identity_1_error_kw").abs().max()).item() <= 1e-3
    assert result["grid_buy_kw"].sum() >= 0
    assert result["grid_sell_kw"].sum() >= 0
