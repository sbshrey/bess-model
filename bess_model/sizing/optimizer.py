"""Battery sizing sweeps and selection logic."""

from __future__ import annotations

import polars as pl

from bess_model.config import SimulationConfig
from bess_model.core.pipeline import simulate_system
from bess_model.results import SizingResult


def run_sizing(config: SimulationConfig) -> SizingResult:
    """Run the configured capacity sweep and choose an optimal size."""
    rows: list[dict[str, float | int | str]] = []
    power_candidates = config.sizing.power_kw_candidates or [
        capacity / config.battery.duration_hours for capacity in config.sizing.capacities_kwh
    ]
    for nominal_power_kw in power_candidates:
        run_config = config.with_battery_nominal_power(nominal_power_kw)
        simulation = simulate_system(run_config)
        row = dict(simulation.summary_metrics)
        row["battery_capacity_kwh"] = run_config.battery.capacity_kwh
        row["battery_nominal_power_kw"] = run_config.battery.nominal_power_kw
        rows.append(row)

    results = pl.DataFrame(rows)
    sort_columns: list[str] = []
    if "grid_import_energy_kwh" in results.columns:
        sort_columns.append("grid_import_energy_kwh")
    if "grid_export_energy_kwh" in results.columns:
        sort_columns.append("grid_export_energy_kwh")
    sort_columns.extend(["battery_capacity_kwh", "battery_nominal_power_kw"])
    results = results.sort(by=sort_columns, descending=[False] * len(sort_columns))
    optimal_capacity = float(results[0, "battery_capacity_kwh"])
    return SizingResult(results=results, optimal_capacity_kwh=optimal_capacity)
