"""Battery sizing sweep and optimal selection logic."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from bess_model.core.pipeline import simulate_system

if TYPE_CHECKING:
    from bess_model.config import SimulationConfig


def run_sizing_sweep(
    config: "SimulationConfig",
    capacities_kwh: list[float],
    progress_callback: Callable[[str, float, str], None] | None = None,
) -> list[dict[str, Any]]:
    """Run simulation for each battery capacity and collect metrics.

    Args:
        config: Base simulation config.
        capacities_kwh: List of capacities (kWh) to sweep.
        progress_callback: Optional callback (stage, pct, detail) for progress updates.

    Returns:
        List of dicts with capacity_kwh, metrics (summary_metrics from each run),
        and recommended (bool) if this was selected as optimal.
    """
    results: list[dict[str, Any]] = []
    n = len(capacities_kwh)

    for i, cap in enumerate(sorted(capacities_kwh)):
        if progress_callback:
            pct = 5.0 + 85.0 * (i + 1) / n
            progress_callback("Sizing sweep", pct, f"Capacity {cap} kWh ({i + 1}/{n})")

        run_config = config.with_battery_capacity(cap)
        result = simulate_system(run_config)
        results.append(
            {
                "capacity_kwh": cap,
                "metrics": result.summary_metrics,
                "recommended": False,
            }
        )

    return results


def select_optimal(
    results: list[dict[str, Any]],
    objective: str = "min_grid_import_then_smallest",
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Select the optimal result from a sizing sweep.

    Args:
        results: Output from run_sizing_sweep (list of {capacity_kwh, metrics}).
        objective: One of min_grid_import_then_smallest, max_self_consumption_then_smallest,
            min_battery_then_meet_target.
        constraints: Optional dict with min_self_consumption_pct (float), max_cycles_per_year (float|None).

    Returns:
        The selected result dict (with recommended=True), or None if no result meets constraints.
    """
    constraints = constraints or {}
    min_self_pct = constraints.get("min_self_consumption_pct")
    max_cycles = constraints.get("max_cycles_per_year")
    rows_per_year = 525_600  # 1-min resolution for 1 year

    # Filter by constraints
    candidates = []
    for r in results:
        m = r["metrics"]
        if min_self_pct is not None:
            sc = m.get("self_consumption_pct")
            if sc is None or sc < min_self_pct:
                continue
        if max_cycles is not None and max_cycles > 0:
            rows = m.get("rows", 0)
            charge_count = m.get("cumulative_charge_count", 0.0)
            cycles_per_year = (charge_count * rows_per_year / rows) if rows > 0 else 0.0
            if cycles_per_year > max_cycles:
                continue
        candidates.append(r)

    if not candidates:
        return None

    # Rank by objective
    if objective == "min_grid_import_then_smallest":
        candidates.sort(
            key=lambda r: (r["metrics"].get("grid_import_kw_min", float("inf")), r["capacity_kwh"])
        )
    elif objective == "max_self_consumption_then_smallest":
        candidates.sort(
            key=lambda r: (-r["metrics"].get("self_consumption_pct", -1), r["capacity_kwh"])
        )
    elif objective == "min_battery_then_meet_target":
        # Already filtered by min_self_consumption_pct; pick smallest
        candidates.sort(key=lambda r: r["capacity_kwh"])
    else:
        # Default to min_grid_import_then_smallest
        candidates.sort(
            key=lambda r: (r["metrics"].get("grid_import_kw_min", float("inf")), r["capacity_kwh"])
        )

    best = candidates[0]
    best["recommended"] = True
    return best
