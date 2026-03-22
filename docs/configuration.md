# Configuration Reference

## Overview

Configuration is loaded from a YAML file and validated into typed dataclasses in `bess_model/config.py`. Load with:

```python
config = SimulationConfig.from_yaml("config.example.yaml")
```

## Configuration File Structure

```yaml
plant_name: solar_wind_plant
output_dir: output
data:
  data_dir: data
  solar_enabled: true
  wind_enabled: true
preprocessing:
  frequency: 1m
  gap_fill: zero
  max_interpolation_gap_minutes: 15
grid:
  export_limit_kw: 400.0
  import_limit_kw: ''        # null or '' for no limit
load:
  profile_mode: flat
  profile_template_id: null
  contracted_capacity_mw: null
  output_profile_kw: 400.0
  aux_consumption_kw: 20.0
battery:
  nominal_power_kw: 500.0
  duration_hours: 2.0
  initial_soc_fraction: 0.5
  degradation_per_cycle: 0.0002739726027
  charge_efficiency: 0.96
  discharge_efficiency: 0.94
  charge_loss_table:
    0.2: 0.04
    0.3: 0.045
    0.5: 0.07
    1.0: 0.11
    1.2: 0.14
  discharge_loss_table:
    0.2: 0.023
    0.3: 0.032
    0.5: 0.042
    1.0: 0.062
    1.2: 0.067
  min_soc_fraction: 0.0
  max_soc_fraction: 1.0
```

## Config Sections

### Top Level

| Field | Type | Description |
|-------|------|-------------|
| `plant_name` | str | Identifier for outputs (e.g. `solar_wind_plant_minute_flows.parquet`) |
| `output_dir` | str | Directory for Parquet, summary CSV, and section CSVs |

### `data` (DataConfig)

Input file paths are fixed under `data_dir` (not editable in the UI). Use toggles to choose which sources to include.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `data_dir` | str | `"data"` | Folder for input CSVs (relative path) |
| `solar_enabled` | bool | `true` | Include solar generation from `data_dir/Solar_2025-01-01_data_.csv` |
| `wind_enabled` | bool | `true` | Include wind generation from `data_dir/Wind_2025_01-01_data_.csv` |

At least one of `solar_enabled` or `wind_enabled` must be true. Any combination is allowed (solar only, wind only, or both).

**Expected CSV columns:**
- Solar: `timestamp` (dd/mm/yyyy hh:mm), `Power in KW`
- Wind: `time stamp` (yyyy-mm-dd hh:mm), `Power in KW`

### `preprocessing` (PreprocessingConfig)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `frequency` | str | `"1m"` | Output resolution (1m = 1-minute) |
| `gap_fill` | str | `"linear_interpolate"` | `linear_interpolate` or `zero` |
| `max_interpolation_gap_minutes` | int | 15 | Max gap (minutes) to interpolate; larger gaps use zero fill |
| `align_to_full_year` | bool | `true` | If true, aligned output spans full calendar year (525,600 or 527,040 rows); timestamps outside source data get zero fill |
| `simulation_dtype` | str | `"float32"` | NumPy dtype for simulation arrays: `float32` (lower memory, ~50% less) or `float64` (higher precision). Use `float32` for Render/memory-limited environments |

Legacy configs that use explicit `data.solar_path` / `data.wind_path` and omit `align_to_full_year` default to source-range alignment for backward compatibility. Set `align_to_full_year` explicitly to override that behavior.

### `grid` (GridConfig)

| Field | Type | Description |
|-------|------|-------------|
| `export_limit_kw` | float | Grid export limit (kW); must be > 0 |
| `import_limit_kw` | float \| None | Grid import limit; `null` or empty = no limit |

### `load` (LoadConfig)

| Field | Type | Description |
|-------|------|-------------|
| `profile_mode` | str | `flat` for a constant output load, `template` for a tender-driven output profile |
| `profile_template_id` | str \| None | Tender profile id: `seci_fdre_v_amendment_03` or `seci_fdre_ii_revised_annexure_b` |
| `contracted_capacity_mw` | float \| None | Contracted capacity used to scale the tender profile |
| `output_profile_kw` | float \| None | Constant output load (kW), required in `flat` mode |
| `aux_consumption_kw` | float | Auxiliary consumption (kW) |

In `flat` mode, total consumption = `output_profile_kw + aux_consumption_kw`.

In `template` mode, `output_profile_kw` is expanded from the selected tender profile by month and block, scaled by `contracted_capacity_mw / base_capacity_mw`, then combined with `aux_consumption_kw`.

### `battery` (BatteryConfig)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `nominal_power_kw` | float | — | Rated power (kW) |
| `duration_hours` | float | — | Duration at rated power; capacity = nominal_power_kw × duration_hours |
| `initial_soc_fraction` | float | 1.0 | Initial SOC (0–1) |
| `degradation_per_cycle` | float | ~0.00027 | Capacity loss per equivalent full cycle |
| `charge_efficiency` | float | derived | 1 − charge_loss_table[1.0] if not set |
| `discharge_efficiency` | float | derived | 1 − discharge_loss_table[1.0] if not set |
| `charge_loss_table` | dict | — | C-rate → loss fraction (e.g. 1.0: 0.11) |
| `discharge_loss_table` | dict | — | C-rate → loss fraction |
| `min_soc_fraction` | float | 0.0 | Lower SOC bound |
| `max_soc_fraction` | float | 1.0 | Upper SOC bound |
| `max_charge_kw` | float | capacity | Override charge limit |
| `max_discharge_kw` | float | capacity | Override discharge limit |

**Loss tables:** Keys are C-rates (e.g. 0.5, 1.0); values are loss fractions. Linear interpolation between points.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `BESS_CONFIG_PATH` | Config file path for the web app |
| `PORT` | Port for Gunicorn (e.g. Render) |

## Validation Rules

`SimulationConfig.validate()` enforces:

- `grid.export_limit_kw` > 0  
- `battery.capacity_kwh` ≥ 0  
- `battery.duration_hours` > 0  
- `battery.charge_efficiency` and `discharge_efficiency` in (0, 1]  
- `battery.initial_soc_fraction` in [0, 1]  
- 0 ≤ `min_soc_fraction` ≤ `max_soc_fraction` ≤ 1  
- `max_interpolation_gap_minutes` ≥ 0  
