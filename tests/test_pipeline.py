from __future__ import annotations

import csv

import pytest
import polars as pl

from bess_model.config import SimulationConfig
from bess_model.core.pipeline import load_aligned_inputs, simulate_system, write_stage_outputs


def test_simulate_system_produces_expected_grid_flows(tmp_path) -> None:
    solar_path = tmp_path / "solar.csv"
    wind_path = tmp_path / "wind.csv"
    _write_csv(
        solar_path,
        ["timestamp", "Power in KW"],
        [
            ["01/01/2025 00:00", "800"],
            ["01/01/2025 00:01", "200"],
            ["01/01/2025 00:02", "0"],
        ],
    )
    _write_csv(
        wind_path,
        ["time stamp", "Power in KW"],
        [
            ["2025-01-01 00:00", "0"],
            ["2025-01-01 00:01", "0"],
            ["2025-01-01 00:02", "0"],
        ],
    )

    config = SimulationConfig.from_dict(
        {
            "plant_name": "dispatch_case",
            "data": {"solar_path": str(solar_path), "wind_path": str(wind_path)},
            "preprocessing": {"frequency": "1m", "gap_fill": "linear_interpolate", "max_interpolation_gap_minutes": 15},
            "grid": {"export_limit_kw": 100.0, "import_limit_kw": None},
            "load": {"output_profile_kw": 400.0, "aux_consumption_kw": 20.0},
            "battery": {
                "capacity_kwh": 1000.0,
                "max_charge_kw": 200.0,
                "max_discharge_kw": 200.0,
                "charge_efficiency": 1.0,
                "discharge_efficiency": 1.0,
                "initial_soc_kwh": 0.0,
            },
            "sizing": {"capacities_kwh": [1000.0], "objective": "min_grid_import_then_smallest"},
        }
    )

    result = simulate_system(config)
    flows = result.minute_flows

    expected_columns = {
        "timestamp",
        "solar_kw",
        "wind_kw",
        "total_generation_kw",
        "grid_buy_kw",
        "grid_sell_kw",
        "soc_pct",
    }
    assert expected_columns.issubset(set(flows.columns))
    assert flows[0, "battery_store_available_kw"] == pytest.approx(380.0)
    assert flows[0, "grid_sell_kw"] == pytest.approx(0.0)
    assert flows[1, "battery_draw_required_kw"] == pytest.approx(220.0)
    assert flows[1, "grid_buy_kw"] >= 0.0
    assert flows[2, "grid_buy_kw"] == pytest.approx(286.91, abs=1e-2)
    assert result.summary_metrics["max_identity_error_kw"] <= 1e-9
    assert result.summary_metrics["grid_import_energy_kwh"] >= 0.0


def test_write_stage_outputs_writes_csv_for_each_stage(tmp_path) -> None:
    solar_path = tmp_path / "solar.csv"
    wind_path = tmp_path / "wind.csv"
    _write_csv(
        solar_path,
        ["timestamp", "Power in KW"],
        [
            ["01/01/2025 00:00", "800"],
            ["01/01/2025 00:01", "200"],
        ],
    )
    _write_csv(
        wind_path,
        ["time stamp", "Power in KW"],
        [
            ["2025-01-01 00:00", "0"],
            ["2025-01-01 00:01", "0"],
        ],
    )
    config = SimulationConfig.from_dict(
        {
            "plant_name": "stage_dump_case",
            "data": {"solar_path": str(solar_path), "wind_path": str(wind_path)},
            "preprocessing": {"frequency": "1m", "gap_fill": "linear_interpolate", "max_interpolation_gap_minutes": 15},
            "grid": {"export_limit_kw": 100.0, "import_limit_kw": None},
            "load": {"output_profile_kw": 400.0, "aux_consumption_kw": 20.0},
            "battery": {
                "capacity_kwh": 1000.0,
                "max_charge_kw": 200.0,
                "max_discharge_kw": 200.0,
                "charge_efficiency": 1.0,
                "discharge_efficiency": 1.0,
                "initial_soc_kwh": 0.0,
            },
            "sizing": {"capacities_kwh": [1000.0], "objective": "min_grid_import_then_smallest"},
        }
    )

    aligned_input, context = load_aligned_inputs(config)
    paths = write_stage_outputs(aligned_input, context, tmp_path / "output", config.plant_name)

    assert len(paths) == 15
    assert paths[0].name == "00_aligned_input.csv"
    assert paths[1].name == "01_wind_solar_generation.csv"
    wind_solar_df = pl.read_csv(paths[1], try_parse_dates=True)
    assert "total_generation_kw" in wind_solar_df.columns
    section_path = tmp_path / "output" / "stage_dump_case_sections" / "08_consume_from_grid.csv"
    assert section_path.exists()
    section_df = pl.read_csv(section_path, try_parse_dates=True)
    assert "grid_buy_kw" in section_df.columns


def _write_csv(path, header, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
