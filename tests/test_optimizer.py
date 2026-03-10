from __future__ import annotations

import polars as pl

from bess_model.config import SimulationConfig
from bess_model.results import SimulationResult
from bess_model.sizing import optimizer


def test_run_sizing_prefers_lowest_grid_import_then_smallest_capacity(monkeypatch) -> None:
    config = SimulationConfig.from_dict(
        {
            "plant_name": "sizing_case",
            "data": {"solar_path": "solar.csv", "wind_path": "wind.csv"},
            "preprocessing": {"frequency": "1m", "gap_fill": "linear_interpolate", "max_interpolation_gap_minutes": 15},
            "grid": {"export_limit_kw": 1000.0, "import_limit_kw": None},
            "load": {"output_profile_kw": 400.0, "aux_consumption_kw": 20.0},
            "battery": {
                "capacity_kwh": 1000.0,
                "max_charge_kw": 500.0,
                "max_discharge_kw": 500.0,
                "charge_efficiency": 0.96,
                "discharge_efficiency": 0.94,
                "initial_soc_kwh": 0.0,
            },
            "sizing": {"capacities_kwh": [1000.0, 2000.0, 3000.0], "objective": "min_grid_import_then_smallest"},
        }
    )

    def fake_simulate_system(run_config: SimulationConfig) -> SimulationResult:
        imported = 5.0 if run_config.battery.capacity_kwh == 1000.0 else 2.0
        return SimulationResult(
            minute_flows=pl.DataFrame({"timestamp": [], "grid_sell_kw": []}),
            summary_metrics={
                "plant_name": run_config.plant_name,
                "rows": 0,
                "grid_import_energy_kwh": imported,
                "grid_export_energy_kwh": 0.0,
                "final_degraded_capacity_kwh": run_config.battery.capacity_kwh,
                "final_soc_pct": 0.0,
                "cumulative_drawn_energy_kwh": 0.0,
                "cumulative_stored_energy_kwh": 0.0,
                "cumulative_charge_count": 0.0,
                "identity_1_failures": 0,
                "identity_2_failures": 0,
                "max_identity_error_kw": 0.0,
            },
        )

    monkeypatch.setattr(optimizer, "simulate_system", fake_simulate_system)

    result = optimizer.run_sizing(config)

    assert result.optimal_capacity_kwh == 2000.0
    assert list(result.results["battery_capacity_kwh"]) == [2000.0, 3000.0, 1000.0]
