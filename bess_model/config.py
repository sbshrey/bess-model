"""Configuration models and YAML loading helpers."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

DEFAULT_DEGRADATION_PER_CYCLE = 0.0002739726027
DEFAULT_CHARGE_LOSS_TABLE = {
    0.0: 0.0,
    0.1: 0.04,
    0.2: 0.04,
    0.3: 0.045,
    0.4: 0.0575,
    0.5: 0.07,
    0.6: 0.078,
    0.7: 0.086,
    0.8: 0.094,
    0.9: 0.102,
    1.0: 0.11,
    1.1: 0.125,
    1.2: 0.14,
    1.3: 0.14,
    1.4: 0.14,
    1.5: 0.14,
}
DEFAULT_DISCHARGE_LOSS_TABLE = {
    0.0: 0.0,
    0.1: 0.023,
    0.2: 0.023,
    0.3: 0.032,
    0.4: 0.037,
    0.5: 0.042,
    0.6: 0.046,
    0.7: 0.05,
    0.8: 0.054,
    0.9: 0.058,
    1.0: 0.062,
    1.1: 0.0645,
    1.2: 0.067,
    1.3: 0.067,
    1.4: 0.067,
    1.5: 0.067,
}


@dataclass(frozen=True)
class DataConfig:
    """Paths to source generation data."""

    solar_path: str
    wind_path: str


@dataclass(frozen=True)
class PreprocessingConfig:
    """Controls timestamp alignment and missing-data handling."""

    frequency: str = "1m"
    gap_fill: str = "linear_interpolate"
    max_interpolation_gap_minutes: int = 15
    align_to_full_year: bool = True
    simulation_dtype: str = "float32"
    simulation_chunk_size: int | None = None


@dataclass(frozen=True)
class GridConfig:
    """Grid import and export limits."""

    export_limit_kw: float
    import_limit_kw: float | None = None


@dataclass(frozen=True)
class LoadConfig:
    """Site load assumptions."""

    output_profile_kw: float
    aux_consumption_kw: float


@dataclass(frozen=True)
class SizingConfig:
    """Battery sizing sweep configuration."""

    enabled: bool = True
    capacities_kwh: list[float] = field(default_factory=lambda: [500.0, 750.0, 1000.0, 1250.0, 1500.0])
    objective: str = "min_grid_import_then_smallest"
    min_self_consumption_pct: float | None = None
    max_cycles_per_year: float | None = None


@dataclass(frozen=True)
class BatteryConfig:
    """Battery power and energy constraints."""

    nominal_power_kw: float
    duration_hours: float
    initial_soc_fraction: float = 1.0
    degradation_per_cycle: float = DEFAULT_DEGRADATION_PER_CYCLE
    charge_loss_table: dict[float, float] = field(
        default_factory=lambda: dict(DEFAULT_CHARGE_LOSS_TABLE)
    )
    discharge_loss_table: dict[float, float] = field(
        default_factory=lambda: dict(DEFAULT_DISCHARGE_LOSS_TABLE)
    )
    min_soc_fraction: float = 0.0
    max_soc_fraction: float = 1.0
    max_charge_kw: float = 0.0
    max_discharge_kw: float = 0.0
    charge_efficiency: float = 1.0
    discharge_efficiency: float = 1.0

    @property
    def capacity_kwh(self) -> float:
        return self.nominal_power_kw * self.duration_hours

    @property
    def initial_soc_kwh(self) -> float:
        return self.capacity_kwh * self.initial_soc_fraction

    def with_capacity(self, capacity_kwh: float) -> "BatteryConfig":
        duration = self.duration_hours if self.duration_hours > 0 else 1.0
        return replace(
            self,
            nominal_power_kw=capacity_kwh / duration,
            max_charge_kw=capacity_kwh,
            max_discharge_kw=capacity_kwh,
        )

    def with_nominal_power(self, nominal_power_kw: float) -> "BatteryConfig":
        capacity_kwh = nominal_power_kw * self.duration_hours
        return replace(
            self,
            nominal_power_kw=nominal_power_kw,
            max_charge_kw=capacity_kwh,
            max_discharge_kw=capacity_kwh,
        )


@dataclass(frozen=True)
class SimulationConfig:
    """Top-level simulation configuration."""

    plant_name: str
    data: DataConfig
    preprocessing: PreprocessingConfig
    grid: GridConfig
    load: LoadConfig
    battery: BatteryConfig
    output_dir: str = "output"
    sizing: SizingConfig | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SimulationConfig":
        """Build a typed config from a nested dictionary."""
        battery = _normalize_battery_payload(payload["battery"])
        sizing = _normalize_sizing_payload(payload.get("sizing"))
        config = cls(
            plant_name=payload["plant_name"],
            data=DataConfig(**payload["data"]),
            preprocessing=PreprocessingConfig(**payload.get("preprocessing", {})),
            grid=GridConfig(**payload["grid"]),
            load=LoadConfig(**payload["load"]),
            battery=BatteryConfig(**battery),
            output_dir=payload.get("output_dir", "output"),
            sizing=sizing,
        )
        config.validate()
        return config

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SimulationConfig":
        """Load config from a YAML file."""
        with Path(path).open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Configuration root must be a mapping.")
        return cls.from_dict(payload)

    def with_battery_capacity(self, capacity_kwh: float) -> "SimulationConfig":
        """Clone the config with a different battery capacity."""
        return replace(self, battery=self.battery.with_capacity(capacity_kwh))

    def with_battery_nominal_power(self, nominal_power_kw: float) -> "SimulationConfig":
        """Clone the config with a different nominal battery power."""
        return replace(self, battery=self.battery.with_nominal_power(nominal_power_kw))

    def validate(self) -> None:
        """Validate critical configuration bounds."""
        if self.grid.export_limit_kw <= 0:
            raise ValueError("grid.export_limit_kw must be positive.")
        if self.battery.capacity_kwh < 0:
            raise ValueError("battery.capacity_kwh must be non-negative.")
        if self.battery.duration_hours <= 0:
            raise ValueError("battery.duration_hours must be positive.")
        if not 0 < self.battery.charge_efficiency <= 1:
            raise ValueError("battery.charge_efficiency must be within (0, 1].")
        if not 0 < self.battery.discharge_efficiency <= 1:
            raise ValueError("battery.discharge_efficiency must be within (0, 1].")
        if not 0 <= self.battery.initial_soc_fraction <= 1:
            raise ValueError("battery.initial_soc_fraction must be within [0, 1].")
        if not 0 <= self.battery.min_soc_fraction <= self.battery.max_soc_fraction <= 1:
            raise ValueError("battery SOC bounds must satisfy 0 <= min <= max <= 1.")
        if self.preprocessing.max_interpolation_gap_minutes < 0:
            raise ValueError("max_interpolation_gap_minutes must be non-negative.")


def _normalize_battery_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)

    if "nominal_power_kw" in normalized and "duration_hours" in normalized:
        nominal_power_kw = float(normalized["nominal_power_kw"])
        duration_hours = float(normalized["duration_hours"])
        capacity_kwh = nominal_power_kw * duration_hours
    else:
        capacity_kwh = float(normalized["capacity_kwh"])
        legacy_max_charge = float(normalized.get("max_charge_kw", capacity_kwh))
        legacy_max_discharge = float(normalized.get("max_discharge_kw", capacity_kwh))
        nominal_power_kw = max(legacy_max_charge, legacy_max_discharge)
        if nominal_power_kw <= 0:
            nominal_power_kw = capacity_kwh
        duration_hours = float(normalized.get("duration_hours", capacity_kwh / nominal_power_kw))

    initial_soc_fraction = normalized.get("initial_soc_fraction")
    if initial_soc_fraction is None:
        initial_soc_kwh = normalized.get("initial_soc_kwh")
        if initial_soc_kwh is None:
            initial_soc_fraction = 1.0
        elif capacity_kwh > 0:
            initial_soc_fraction = float(initial_soc_kwh) / capacity_kwh
        else:
            initial_soc_fraction = 0.0

    charge_loss_table = _normalize_loss_table(
        normalized.get("charge_loss_table", DEFAULT_CHARGE_LOSS_TABLE),
        DEFAULT_CHARGE_LOSS_TABLE,
    )
    discharge_loss_table = _normalize_loss_table(
        normalized.get("discharge_loss_table", DEFAULT_DISCHARGE_LOSS_TABLE),
        DEFAULT_DISCHARGE_LOSS_TABLE,
    )

    charge_efficiency = float(
        normalized.get("charge_efficiency", 1.0 - charge_loss_table.get(1.0, 0.0))
    )
    discharge_efficiency = float(
        normalized.get("discharge_efficiency", 1.0 - discharge_loss_table.get(1.0, 0.0))
    )

    return {
        "nominal_power_kw": nominal_power_kw,
        "duration_hours": duration_hours,
        "initial_soc_fraction": float(initial_soc_fraction),
        "degradation_per_cycle": float(
            normalized.get("degradation_per_cycle", DEFAULT_DEGRADATION_PER_CYCLE)
        ),
        "charge_loss_table": charge_loss_table,
        "discharge_loss_table": discharge_loss_table,
        "min_soc_fraction": float(normalized.get("min_soc_fraction", 0.0)),
        "max_soc_fraction": float(normalized.get("max_soc_fraction", 1.0)),
        "max_charge_kw": float(normalized.get("max_charge_kw", capacity_kwh)),
        "max_discharge_kw": float(normalized.get("max_discharge_kw", capacity_kwh)),
        "charge_efficiency": charge_efficiency,
        "discharge_efficiency": discharge_efficiency,
    }



def _normalize_sizing_payload(payload: dict[str, Any] | None) -> SizingConfig | None:
    """Parse sizing config from YAML. Returns None if not present or disabled."""
    if not payload:
        return None
    if payload.get("enabled") is False:
        return None
    raw_caps = payload.get("capacities_kwh")
    if raw_caps:
        capacities = [float(c) for c in raw_caps]
    else:
        capacities = [500.0, 750.0, 1000.0, 1250.0, 1500.0]
    constraints = payload.get("constraints") or {}
    min_sc = constraints.get("min_self_consumption_pct")
    max_cy = constraints.get("max_cycles_per_year")
    return SizingConfig(
        enabled=bool(payload.get("enabled", True)),
        capacities_kwh=capacities,
        objective=str(payload.get("objective", "min_grid_import_then_smallest")),
        min_self_consumption_pct=float(min_sc) if min_sc is not None else None,
        max_cycles_per_year=float(max_cy) if max_cy is not None else None,
    )


def _normalize_loss_table(
    payload: dict[float | str, float] | None,
    defaults: dict[float, float],
) -> dict[float, float]:
    source = payload or defaults
    return {float(key): float(value) for key, value in source.items()}
