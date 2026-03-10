"""Typed return models for simulation and sizing runs."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class SimulationResult:
    """Minute-level outputs and aggregate metrics for a single run."""

    minute_flows: pl.DataFrame
    summary_metrics: dict[str, float | int | str]


@dataclass(frozen=True)
class SizingResult:
    """Results for a capacity sweep."""

    results: pl.DataFrame
    optimal_capacity_kwh: float
