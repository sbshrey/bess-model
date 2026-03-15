---
name: Auto Simulation and Battery Sizing
overview: Enable users to run automated simulation sweeps that optimize for grid import minimization, battery utilization, and profile coverage; implement capacity sizing with configurable objectives; and document top industry-standard scenario questions for battery sizing decisions.
todos: []
isProject: false
---

# Auto Simulation and Battery Sizing Plan

## 1. Current State

- **Simulation**: Single-run only via CLI or web. No sweep or optimization.
- **Sizing**: README mentions `--mode size` but [bess_model/main.py](bess_model/main.py) has no size mode. Tests reference `sizing.capacities_kwh` and `objective: min_grid_import_then_smallest` but this is not implemented.
- **Metrics**: `grid_import_kw_min`, `grid_export_kw_min`, `cumulative_charge_count`, `final_degraded_capacity_kw_min`, etc. No explicit "profile coverage" or "self-consumption %" metric.
- **Profile coverage**: Model always meets consumption (battery + grid). "90% profile" = ≥90% of load served by renewables+battery (≤10% from grid). Requires new metric: `self_consumption_pct = 100 * (1 - grid_import / total_consumption)`.

## 2. New Metrics for Optimization

Add to [bess_model/core/pipeline.py](bess_model/core/pipeline.py) `compute_summary_metrics()`:


| Metric                          | Formula                                                   | Purpose                            |
| ------------------------------- | --------------------------------------------------------- | ---------------------------------- |
| `self_consumption_pct`          | 100 × (1 - grid_import_kw_min / total_consumption_kw_min) | Profile coverage / renewable share |
| `total_consumption_kw_min`      | `sum(total_consumption_kw)`                               | Denominator for coverage           |
| `years_to_70pct_soh` (optional) | 0.30 / (degradation_per_cycle × cycles_per_year)          | Degradation-aware sizing           |


## 3. Auto Simulation (Sizing) Implementation

### 3.1 Config Schema

Extend [config.example.yaml](config.example.yaml) and [bess_model/config.py](bess_model/config.py):

```yaml
sizing:
  enabled: true
  capacities_kwh: [500, 750, 1000, 1250, 1500]   # or min/max/step
  objective: min_grid_import_then_smallest        # primary
  constraints:
    min_self_consumption_pct: 90.0                # "not miss 90% profile"
    max_cycles_per_year: null                     # optional degradation cap
```

**Objectives** (in priority order when tied):

- `min_grid_import_then_smallest` — minimize grid import, then pick smallest battery
- `max_self_consumption_then_smallest` — maximize self-consumption %, then smallest
- `min_battery_then_meet_target` — smallest battery that meets `min_self_consumption_pct`

### 3.2 Sizing Module

Create `bess_model/sizing.py`:

- `run_sizing_sweep(config, capacities_kwh, progress_cb) -> list[dict]`
  - For each capacity: clone config with `config.with_battery_capacity(cap)`, run `simulate_system()`, collect metrics
  - Return list of `{capacity_kwh, metrics, ...}` for each run
- `select_optimal(results, objective, constraints) -> dict`
  - Filter by constraints (e.g. `self_consumption_pct >= 90`)
  - Rank by objective, return best

### 3.3 CLI Integration

Update [bess_model/main.py](bess_model/main.py):

- Add `--mode size` (or infer from presence of `sizing` in config)
- When sizing enabled: run sweep, print capacity vs grid_import/self_consumption table, output recommended capacity and `{plant}_sizing_results.csv`

### 3.4 Web UI Integration

Update [bess_model/web/app.py](bess_model/web/app.py) and [bess_model/web/services.py](bess_model/web/services.py):

- Add "Run Sizing" button/action (alongside "Run Simulation")
- On sizing run: execute sweep with progress, persist `{plant}_sizing_results.csv`
- Add Sizing Results block: table of capacity vs grid import, self-consumption %, recommended capacity
- Optional: chart of capacity vs grid_import / self_consumption curve (reuse existing chart infra)

## 4. Industry-Standard Scenario Questions (Top 5)

Document in [docs/simulation.md](docs/simulation.md) (new section) and optionally as scenario presets in config:


| #   | Scenario Question                                                                  | What It Answers                          | Key Metric                                      | How Model Addresses It                                                                                  |
| --- | ---------------------------------------------------------------------------------- | ---------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| 1   | **What battery size minimizes grid import?**                                       | Self-consumption / renewable integration | `grid_import_kw_min`                            | Sweep capacities; pick minimum grid import (then smallest if tied)                                      |
| 2   | **What minimum battery size achieves ≥90% profile coverage (self-consumption)?**   | Reliability / renewable share target     | `self_consumption_pct`                          | Constraint: `min_self_consumption_pct: 90`; find smallest capacity that meets it                        |
| 3   | **What battery size balances throughput vs degradation over 6–10 years?**          | Cycle life / replacement planning        | `cumulative_charge_count`, `years_to_70pct_soh` | Filter/rank by cycle count or add `max_cycles_per_year`; use calibrated `degradation_per_cycle`         |
| 4   | **What is the cost-optimal battery size?**                                         | Capex vs avoided grid cost               | Grid $ saved vs battery $                       | Requires price inputs (import $/kWh, export $/kWh, battery $/kWh); extend config for optional economics |
| 5   | **What battery power (kW) and duration (h) are needed for peak deficit coverage?** | Peak shaving / power vs energy trade-off | Deficit duration, C-rate                        | Sweep `nominal_power_kw` and `duration_hours`; analyze worst deficit windows                            |


**Notes**:

- Scenarios 1–3 are directly supported by the proposed sizing + metrics.
- Scenario 4 needs a future "economics" config block (prices, discount rate).
- Scenario 5 uses existing `nominal_power_kw` × `duration_hours` = capacity; can add power sweep if needed.

## 5. "Optimal Battery Usage" Clarification

"Optimal battery usage" can mean:

- **Throughput**: Maximize energy cycled (stored + drawn) — often conflicts with minimizing grid import (more cycling = more degradation)
- **Efficiency**: Minimize round-trip losses — already captured in loss tables
- **Life**: Minimize cycles to preserve capacity — constraint `max_cycles_per_year` or `years_to_70pct_soh`

Recommendation: treat it as a **constraint** (e.g. max cycles or min years to 70% SOH) rather than a primary objective. Primary objective remains min grid import or max self-consumption.

## 6. Implementation Order

1. Add `self_consumption_pct` and `total_consumption_kw_min` to summary metrics
2. Implement `bess_model/sizing.py` (sweep + selection logic)
3. Add sizing config schema and CLI `--mode size`
4. Add "Run Sizing" and Sizing Results to web UI
5. Document the 5 scenario questions and how to use them in `docs/simulation.md`
6. (Optional) Add `years_to_70pct_soh` to summary; add economics block for scenario 4 later

