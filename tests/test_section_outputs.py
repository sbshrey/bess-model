from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from bess_model.config import SimulationConfig
from bess_model.core.pipeline import SimulationContext, simulate_system, write_stage_outputs
from bess_model.flows.section_outputs import section_accounting_stage

def test_invariant_battery_bounds_and_flows() -> None:
    # capacity 1.0 kWh, degraded over time, to test bounds
    config = _section_config(capacity_kwh=1.0, initial_soc_fraction=1.0, degradation_per_cycle=0.01)
    context = SimulationContext(config=config, logger=logging.getLogger("test.sections"))
    
    # 40 rows representing heavy cycling
    df = pl.DataFrame(
        {
            "timestamp": [datetime(2025, 1, 1, 0, index) for index in range(40)],
            "wind_kw": [0.0] * 40,
            "solar_kw": [0.0] * 40,
            # heavy over-generation for first 20, heavy under-generation for next 20
            "total_generation_kw": [100.0 if i < 20 else 0.0 for i in range(40)],
            "output_profile_kw": [0.0] * 40,
            "aux_consumption_kw": [0.0] * 40,
            "site_load_kw": [0.0 if i < 20 else 100.0 for i in range(40)],
        }
    )

    result = section_accounting_stage(df, context)

    # Invariant: battery never goes below zero, never opens/closes above capacity_now_kwh
    capacity_now = result["capacity_now_kw_min"].to_list()
    opening = result["battery_opening_kw_min"].to_list()
    closing = result["battery_closing_kw_min"].to_list()

    for cap, o, c in zip(capacity_now, opening, closing):
        assert o >= 0.0
        assert c >= 0.0
        assert o <= cap + 1e-9
        assert c <= cap + 1e-9

    # Invariant: charging never exceeds remaining headroom
    store_available = result["battery_store_available_kw"].to_list()
    store_final = result["battery_store_final_kw"].to_list()
    
    for cap, o, s_a, s_f in zip(capacity_now, opening, store_available, store_final):
        headroom_kw = max(cap - o, 0.0)
        assert s_a <= headroom_kw + 1e-9
        assert s_f <= headroom_kw + 1e-9

    # Invariant: discharge never exceeds available stored energy
    required_draw = result["battery_draw_required_kw"].to_list()
    draw_loss = result["battery_draw_loss_kw"].to_list()
    total_draw = result["battery_draw_final_kw"].to_list()
    
    for o, d_r, d_l, d_t in zip(opening, required_draw, draw_loss, total_draw):
        available_discharge_kw = o
        assert d_r <= available_discharge_kw + 1e-9
        assert d_t <= available_discharge_kw + 1e-9

    # Invariant: grid buy occurs only after battery discharge is exhausted
    grid_buy = result["grid_buy_kw"].to_list()
    deficit = result["deficit_power_kw"].to_list()
    
    for gb, def_kw, d_r, d_t, o in zip(grid_buy, deficit, required_draw, total_draw, opening):
        if gb > 0.0:
            # We bought from grid, meaning we had a deficit we couldn't fully meet
            # Therefore battery must have given everything it successfully could
            assert abs(o - d_t) < 1e-3 or d_r == def_kw
            
    # Invariant: Both identity equations pass
    assert all(ok == 1 for ok in result["identity_1_ok"].to_list())
    assert all(ok == 1 for ok in result["identity_2_ok"].to_list())

def test_write_stage_outputs_writes_split_section_outputs(tmp_path) -> None:
    solar_path = tmp_path / "solar.csv"
    wind_path = tmp_path / "wind.csv"
    solar_path.write_text("timestamp,Power in KW\n01/01/2025 00:00,0\n01/01/2025 00:01,500\n", encoding="utf-8")
    wind_path.write_text("time stamp,Power in KW\n2025-01-01 00:00,50\n2025-01-01 00:01,0\n", encoding="utf-8")
    config = SimulationConfig.from_dict(
        {
            "plant_name": "section_outputs_case",
            "output_dir": str(tmp_path / "output"),
            "data": {"solar_path": str(solar_path), "wind_path": str(wind_path)},
            "preprocessing": {"frequency": "1m", "gap_fill": "linear_interpolate", "max_interpolation_gap_minutes": 15, "align_to_full_year": False, "simulation_dtype": "float64"},
            "grid": {"export_limit_kw": 100.0, "import_limit_kw": None},
            "load": {"output_profile_kw": 40.0, "aux_consumption_kw": 10.0},
            "battery": {
                "capacity_kwh": 100.0,
                "max_charge_kw": 100.0,
                "max_discharge_kw": 100.0,
                "charge_efficiency": 1.0,
                "discharge_efficiency": 1.0,
                "initial_soc_kwh": 100.0,
            },
            "sizing": {"capacities_kwh": [100.0]},
        }
    )

    result = simulate_system(config)
    assert result.summary_metrics["identity_1_failures"] == 0
    assert result.summary_metrics["identity_2_failures"] == 0

    aligned_input, context = _aligned_inputs(config)
    written = write_stage_outputs(aligned_input, context, tmp_path / "output", config.plant_name)
    section_path = tmp_path / "output" / "section_outputs_case_sections" / "08_consume_from_grid.csv"

    assert section_path in written
    assert section_path.exists()
    section_df = pl.read_csv(section_path, try_parse_dates=True)
    assert "grid_buy_kw" in section_df.columns

def _section_config(
    *,
    capacity_kwh: float,
    initial_soc_fraction: float,
    degradation_per_cycle: float = 0.0002739726027,
) -> SimulationConfig:
    return SimulationConfig.from_dict(
        {
            "plant_name": "section_test",
            "data": {"solar_path": "unused.csv", "wind_path": "unused.csv"},
            "preprocessing": {"frequency": "1m", "gap_fill": "linear_interpolate", "max_interpolation_gap_minutes": 15, "align_to_full_year": False, "simulation_dtype": "float64"},
            "grid": {"export_limit_kw": 400.0, "import_limit_kw": None},
            "load": {"output_profile_kw": 400.0, "aux_consumption_kw": 20.0},
            "battery": {
                "nominal_power_kw": capacity_kwh / 2.0,
                "duration_hours": 2.0,
                "initial_soc_fraction": initial_soc_fraction,
                "degradation_per_cycle": degradation_per_cycle,
            },
            "sizing": {"capacities_kwh": [capacity_kwh]},
        }
    )

def _aligned_inputs(config: SimulationConfig) -> tuple[pl.DataFrame, SimulationContext]:
    from bess_model.core.pipeline import load_aligned_inputs
    return load_aligned_inputs(config)

def test_lookup_loss_rate_interpolation() -> None:
    from bess_model.flows.section_outputs import _lookup_loss_rate
    
    loss_table = {
        0.2: 0.04,
        0.3: 0.045,
        0.5: 0.07,
        1.0: 0.11,
        1.2: 0.14
    }
    
    # Below min bounds
    assert _lookup_loss_rate(0.1, loss_table) == 0.04
    # Exact match
    assert _lookup_loss_rate(0.3, loss_table) == 0.045
    # Interpolation exactly halfway
    # Between 0.3 (0.045) and 0.5 (0.07): 0.4 should be 0.045 + 0.5 * (0.07 - 0.045) = 0.045 + 0.0125 = 0.0575
    assert _lookup_loss_rate(0.4, loss_table) == pytest.approx(0.0575)
    # Above max bounds
    assert _lookup_loss_rate(1.5, loss_table) == 0.14
