"""CLI entrypoint for running simulation or sizing flows."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from bess_model.config import SimulationConfig
from bess_model.core.pipeline import (
    load_aligned_inputs,
    simulate_system,
    write_simulation_outputs,
    write_stage_outputs,
)
from bess_model.sizing.optimizer import run_sizing


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI arguments and execute the requested mode."""
    parser = argparse.ArgumentParser(description="BESS simulation and sizing runner")
    parser.add_argument("--config", required=True, help="Path to a YAML configuration file")
    parser.add_argument(
        "--mode",
        choices=("simulate", "size"),
        default="simulate",
        help="Whether to run one simulation or a sizing sweep",
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

    if args.mode == "simulate":
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

    sizing_result = run_sizing(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / f"{config.plant_name}_sizing_results.csv"
    sizing_result.results.write_csv(result_path)
    print(f"Sizing results written to {result_path}")
    print(f"optimal_capacity_kwh: {sizing_result.optimal_capacity_kwh}")
    return 0
