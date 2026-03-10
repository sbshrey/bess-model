from __future__ import annotations

import logging
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from bess_model.config import SimulationConfig
from bess_model.core.pipeline import SimulationContext, simulate_system, write_stage_outputs
from bess_model.flows.section_outputs import section_accounting_stage

REFERENCE_MODEL_PATH = Path(__file__).resolve().parents[1] / "data" / "BESS Model on 1 min data.xlsx"
NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def test_section_accounting_stage_handles_deficit_charge_and_grid_paths() -> None:
    config = _section_config(capacity_kwh=1.0, initial_soc_fraction=1.0, degradation_per_cycle=0.0)
    context = SimulationContext(config=config, logger=logging.getLogger("test.sections"))
    df = pl.DataFrame(
        {
            "timestamp": [
                datetime(2025, 1, 1, 0, 0),
                datetime(2025, 1, 1, 0, 1),
                datetime(2025, 1, 1, 0, 2),
                datetime(2025, 1, 1, 0, 3),
            ],
            "wind_kw": [0.0, 0.0, 0.0, 0.0],
            "solar_kw": [0.0, 0.0, 0.0, 0.0],
            "total_generation_kw": [0.0, 0.0, 40.0, 70.0],
            "output_profile_kw": [0.0, 0.0, 0.0, 0.0],
            "aux_consumption_kw": [0.0, 0.0, 0.0, 0.0],
            "site_load_kw": [30.0, 40.0, 0.0, 0.0],
        }
    )

    result = section_accounting_stage(df, context)

    assert result[0, "battery_draw_required_kw"] == pytest.approx(30.0)
    assert result[0, "battery_draw_loss_rate"] == pytest.approx(0.067)
    assert result[0, "grid_buy_kw"] == pytest.approx(0.0)
    assert result[1, "grid_buy_kw"] == pytest.approx(12.01, abs=1e-2)
    assert result[1, "battery_closing_kw_min"] == pytest.approx(0.0)
    assert result[2, "battery_store_available_kw"] == pytest.approx(40.0)
    assert result[2, "battery_store_final_kw"] == pytest.approx(34.4)
    assert result[3, "grid_sell_kw"] == pytest.approx(44.4, abs=1e-6)

    full_result = section_accounting_stage(
        pl.DataFrame(
            {
                "timestamp": [datetime(2025, 1, 1, 1, 0)],
                "wind_kw": [0.0],
                "solar_kw": [0.0],
                "total_generation_kw": [70.0],
                "output_profile_kw": [0.0],
                "aux_consumption_kw": [0.0],
                "site_load_kw": [0.0],
            }
        ),
        context,
    )
    assert full_result[0, "battery_store_available_kw"] == pytest.approx(0.0)
    assert full_result[0, "grid_sell_kw"] == pytest.approx(70.0)


def test_section_accounting_stage_tracks_degradation_and_identity_columns() -> None:
    config = _section_config(capacity_kwh=10.0, initial_soc_fraction=1.0, degradation_per_cycle=0.01)
    context = SimulationContext(config=config, logger=logging.getLogger("test.sections"))
    df = pl.DataFrame(
        {
            "timestamp": [datetime(2025, 1, 1, 0, index) for index in range(3)],
            "wind_kw": [0.0, 0.0, 0.0],
            "solar_kw": [0.0, 0.0, 0.0],
            "total_generation_kw": [0.0, 20.0, 0.0],
            "output_profile_kw": [0.0, 0.0, 0.0],
            "aux_consumption_kw": [0.0, 0.0, 0.0],
            "site_load_kw": [5.0, 0.0, 5.0],
        }
    )

    result = section_accounting_stage(df, context)

    assert result[1, "current_cycle"] > 0.0
    assert result[2, "cumulative_degradation"] > result[1, "cumulative_degradation"]
    assert result[2, "capacity_now_kwh"] < result[0, "capacity_now_kwh"]
    assert result["identity_1_ok"].to_list() == [1, 1, 1]
    assert result["identity_2_ok"].to_list() == [1, 1, 1]


def test_section_accounting_stage_caps_opening_and_closing_at_current_capacity() -> None:
    config = _section_config(capacity_kwh=1.0, initial_soc_fraction=1.0, degradation_per_cycle=0.0)
    context = SimulationContext(config=config, logger=logging.getLogger("test.sections"))
    df = pl.DataFrame(
        {
            "timestamp": [datetime(2025, 1, 1, 0, 0)],
            "wind_kw": [0.0],
            "solar_kw": [120.0],
            "total_generation_kw": [120.0],
            "output_profile_kw": [0.0],
            "aux_consumption_kw": [0.0],
            "site_load_kw": [0.0],
        }
    )

    result = section_accounting_stage(df, context)

    assert result[0, "battery_opening_kw_min"] == pytest.approx(60.0)
    assert result[0, "battery_store_available_kw"] == pytest.approx(0.0)
    assert result[0, "battery_closing_kw_min"] == pytest.approx(60.0)
    assert result[0, "grid_sell_kw"] == pytest.approx(120.0)


def test_section_stage_matches_reference_model_representative_rows() -> None:
    rows = _load_reference_model_rows(start_row=31, end_row=406)
    config = _section_config(capacity_kwh=500.0, initial_soc_fraction=1.0)
    context = SimulationContext(config=config, logger=logging.getLogger("test.sections"))
    base_time = datetime(2025, 1, 1, 0, 0)
    df = pl.DataFrame(
        {
            "timestamp": [base_time + timedelta(minutes=index) for index in range(len(rows))],
            "wind_kw": [row["wind_kw"] for row in rows],
            "solar_kw": [row["solar_kw"] for row in rows],
            "total_generation_kw": [row["total_generation_kw"] for row in rows],
            "output_profile_kw": [400.0] * len(rows),
            "aux_consumption_kw": [20.0] * len(rows),
            "site_load_kw": [420.0] * len(rows),
        }
    )

    result = section_accounting_stage(df, context)

    assert result[0, "deficit_power_kw"] == pytest.approx(333.249, abs=1e-3)
    assert result[0, "battery_closing_kw_min"] == pytest.approx(29650.08855, abs=1e-5)
    assert result[1, "current_cycle"] == pytest.approx(0.011663715, abs=1e-9)
    assert result[100, "battery_store_available_kw"] == pytest.approx(15.849, abs=1e-3)
    assert result[100, "battery_closing_kw_min"] == pytest.approx(6005.285352, abs=1e-6)
    assert result[245, "grid_buy_kw"] == pytest.approx(236.341318, abs=1e-6)
    assert result[245, "battery_closing_kw_min"] == pytest.approx(0.0)
    assert result[375, "grid_sell_kw"] == pytest.approx(80.89278083756636, abs=1e-6)
    assert result[375, "battery_store_available_kw"] == pytest.approx(2.9472191624336347, abs=1e-6)


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
            "preprocessing": {"frequency": "1m", "gap_fill": "linear_interpolate", "max_interpolation_gap_minutes": 15},
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
            "preprocessing": {"frequency": "1m", "gap_fill": "linear_interpolate", "max_interpolation_gap_minutes": 15},
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


def _load_reference_model_rows(start_row: int, end_row: int) -> list[dict[str, float]]:
    with zipfile.ZipFile(REFERENCE_MODEL_PATH) as archive:
        shared_strings = _shared_strings(archive)
        target = _sheet_target(archive, "Corrections BESS Model V1")
        root = ET.fromstring(archive.read(target))
        rows = {
            int(row.attrib["r"]): row
            for row in root.findall(".//a:sheetData/a:row", NS)
            if start_row <= int(row.attrib["r"]) <= end_row
        }

    parsed: list[dict[str, float]] = []
    for row_number in range(start_row, end_row + 1):
        row = rows[row_number]
        cell_map = {cell.attrib["r"]: cell for cell in row.findall("a:c", NS)}
        parsed.append(
            {
                "wind_kw": _numeric_cell(cell_map, f"B{row_number}", shared_strings),
                "solar_kw": _numeric_cell(cell_map, f"E{row_number}", shared_strings),
                "total_generation_kw": _numeric_cell(cell_map, f"F{row_number}", shared_strings),
            }
        )
    return parsed


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall("a:si", NS):
        values.append("".join(node.text or "" for node in item.findall(".//a:t", NS)))
    return values


def _sheet_target(archive: zipfile.ZipFile, sheet_name: str) -> str:
    manifest = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in relationships
        if rel.tag.endswith("Relationship")
    }
    for sheet in manifest.find("a:sheets", NS):
        if sheet.attrib["name"] == sheet_name:
            rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            return f"xl/{rel_map[rel_id]}"
    raise AssertionError(f"Missing reference sheet: {sheet_name}")


def _numeric_cell(
    cells: dict[str, ET.Element],
    ref: str,
    shared_strings: list[str],
) -> float:
    cell = cells[ref]
    value = cell.find("a:v", NS)
    assert value is not None
    if cell.attrib.get("t") == "s":
        return float(shared_strings[int(value.text)])
    return float(value.text)
