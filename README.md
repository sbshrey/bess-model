# BESS Model

Python framework for simulating and sizing a Battery Energy Storage System
(BESS) from minute-level solar and wind generation data.

## Features

- Reads mismatched solar and wind CSV files and aligns them to a 1-minute grid
- Runs a section-based accounting simulation aligned to the reference sizing model
- Simulates battery charge, discharge, SOC, degradation, and loss lookups
- Sweeps multiple battery capacities and recommends an optimal size
- Writes minute-level outputs to Parquet and summary metrics to the console
- Can dump aligned input and every intermediate stage as CSV

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
python main.py --config config.example.yaml --mode simulate
python main.py --config config.example.yaml --mode simulate --dump-sections
python main.py --config config.example.yaml --mode size
bess-model-web --config config.example.yaml --host 127.0.0.1 --port 5000
```

## Summary Columns

- `rows`
- `grid_import_energy_kwh`
- `grid_export_energy_kwh`
- `final_degraded_capacity_kwh`
- `final_soc_pct`
- `cumulative_drawn_energy_kwh`
- `cumulative_stored_energy_kwh`
- `cumulative_charge_count`
- `identity_1_failures`
- `identity_2_failures`

## Notes

- Source power values are normalized to `kW`
- Battery capacity and SOC are stored in `kWh`
- Internal energy calculations use `power_kw / 60`
- Linear interpolation is applied only to short gaps; longer gaps are set to zero

## Section CSVs

Run `python main.py --config config.example.yaml --mode simulate --dump-sections`
to write:

- `output/<plant_name>_sections/00_aligned_input.csv`
- `output/<plant_name>_sections/01_wind_solar_generation.csv`
- `output/<plant_name>_sections/02_cumulative_generation.csv`
- `output/<plant_name>_sections/03_output_profile.csv`
- `output/<plant_name>_sections/04_battery_capacity_cycles.csv`
- `output/<plant_name>_sections/05_excess_deficit_power.csv`
- `output/<plant_name>_sections/06_battery_opening_closing.csv`
- `output/<plant_name>_sections/07_power_from_battery.csv`
- `output/<plant_name>_sections/08_consume_from_grid.csv`
- `output/<plant_name>_sections/09_power_to_battery.csv`
- `output/<plant_name>_sections/10_sell_to_grid.csv`
- `output/<plant_name>_sections/11_soc_calculations.csv`
- `output/<plant_name>_sections/12_battery_charge_cycles.csv`
- `output/<plant_name>_sections/13_identity_equation_1.csv`
- `output/<plant_name>_sections/14_identity_equation_2.csv`

## Web Frontend

Run `bess-model-web --config config.example.yaml` to launch a Flask/Jinja2 UI that can:

- edit the YAML config in-browser
- trigger simulation and sizing runs
- preview richer charts for SOC, grid buy/sale, battery state, degradation, and sizing curves
- edit paginated section CSVs
- recalculate downstream outputs after CSV edits
