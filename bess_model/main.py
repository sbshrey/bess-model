"""CLI entrypoint for running simulation or sizing flows."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

import polars as pl

from bess_model.config import SimulationConfig, SizingConfig
from bess_model.core.pipeline import (
    load_aligned_inputs,
    simulate_system,
    write_simulation_outputs,
    write_stage_outputs,
)
from bess_model.sizing import run_auto_sizing, run_sizing_sweep, select_optimal


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI arguments and execute the requested mode."""
    parser = argparse.ArgumentParser(description="BESS simulation and sizing runner")
    parser.add_argument("--config", required=True, help="Path to a YAML configuration file")
    parser.add_argument(
        "--mode",
        default="simulate",
        choices=("simulate", "size"),
        help="Run mode: simulate (single run) or size (capacity sweep)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Logging verbosity",
    )
    parser.add_argument(
        "--dump-sections",
        "--dump-stages",
        action="store_true",
        help="Write aligned input and per-section CSV snapshots for simulate mode",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    config = SimulationConfig.from_yaml(args.config)
    output_dir = Path(config.output_dir)

    if args.mode == "size":
        sizing = config.sizing or SizingConfig(
            capacities_kwh=[
                config.battery.capacity_kwh * f
                for f in (0.5, 0.75, 1.0, 1.25, 1.5)
            ]
        )
        if not sizing.enabled:
            logging.warning("Sizing disabled in config; using default capacities")
            sizing = SizingConfig(capacities_kwh=sizing.capacities_kwh)

        def _progress(stage: str, pct: float, detail: str) -> None:
            logging.info("%s: %.0f%% - %s", stage, pct, detail)

        use_auto = sizing.auto_sizing and sizing.capacity_min_kwh is not None and sizing.capacity_max_kwh is not None
        if use_auto:
            results = run_auto_sizing(config, progress_callback=_progress)
        else:
            results = run_sizing_sweep(
                config, sizing.capacities_kwh, progress_callback=_progress
            )
        constraints = {}
        if sizing.min_self_consumption_pct is not None:
            constraints["min_self_consumption_pct"] = sizing.min_self_consumption_pct
        if sizing.max_cycles_per_year is not None:
            constraints["max_cycles_per_year"] = sizing.max_cycles_per_year
        optimal = select_optimal(results, sizing.objective, constraints)

        # Build sizing results table
        rows = []
        for r in results:
            m = r["metrics"]
            rows.append({
                "capacity_kwh": r["capacity_kwh"],
                "grid_import_kw_min": m.get("grid_import_kw_min"),
                "self_consumption_pct": m.get("self_consumption_pct"),
                "cumulative_charge_count": m.get("cumulative_charge_count"),
                "recommended": r.get("recommended", False),
            })
        sizing_df = pl.DataFrame(rows)
        sizing_path = output_dir / f"{config.plant_name}_sizing_results.csv"
        output_dir.mkdir(parents=True, exist_ok=True)
        sizing_df.write_csv(sizing_path)
        print(f"Sizing results written to {sizing_path}")

        # Print table
        print("\nCapacity (kWh) | Grid import (kW-min) | Self-consumption % | Recommended")
        print("-" * 65)
        for r in results:
            m = r["metrics"]
            rec = " *" if r.get("recommended") else ""
            print(
                f"{r['capacity_kwh']:>14.0f} | "
                f"{m.get('grid_import_kw_min', 0):>19.0f} | "
                f"{m.get('self_consumption_pct', 0):>18.1f} |{rec}"
            )
        if optimal:
            print(f"\nRecommended capacity: {optimal['capacity_kwh']} kWh")
        else:
            print("\nNo capacity met constraints.")
        return 0

    result = simulate_system(config)
    parquet_path, metrics_path = write_simulation_outputs(result, output_dir, config.plant_name)
    print(f"Minute flows written to {parquet_path}")
    print(f"Summary metrics written to {metrics_path}")
    if args.dump_sections:
        aligned_input, context = load_aligned_inputs(config)
        section_paths = write_stage_outputs(aligned_input, context, output_dir, config.plant_name)
        print(f"Section CSVs written to {output_dir / f'{config.plant_name}_sections'}")
        for path in section_paths:
            print(f"section_csv: {path}")
    for key, value in result.summary_metrics.items():
        print(f"{key}: {value}")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
