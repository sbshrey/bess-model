"""Battery sizing sweep and optimal selection logic."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from bess_model.core.pipeline import simulate_system

if TYPE_CHECKING:
    from bess_model.config import SimulationConfig


def _log_spaced_capacities(min_kwh: float, max_kwh: float, n: int) -> list[float]:
    """Return n capacities log-spaced in [min_kwh, max_kwh]. min/max must be > 0."""
    if min_kwh <= 0 or max_kwh <= 0 or n < 1:
        return [max(min_kwh, max_kwh)] if n >= 1 else []
    if min_kwh >= max_kwh:
        return [min_kwh] * n
    log_min = math.log(min_kwh)
    log_max = math.log(max_kwh)
    return [math.exp(log_min + (log_max - log_min) * i / (n - 1)) for i in range(n)]


def _knee_capacity_index(
    results: list[dict[str, Any]],
    improvement_threshold_pct: float,
    objective: str = "min_grid_import_then_smallest",
) -> int | None:
    """Return index of the first capacity after which marginal improvement is below threshold.

    For min_grid_import: marginal improvement = % reduction in grid import per 10% more capacity.
    When that drops below improvement_threshold_pct, we treat that as the knee.
    Returns the index in results (0-based), or None if no knee found.
    """
    if len(results) < 2 or objective not in (
        "min_grid_import_then_smallest",
        "max_self_consumption_then_smallest",
    ):
        return None
    key = "grid_import_kw_min" if objective == "min_grid_import_then_smallest" else "self_consumption_pct"
    for i in range(len(results) - 1):
        cap_curr = results[i]["capacity_kwh"]
        cap_next = results[i + 1]["capacity_kwh"]
        val_curr = results[i]["metrics"].get(key)
        val_next = results[i + 1]["metrics"].get(key)
        if val_curr is None or val_next is None or cap_curr <= 0:
            continue
        cap_increase_pct = 10.0 * (cap_next - cap_curr) / cap_curr
        if cap_increase_pct <= 0:
            continue
        if key == "grid_import_kw_min":
            # Reduction in grid import (positive = good). Per 10% capacity: (curr - next)/curr * 100 / (cap_increase_pct/10)
            reduction_pct = 100.0 * (float(val_curr) - float(val_next)) / float(val_curr)
            improvement_per_10pct_cap = 10.0 * reduction_pct / cap_increase_pct
        else:
            # Self-consumption increase per 10% capacity
            gain_pct = float(val_next) - float(val_curr)
            improvement_per_10pct_cap = 10.0 * gain_pct / cap_increase_pct
        if improvement_per_10pct_cap < improvement_threshold_pct:
            return i + 1
    return None


def run_auto_sizing(
    config: "SimulationConfig",
    progress_callback: Callable[[str, float, str], None] | None = None,
) -> list[dict[str, Any]]:
    """Run an automated capacity search (target-based or knee-based), then return sweep results.

    Uses config.sizing for auto_sizing, capacity_min_kwh, capacity_max_kwh, auto_max_simulations,
    improvement_threshold_pct, and target_self_consumption_pct. Generates a capacity list and
    runs run_sizing_sweep; selection is done by the caller via select_optimal.
    """
    from bess_model.config import SizingConfig

    sizing = config.sizing or SizingConfig()
    cap_min = sizing.capacity_min_kwh
    cap_max = sizing.capacity_max_kwh
    max_sims = max(3, sizing.auto_max_simulations)
    threshold_pct = sizing.improvement_threshold_pct
    target_sc = sizing.target_self_consumption_pct
    objective = sizing.objective

    if cap_min is None or cap_max is None or cap_min <= 0 or cap_max < cap_min:
        # Fallback: use a small default range from config battery capacity
        base = config.battery.capacity_kwh or 1000.0
        cap_min = base * 0.25
        cap_max = base * 4.0

    capacities_to_run: list[float] = []

    if target_sc is not None and target_sc > 0:
        # Target-based: run coarse log-spaced points to find smallest capacity meeting target.
        bracket_size = min(6, max_sims)
        capacities_to_run = _log_spaced_capacities(cap_min, cap_max, bracket_size)
    else:
        # Knee-based: coarse sweep (5-6 log-spaced)
        n_coarse = min(6, max_sims)
        capacities_to_run = _log_spaced_capacities(cap_min, cap_max, n_coarse)

    # Run sweep for the chosen capacities (dedupe and sort)
    seen: set[float] = set()
    unique_caps: list[float] = []
    for c in sorted(capacities_to_run):
        if c not in seen:
            seen.add(c)
            unique_caps.append(c)
    if not unique_caps:
        unique_caps = [cap_min, cap_max]

    results = run_sizing_sweep(config, unique_caps, progress_callback=progress_callback)
    n_done = len(results)

    if target_sc is not None and target_sc > 0:
        # Find smallest capacity that meets target; add refine points if we have budget
        meeting = [r for r in results if (r["metrics"].get("self_consumption_pct") or 0) >= target_sc]
        if meeting:
            meeting.sort(key=lambda r: r["capacity_kwh"])
            best_cap = meeting[0]["capacity_kwh"]
            # Optionally add 1-2 points around best_cap for a nicer chart
            if n_done < max_sims and best_cap > cap_min:
                extra = [best_cap * 0.8]
                extra = [c for c in extra if c not in seen and c >= cap_min]
                if extra:
                    more = run_sizing_sweep(config, extra, progress_callback=progress_callback)
                    results.extend(more)
                    results.sort(key=lambda r: r["capacity_kwh"])
        return results

    # Knee-based: optionally add 2-3 points around the knee
    knee_idx = _knee_capacity_index(results, threshold_pct, objective)
    if knee_idx is not None and n_done < max_sims:
        knee_cap = results[knee_idx]["capacity_kwh"]
        prev_cap = results[knee_idx - 1]["capacity_kwh"] if knee_idx > 0 else knee_cap * 0.8
        next_cap = results[knee_idx + 1]["capacity_kwh"] if knee_idx + 1 < len(results) else knee_cap * 1.2
        refine = [
            (prev_cap + knee_cap) / 2.0,
            (knee_cap + next_cap) / 2.0,
        ]
        refine = [c for c in refine if cap_min <= c <= cap_max and c not in seen]
        refine = refine[: max(0, max_sims - n_done)]
        if refine:
            more = run_sizing_sweep(config, refine, progress_callback=progress_callback)
            results.extend(more)
            results.sort(key=lambda r: r["capacity_kwh"])

    return results


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
