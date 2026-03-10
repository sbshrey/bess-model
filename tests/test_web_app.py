from __future__ import annotations

import csv

from pathlib import Path

from bess_model.web.app import create_app
from bess_model.web.services import build_chart_cards, load_csv_page, run_sizing_from_frontend


def test_dashboard_renders_and_simulation_route_runs(tmp_path) -> None:
    solar_path = tmp_path / "solar.csv"
    wind_path = tmp_path / "wind.csv"
    config_path = tmp_path / "config.yaml"
    output_dir = tmp_path / "output"

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
    config_path.write_text(
        "\n".join(
            [
                "plant_name: web_case",
                f"output_dir: {output_dir}",
                "data:",
                f"  solar_path: {solar_path}",
                f"  wind_path: {wind_path}",
                "preprocessing:",
                "  frequency: 1m",
                "  gap_fill: linear_interpolate",
                "  max_interpolation_gap_minutes: 15",
                "grid:",
                "  export_limit_kw: 100.0",
                "  import_limit_kw:",
                "load:",
                "  output_profile_kw: 400.0",
                "  aux_consumption_kw: 20.0",
                "battery:",
                "  capacity_kwh: 1000.0",
                "  max_charge_kw: 200.0",
                "  max_discharge_kw: 200.0",
                "  charge_efficiency: 1.0",
                "  discharge_efficiency: 1.0",
                "  initial_soc_kwh: 0.0",
                "sizing:",
                "  capacities_kwh: [1000.0]",
                "  objective: min_grid_import_then_smallest",
            ]
        ),
        encoding="utf-8",
    )

    app = create_app(config_path)
    client = app.test_client()

    response = client.get("/")
    assert response.status_code == 200
    assert b"BESS Control Room" in response.data
    assert b"data-sidebar-toggle" in response.data
    assert b"data-dashboard-sidebar" in response.data

    simulate = client.post(
        "/run/simulate",
        data={"config_text": config_path.read_text(encoding="utf-8")},
        follow_redirects=True,
    )
    assert simulate.status_code == 200
    assert b"Simulation completed" in simulate.data
    assert (output_dir / "web_case_summary.csv").exists()
    section_path = output_dir / "web_case_sections" / "11_soc_calculations.csv"
    assert section_path.exists()
    battery_state_path = output_dir / "web_case_sections" / "06_battery_opening_closing.csv"
    assert battery_state_path.exists()

    flow_charts = build_chart_cards(section_path)
    assert any(chart.title == "SOC Profile" for chart in flow_charts)
    soc_chart = next(chart for chart in flow_charts if chart.title == "SOC Profile")
    assert "Time" in soc_chart.svg
    assert "SOC (%)" in soc_chart.svg
    assert "00:00" in soc_chart.svg

    battery_state_charts = build_chart_cards(battery_state_path)
    assert any(chart.title == "Battery State Window" for chart in battery_state_charts)
    battery_state_chart = next(chart for chart in battery_state_charts if chart.title == "Battery State Window")
    assert "Battery State (kW-min)" in battery_state_chart.svg

    filtered_dashboard = client.get(
        f"/?file=web_case_sections/11_soc_calculations.csv&start_date=2025-01-01&end_date=2025-01-01"
    )
    assert filtered_dashboard.status_code == 200
    assert b"name=\"start_date\"" in filtered_dashboard.data
    assert b"Showing 2 of 2 rows from 2025-01-01 to 2025-01-01." in filtered_dashboard.data

    filtered_editor = client.get(
        "/edit/web_case_sections/11_soc_calculations.csv?start_date=2025-01-01&end_date=2025-01-01&page_size=1"
    )
    assert filtered_editor.status_code == 200
    assert b"Recalculate downstream outputs after save" in filtered_editor.data
    assert b"name=\"start_date\" value=\"2025-01-01\"" in filtered_editor.data

    aligned_editor = client.get(
        "/edit/web_case_sections/00_aligned_input.csv?start_date=2025-01-01&end_date=2025-01-01&page_size=1"
    )
    assert aligned_editor.status_code == 200

    _, sizing_path = run_sizing_from_frontend(Path(config_path))
    sizing_charts = build_chart_cards(sizing_path)
    assert any(chart.title == "Sizing Curve" for chart in sizing_charts)
    sizing_svg = next(chart.svg for chart in sizing_charts if chart.title == "Sizing Curve")
    assert "Battery Capacity (kWh)" in sizing_svg
    assert "Grid Import Energy (kWh)" in sizing_svg
    assert "1,000" in sizing_svg

    filtered_page = load_csv_page(section_path, page=1, page_size=1, start_date="2025-01-01", end_date="2025-01-01")
    assert filtered_page.total_rows == 2
    assert filtered_page.row_numbers == [0]


def _write_csv(path, header, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
