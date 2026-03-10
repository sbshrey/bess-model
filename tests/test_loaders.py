from __future__ import annotations

import csv

import pytest

from bess_model.config import SimulationConfig
from bess_model.data.loaders import load_generation_data


def test_load_generation_data_normalizes_units_and_parses_timestamps(tmp_path) -> None:
    solar_path = tmp_path / "solar.csv"
    wind_path = tmp_path / "wind.csv"
    _write_csv(
        solar_path,
        ["timestamp", "Power in KW"],
        [
            ["01/01/2025 06:42", "1200"],
            ["01/01/2025 06:43", "1800"],
        ],
    )
    _write_csv(
        wind_path,
        ["time stamp", "Power in KW"],
        [
            ["2025-01-01 06:42", "500"],
            ["2025-01-01 06:43", "750"],
        ],
    )

    config = _config_dict(str(solar_path), str(wind_path))
    solar, wind = load_generation_data(SimulationConfig.from_dict(config))

    assert solar.columns == ["timestamp", "solar_kw"]
    assert wind.columns == ["timestamp", "wind_kw"]
    assert solar[0, "solar_kw"] == pytest.approx(1200.0)
    assert wind[1, "wind_kw"] == pytest.approx(750.0)


def test_load_generation_data_rejects_duplicate_timestamps(tmp_path) -> None:
    solar_path = tmp_path / "solar.csv"
    wind_path = tmp_path / "wind.csv"
    _write_csv(
        solar_path,
        ["timestamp", "Power in KW"],
        [
            ["01/01/2025 06:42", "1200"],
            ["01/01/2025 06:42", "1800"],
        ],
    )
    _write_csv(
        wind_path,
        ["time stamp", "Power in KW"],
        [["2025-01-01 06:42", "500"]],
    )

    config = SimulationConfig.from_dict(_config_dict(str(solar_path), str(wind_path)))

    with pytest.raises(ValueError, match="duplicate timestamps"):
        load_generation_data(config)


def _config_dict(solar_path: str, wind_path: str) -> dict[str, object]:
    return {
        "plant_name": "test_plant",
        "data": {"solar_path": solar_path, "wind_path": wind_path},
        "preprocessing": {"frequency": "1m", "gap_fill": "linear_interpolate", "max_interpolation_gap_minutes": 15},
        "grid": {"export_limit_kw": 1000.0, "import_limit_kw": None},
        "load": {"output_profile_kw": 400.0, "aux_consumption_kw": 20.0},
        "battery": {
            "capacity_kwh": 1000.0,
            "max_charge_kw": 1000.0,
            "max_discharge_kw": 1000.0,
            "charge_efficiency": 0.96,
            "discharge_efficiency": 0.94,
            "initial_soc_kwh": 500.0,
        },
        "sizing": {"capacities_kwh": [1000.0], "objective": "min_grid_import_then_smallest"},
    }


def _write_csv(path, header, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
