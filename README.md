# BESS Model

Python framework for simulating and sizing a Battery Energy Storage System
(BESS) from minute-level solar and wind generation data.

## Features

- Reads mismatched solar and wind CSV files and aligns them to a 1-minute grid
- Runs a section-based accounting simulation using model-driven logic and normalized kWh constraints
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
- `grid_import_kw_min`
- `grid_export_kw_min`
- `final_degraded_capacity_kw_min`
- `final_soc_pct`
- `cumulative_drawn_kw_min`
- `cumulative_stored_kw_min`
- `cumulative_charge_count`
- `identity_1_failures`
- `identity_2_failures`
- `max_identity_error_kw`
- `identity_2_max_error_kw_min`

## Notes

- The original spreadsheet acts as a business-logic layout reference only – internal logic enforces strictly physically valid constraints.
- Battery state, degradation, and capacity strictly enforce flow limits using `kW-min` mapping natively matching the 1-minute sequence basis scale.
- Power calculations, grid limits, sales, and losses evaluate purely in `kW`.
- Linear interpolation is applied only to short gaps; longer gaps are set to zero

## Memory-Optimized Deployment (e.g. Render Free Tier)

For memory-limited environments, set in your config:

```yaml
preprocessing:
  simulation_dtype: "float32"   # Uses ~50% less memory than float64
```

The default is `float32`. Explicit `gc.collect()` runs after simulation to reclaim memory. With 525,600 rows, float32 reduces simulation array memory from ~168 MB to ~84 MB.

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
- `output/<plant_name>_energy_table.csv` (SOURCES, USES, LOSS in kW-min)

## Web Frontend

Run `bess-model-web --config config.example.yaml` to launch a Flask/Jinja2 UI that can:

- edit the YAML config in-browser
- trigger simulation and sizing runs
- preview richer charts for SOC, grid buy/sale, battery state, degradation, and sizing curves
- edit paginated section CSVs
- recalculate downstream outputs after CSV edits


# Notes - 14 Mar 2026
consumption generation losses, solar wind , grid, loss 1 loss 2, profile output, grid sell
identity 2 failures - why and fix them, bring them close to , what are the reasons
highest charge discharge run sizing algo to find minimal grid usage, price wise import export battery sizing, miss profile only 90% time decide minimize grid import export 
in 6 - 10 years replace battery if goes below 70%, replace the battery


1) Eliminate the errors - summary shows identity 2 failures are 30K+, while you eliminate the errors - give me the summary what were the reasons 
2) Give clearly the Energy table in one place, which need not chagne until the config changes (the elements of this table can be increased in future (ie. all the stock elements for 1 year of running the model) - you can give on same page or as a tab, which shows this as a static data
3) Recreate the KPI cards to show all the plant summary columns to make it more informative which should cover the green section from the BESS Model on 1 min data.xlsx 

IDENTITIES					
					
SOURCES	1,50,80,493		USES	1,50,80,493	
Solar Power	1,12,43,312		Charge BESS	9,11,830	
Wind Power	25,77,097		Sell to GRID	51,25,035	
Drawl from BESS	9,12,134		O/p	89,22,060	
Draw from GRID	3,47,950				
			LOSS		
			Discharge L	36,286	
			Charge L	85,282	
					
					
					
					

4) What factors lead to minimization of grid import
5) what is optimal battery 
6) Look at the battery degradation factor after each cycle, its look like too much degradation based on current config, usually in 6 - 10 years replace battery if goes below 70%, replace the battery