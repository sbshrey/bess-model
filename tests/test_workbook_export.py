from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import polars as pl
import pytest

from bess_model.workbook_export import export_stakeholder_workbook, main


def test_export_stakeholder_workbook_creates_workbook_and_zip(tmp_path: Path) -> None:
    package_dir = _create_package(tmp_path / "energy_profiles_20260321_122756")

    exit_code = main(["--input-dir", str(package_dir)])

    workbook_path = package_dir / "energy_profiles_20260321_122756.xlsx"
    zip_path = tmp_path / "energy_profiles_20260321_122756.zip"

    assert exit_code == 0
    assert workbook_path.exists()
    assert zip_path.exists()
    assert _sheet_names(workbook_path) == [
        "Energy Table",
        "Scenario Summary",
        "Scenario Index",
    ]

    with zipfile.ZipFile(zip_path) as archive:
        assert f"{package_dir.name}/{workbook_path.name}" in archive.namelist()


def test_export_stakeholder_workbook_requires_all_combined_csvs(tmp_path: Path) -> None:
    package_dir = tmp_path / "energy_profiles_20260321_122756"
    package_dir.mkdir()
    pl.DataFrame({"case_id": ["1a"]}).write_csv(package_dir / "energy_table_all_cases.csv")

    with pytest.raises(FileNotFoundError, match="scenario_summary_all_cases.csv"):
        export_stakeholder_workbook(package_dir)


def _create_package(package_dir: Path) -> Path:
    package_dir.mkdir(parents=True)
    pl.DataFrame(
        {
            "case_id": ["1a", "1b"],
            "output_profile_kw": [400.0, 250.0],
            "draw_from_grid_kwh": [1000.25, 500.5],
        }
    ).write_csv(package_dir / "energy_table_all_cases.csv")
    pl.DataFrame(
        {
            "case_id": ["1a", "1b"],
            "grid_import_kwh": [1000.25, 500.5],
            "self_consumption_pct": [68.6, 79.0],
        }
    ).write_csv(package_dir / "scenario_summary_all_cases.csv")
    pl.DataFrame(
        {
            "case_id": ["1a", "1b"],
            "folder_name": ["01_output400_battery250x2", "04_output250_battery250x2"],
        }
    ).write_csv(package_dir / "scenario_index.csv")
    return package_dir


def _sheet_names(workbook_path: Path) -> list[str]:
    with zipfile.ZipFile(workbook_path) as workbook_zip:
        workbook_xml = workbook_zip.read("xl/workbook.xml")

    root = ET.fromstring(workbook_xml)
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return [sheet.attrib["name"] for sheet in root.findall("main:sheets/main:sheet", ns)]
