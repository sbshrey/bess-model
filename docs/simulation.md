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
| `total_consumption_kw_min` | Total load (output profile + aux) |
| `self_consumption_pct` | 100 × (1 − grid_import / total_consumption); profile coverage from renewables+battery |
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

## Industry-Standard Battery Sizing Scenarios

When deciding plant battery size, these top 5 scenario questions guide sizing:

| # | Scenario Question | What It Answers | Key Metric | How the Model Addresses It |
|---|-------------------|-----------------|------------|----------------------------|
| 1 | **What battery size minimizes grid import?** | Self-consumption / renewable integration | `grid_import_kw_min` | Run `--mode size`; objective `min_grid_import_then_smallest` picks the capacity with lowest grid import, then smallest if tied. |
| 2 | **What minimum battery size achieves ≥90% profile coverage (self-consumption)?** | Reliability / renewable share target | `self_consumption_pct` | Set `sizing.constraints.min_self_consumption_pct: 90`; objective `min_battery_then_meet_target` finds the smallest capacity that meets the target. |
| 3 | **What battery size balances throughput vs degradation over 6–10 years?** | Cycle life / replacement planning | `cumulative_charge_count` | Add `sizing.constraints.max_cycles_per_year` to cap cycling; use calibrated `degradation_per_cycle` for realistic SOH projection. |
| 4 | **What is the cost-optimal battery size?** | Capex vs avoided grid cost | Grid $ saved vs battery $ | Requires price inputs (import $/kWh, export $/kWh, battery $/kWh). Future: optional economics config block. |
| 5 | **What battery power (kW) and duration (h) are needed for peak deficit coverage?** | Peak shaving / power vs energy | Deficit duration, C-rate | Sweep `nominal_power_kw` and `duration_hours` in config; analyze worst deficit windows from section outputs. |

Scenarios 1–3 are supported by the sizing sweep. Run `python main.py --config config.example.yaml --mode size` or use **Run Sizing** in the web UI. Results are written to `{plant}_sizing_results.csv`.

## Output Artifacts

| File | Content |
|------|---------|
| `{plant}_minute_flows.parquet` | Full minute-level DataFrame |
| `{plant}_summary.csv` | One-row summary metrics |
| `{plant}_energy_table.csv` | Annual energy flows (SOURCES, USES, LOSS) in kW-min |
| `{plant}_sections/` | Section CSVs (when `--dump-sections`) |
| `{plant}_sizing_results.csv` | Capacity sweep: grid import, self-consumption %, recommended (when `--mode size`) |

## Units and Conventions

- **Power**: kW (instantaneous)
- **Energy**: kW-min (1-minute resolution, divide by 60 for kWh)
- **C-rate**: power / capacity (1C = full capacity in 1 hour)
- **SOC**: fraction (0–1) or percent (0–100)
- **Loss tables**: C-rate → loss fraction; loss = rate × power
