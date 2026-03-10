"""Pipeline orchestration for section-based BESS simulations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import polars as pl

from bess_model.config import SimulationConfig
from bess_model.data.loaders import load_generation_data
from bess_model.data.preprocessing import align_generation_to_minute
from bess_model.flows.section_outputs import section_accounting_stage, write_section_outputs
from bess_model.results import SimulationResult

StageFn = Callable[[pl.DataFrame, "SimulationContext"], pl.DataFrame]


@dataclass
class SimulationContext:
    """Shared state and helpers for section execution."""

    config: SimulationConfig
    logger: logging.Logger
    balance_tolerance_kw: float = 1e-9

    def log_stage(self, stage_name: str, df: pl.DataFrame) -> None:
        """Emit concise stage-level logging."""
        self.logger.info("Completed stage %s with %s rows", stage_name, df.height)

    def validate_balance(self, df: pl.DataFrame) -> None:
        """Reject materially invalid identity equations."""
        max_abs_error = df.select(pl.col("identity_1_error_kw").abs().max()).item()
        if max_abs_error is None:
            return
        if max_abs_error > self.balance_tolerance_kw:
            raise ValueError(f"Energy balance validation failed. Max error was {max_abs_error:.12f}.")


FLOW_STAGES: list[StageFn] = [section_accounting_stage]


def simulate_system(config: SimulationConfig) -> SimulationResult:
    """Run a single BESS simulation from source data to KPI summary."""
    logger = logging.getLogger(f"bess_model.{config.plant_name}")
    context = SimulationContext(config=config, logger=logger)

    solar, wind = load_generation_data(config)
    minute_data = align_generation_to_minute(solar, wind, config.preprocessing)
    final_df = run_pipeline(minute_data, context, FLOW_STAGES)
    metrics = compute_summary_metrics(final_df, config.plant_name)
    return SimulationResult(minute_flows=final_df, summary_metrics=metrics)


def load_aligned_inputs(config: SimulationConfig) -> tuple[pl.DataFrame, SimulationContext]:
    """Load raw generation inputs and return the aligned minute-level table."""
    logger = logging.getLogger(f"bess_model.{config.plant_name}")
    context = SimulationContext(config=config, logger=logger)
    solar, wind = load_generation_data(config)
    minute_data = align_generation_to_minute(solar, wind, config.preprocessing)
    return minute_data, context


def run_pipeline(
    df: pl.DataFrame,
    context: SimulationContext,
    stages: list[StageFn] | None = None,
) -> pl.DataFrame:
    """Apply each registered stage in sequence."""
    active_stages = stages or FLOW_STAGES
    result = df
    for stage in active_stages:
        result = stage(result, context)
        context.log_stage(stage.__name__, result)
    return result


def compute_summary_metrics(df: pl.DataFrame, plant_name: str) -> dict[str, float | int | str]:
    """Aggregate minute-level section outputs into KPI metrics."""
    return {
        "plant_name": plant_name,
        "rows": df.height,
        "grid_import_energy_kwh": _sum_kw_as_kwh(df, "grid_buy_kw"),
        "grid_export_energy_kwh": _sum_kw_as_kwh(df, "grid_sell_kw"),
        "final_degraded_capacity_kwh": float(df.select(pl.col("capacity_now_kwh").tail(1)).item()),
        "final_soc_pct": float(df.select(pl.col("soc_pct").tail(1)).item()),
        "cumulative_drawn_energy_kwh": float(df.select(pl.col("battery_draw_cumulative_kw_min").tail(1)).item()) / 60.0,
        "cumulative_stored_energy_kwh": float(df.select(pl.col("battery_store_cumulative_kw_min").tail(1)).item()) / 60.0,
        "cumulative_charge_count": float(df.select(pl.col("cum_charge_count").tail(1)).item()),
        "identity_1_failures": int(df.select((1 - pl.col("identity_1_ok")).sum()).item()),
        "identity_2_failures": int(df.select((1 - pl.col("identity_2_ok")).sum()).item()),
        "max_identity_error_kw": float(df.select(pl.col("identity_1_error_kw").abs().max()).item()),
    }


def write_simulation_outputs(result: SimulationResult, output_dir: str | Path, stem: str) -> tuple[Path, Path]:
    """Persist minute-level flows and summary metrics."""
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = target_dir / f"{stem}_minute_flows.parquet"
    metrics_path = target_dir / f"{stem}_summary.csv"
    result.minute_flows.write_parquet(parquet_path)
    pl.DataFrame([result.summary_metrics]).write_csv(metrics_path)
    return parquet_path, metrics_path


def write_stage_outputs(
    df: pl.DataFrame,
    context: SimulationContext,
    output_dir: str | Path,
    stem: str,
    stages: list[StageFn] | None = None,
) -> list[Path]:
    """Write aligned input and section CSV outputs."""
    target_dir = Path(output_dir) / f"{stem}_sections"
    target_dir.mkdir(parents=True, exist_ok=True)

    written_paths: list[Path] = []
    input_path = target_dir / "00_aligned_input.csv"
    df.write_csv(input_path)
    written_paths.append(input_path)

    stage_df = run_pipeline(df, context, stages or FLOW_STAGES)
    written_paths.extend(write_section_outputs(stage_df, target_dir))
    return written_paths


def _sum_kw_as_kwh(df: pl.DataFrame, column: str) -> float:
    return float(df.select((pl.col(column) / 60.0).sum()).item())
