# Simulation Logic

## Overview

The core simulation lives in `bess_model/flows/section_outputs.py`. The `section_accounting_stage` function runs a minute-by-minute BESS model and appends many derived columns to the aligned input DataFrame.

## Simulation Algorithm

`_simulate_section_accounting()` iterates over each minute and:

1. **Cumulative generation** — `cum_wind`, `cum_solar`, `cum_total` (kW-min)
2. **Battery degradation** — `capacity_now_kw_min` = nominal × (1 − cumulative_degradation)
3. **Excess / deficit** — `excess_power_kw` = max(generation − consumption, 0), `deficit_power_kw` = max(consumption − generation, 0)
4. **Battery discharge** — Draw from battery to meet deficit; C-rate, loss lookup, grid buy
5. **Battery charge** — Store excess; C-rate, loss lookup, grid sell
6. **State of charge** — `battery_opening_kw_min`, `battery_closing_kw_min`, `soc_fraction`, `soc_pct`
7. **Cycle counts** — `cum_charge_count` = discharge + charge equivalent full cycles
8. **Identity checks** — Energy balance (identity 1) and BESS state (identity 2)

## Key Helpers

- **`_rounded_c_rate(power_kw, capacity_kwh)`** — C-rate = power / capacity
- **`_lookup_loss_rate(c_rate, table)`** — Linear interpolation on config loss table

## Output Sections

With `--dump-sections`, the pipeline writes these CSVs:

| File | Title |
|------|-------|
| `00_aligned_input.csv` | Aligned solar + wind input |
| `01_wind_solar_generation.csv` | Wind & solar generation |
| `02_cumulative_generation.csv` | Cumulative generation (kW-min) |
| `03_output_profile.csv` | Output profile and total consumption |
| `04_battery_capacity_cycles.csv` | Capacity and degradation |
| `05_excess_deficit_power.csv` | Excess/deficit power |
| `06_battery_opening_closing.csv` | Battery state (kW-min) |
| `07_power_from_battery.csv` | Draw, C-rate, losses |
| `08_consume_from_grid.csv` | Grid buy |
| `09_power_to_battery.csv` | Store, C-rate, losses |
| `10_sell_to_grid.csv` | Grid sell |
| `11_soc_calculations.csv` | SOC (kWh, fraction, %) |
| `12_battery_charge_cycles.csv` | Cycle counts |
| `13_identity_equation_1.csv` | Energy balance identity |
| `14_identity_equation_2.csv` | BESS state identity |

## Summary Metrics

`compute_summary_metrics()` produces:

| Metric | Description |
|--------|-------------|
| `plant_name` | Config plant name |
| `rows` | Number of minute rows |
| `grid_import_kw_min` | Total grid buy |
| `grid_export_kw_min` | Total grid sell |
| `final_degraded_capacity_kw_min` | End-of-run capacity |
| `final_soc_pct` | Final SOC % |
| `cumulative_drawn_kw_min` | Total energy drawn from battery |
| `cumulative_stored_kw_min` | Total energy stored |
| `cumulative_charge_count` | Equivalent full cycles |
| `identity_1_failures` | Energy balance violations |
| `identity_2_failures` | BESS state violations |
| `max_identity_error_kw` | Max identity 1 error |
| `identity_2_max_error_kw_min` | Max identity 2 error (BESS state) |

## Factors Leading to Grid Import Minimization

Several configuration and data factors influence how much energy is imported from the grid:

- **Battery capacity** — Larger capacity stores more surplus generation and reduces reliance on the grid during deficit minutes.
- **Battery power (C-rate)** — Higher nominal power allows faster charge and discharge, improving peak shaving and responsiveness to excess/deficit.
- **Generation–load match** — Solar and wind profiles aligned with consumption reduce deficit minutes and the need for grid import.
- **Initial SOC** — Higher starting SOC provides more discharge headroom in early hours, delaying the first grid import.
- **Degradation and loss tables** — Lower losses and degradation preserve usable energy; higher losses reduce effective throughput.
- **Output profile** — Lower base load (output_profile_kw + aux_consumption_kw) reduces deficit magnitude.

## Optimal Battery Utilization

Optimal battery utilization balances cycle throughput with cycle life:

- **Definition** — Balance between energy throughput (charge/discharge cycles) and capacity retention (degradation over time).
- **Trade-off** — More cycling reduces grid import but accelerates capacity loss; less cycling preserves capacity but increases grid dependence.
- **Indicators** — `cumulative_charge_count`, `final_degraded_capacity_kwh`, and SOH % (capacity health) in the summary metrics.
- **Practical guidance** — Sizing for 90% profile coverage often yields a better cost/benefit than 100% coverage. Consider battery replacement when SOH falls below ~70% (per project notes).

## Output Artifacts

| File | Content |
|------|---------|
| `{plant}_minute_flows.parquet` | Full minute-level DataFrame |
| `{plant}_summary.csv` | One-row summary metrics |
| `{plant}_energy_table.csv` | Annual energy flows (SOURCES, USES, LOSS) in kW-min |
| `{plant}_sections/` | Section CSVs (when `--dump-sections`) |

## Units and Conventions

- **Power**: kW (instantaneous)
- **Energy**: kW-min (1-minute resolution, divide by 60 for kWh)
- **C-rate**: power / capacity (1C = full capacity in 1 hour)
- **SOC**: fraction (0–1) or percent (0–100)
- **Loss tables**: C-rate → loss fraction; loss = rate × power
