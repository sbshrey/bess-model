"""Service helpers for the Flask/Jinja2 frontend."""

from __future__ import annotations

import csv
import html
import math
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable

import polars as pl
import yaml

from bess_model.config import SimulationConfig
from bess_model.core.pipeline import (
    FLOW_STAGES,
    SimulationContext,
    compute_summary_metrics,
    load_aligned_inputs,
    simulate_system,
    write_simulation_outputs,
)
from bess_model.config import SizingConfig
from bess_model.flows.section_outputs import write_section_outputs
from bess_model.results import SimulationResult
from bess_model.sizing import run_sizing_sweep, select_optimal



@dataclass(frozen=True)
class OutputFileInfo:
    """Represents a frontend-visible output artifact."""

    name: str
    relative_path: str
    absolute_path: Path
    size_kb: float
    modified_at: str


@dataclass(frozen=True)
class CsvPage:
    """A paginated CSV view."""

    columns: list[str]
    rows: list[dict[str, str]]
    row_numbers: list[int]
    page: int
    page_size: int
    total_rows: int
    total_pages: int


@dataclass(frozen=True)
class DateFilterState:
    """Date filter metadata for frontend controls."""

    enabled: bool
    start_date: str
    end_date: str
    min_date: str
    max_date: str
    filtered_rows: int
    total_rows: int


@dataclass(frozen=True)
class ChartCard:
    """Frontend chart metadata and SVG payload."""

    title: str
    subtitle: str
    svg: str


@dataclass(frozen=True)
class MetricCard:
    """High-level KPI card for dashboard display."""

    title: str
    value: str
    subtitle: str


@dataclass(frozen=True)
class FilteredCsvData:
    """A CSV file loaded with optional date filtering applied."""

    df: pl.DataFrame
    date_filter: DateFilterState


def load_config_text(config_path: Path) -> str:
    """Read the editable YAML configuration text."""
    return config_path.read_text(encoding="utf-8")


def save_config_text(config_path: Path, text: str) -> SimulationConfig:
    """Validate and persist frontend-edited YAML config text."""
    yaml_data = yaml.safe_load(text)
    if not isinstance(yaml_data, dict):
        raise ValueError("Configuration must be a dictionary.")
    # Let's write the text directly then parse it to ensure it's valid.
    config_path.write_text(text, encoding="utf-8")
    return SimulationConfig.from_yaml(config_path)


def save_config_form(config_path: Path, form_data: dict[str, str]) -> SimulationConfig:
    """Update nested YAML fields strictly from flattened form inputs."""
    text = config_path.read_text(encoding="utf-8")
    yaml_data = yaml.safe_load(text)
    if not isinstance(yaml_data, dict):
        yaml_data = {}

    # Keys whose values must be parsed as YAML (e.g. dict/mapping fields)
    table_keys = {"battery.charge_loss_table", "battery.discharge_loss_table"}

    # Keys that need special parsing
    skip_keys = {"config_text", "recalculate", "page", "page_size", "start_date", "end_date", "file"}
    bool_keys = {"preprocessing.align_to_full_year", "sizing.enabled"}
    list_float_keys = {"sizing.capacities_kwh"}
    nullable_float_keys = {
        "grid.import_limit_kw",
        "sizing.constraints.min_self_consumption_pct",
        "sizing.constraints.max_cycles_per_year",
    }

    for key, raw_value in form_data.items():
        if key in skip_keys:
            continue

        value: Any = raw_value

        if key in table_keys:
            # Parse loss table text (C-rate: loss per line) as YAML dict
            text = (raw_value or "").strip()
            if text:
                try:
                    parsed = yaml.safe_load(text)
                    value = {float(k): float(v) for k, v in (parsed.items() if isinstance(parsed, dict) else [])}
                except (yaml.YAMLError, TypeError, ValueError):
                    value = {}
            else:
                value = {}
        else:
            if key in bool_keys:
                value = str(raw_value).lower() in ("true", "on", "1", "yes")
            elif key in list_float_keys:
                text = (raw_value or "").strip()
                if text:
                    try:
                        value = [float(x.strip()) for x in text.replace(",", " ").split() if x.strip()]
                    except (TypeError, ValueError):
                        value = []
                else:
                    value = []
            elif key in nullable_float_keys:
                text = (raw_value or "").strip()
                if not text or text.lower() in ("null", "none", ""):
                    value = None
                else:
                    try:
                        value = float(text)
                    except (TypeError, ValueError):
                        value = None
            elif isinstance(value, str) and value.replace(".", "", 1).replace("-", "", 1).isdigit() and "." in value:
                value = float(value)
            elif isinstance(value, str) and value.replace("-", "", 1).isdigit():
                value = int(value)

        parts = key.split(".")
        current = yaml_data
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    updated_text = yaml.dump(yaml_data, sort_keys=False, default_flow_style=False)
    config_path.write_text(updated_text, encoding="utf-8")
    return SimulationConfig.from_yaml(config_path)


def run_simulation_from_frontend(config_path: Path) -> tuple[SimulationConfig, SimulationResult, list[Path]]:
    """Execute the simulation pipeline and construct all CSV assets."""
    config = SimulationConfig.from_yaml(config_path)
    result = simulate_system(config)
    write_simulation_outputs(result, config.output_dir, config.plant_name)
    stage_paths = _write_stage_snapshots(config, result=result)
    return config, result, stage_paths

def run_simulation_from_form_frontend(config_path: Path, form_data: dict[str, str]) -> tuple[SimulationConfig, SimulationResult, list[Path]]:
    """Save the form fields and execute the simulation pipeline."""
    save_config_form(config_path, form_data)
    return run_simulation_from_frontend(config_path)


def run_simulation_with_progress(
    config_path: Path,
    form_data: dict[str, str] | None,
    progress_yield: Callable[[str, float, str], None],
) -> tuple[SimulationConfig, SimulationResult, list[Path]]:
    """Run simulation, calling progress_yield(stage, pct, detail) at each checkpoint."""

    def progress_cb(stage: str, pct: float, detail: str) -> None:
        progress_yield(stage, round(pct, 1), detail)

    if form_data:
        save_config_form(config_path, form_data)

    config = SimulationConfig.from_yaml(config_path)

    progress_cb("Loading data", 0, "Starting simulation")
    result = simulate_system(config, progress_callback=progress_cb)

    progress_cb("Writing outputs", 92, "Writing Parquet and summary")
    write_simulation_outputs(result, config.output_dir, config.plant_name)

    progress_cb("Writing sections", 92, "Writing section CSVs")
    _write_stage_snapshots(config, result=result, progress_callback=progress_cb)

    progress_cb("Done", 100, f"Completed {result.summary_metrics['rows']} rows")
    return config, result, []



def get_file_insights(relative_path: str | None) -> dict[str, str] | None:
    """Return title, description, and how_it_works for a selected output file."""
    if not relative_path:
        return None
    name = relative_path.split("/")[-1] if "/" in relative_path else relative_path
    base = name.replace(".csv", "").replace(".parquet", "")

    insights_map: dict[str, dict[str, str]] = {
        "minute_flows": {
            "title": "Minute-level flows",
            "description": "Full simulation output with all derived columns in Parquet format.",
            "how": "Combines aligned input with section accounting results (generation, battery state, grid, SOC, cycles).",
        },
        "summary": {
            "title": "Summary metrics",
            "description": "One-row KPIs aggregated from the minute-level flows.",
            "how": "Sums grid buy/sell, takes final SOC and capacity, counts identity failures.",
        },
        "energy_table": {
            "title": "Energy table",
            "description": "Annual energy flows: SOURCES, USES, LOSS (kW-min).",
            "how": "Sums solar, wind, BESS draw, grid import (sources); charge BESS, sell to grid, output (uses); discharge and charge losses.",
        },
        "00_aligned_input": {
            "title": "Aligned input",
            "description": "Solar and wind generation aligned to a 1-minute grid.",
            "how": "Loads both CSVs, resamples to 1-minute, applies gap-fill strategy. Short gaps are interpolated, long gaps zero-filled.",
        },
        "01_wind_solar_generation": {
            "title": "Wind & solar generation",
            "description": "Raw generation values per minute.",
            "how": "From aligned input: wind_kw, solar_kw, total_generation_kw = solar + wind.",
        },
        "02_cumulative_generation": {
            "title": "Cumulative generation",
            "description": "Running total of wind, solar, and total generation (kW-min).",
            "how": "Cumulative sum of each generation column over time.",
        },
        "03_output_profile": {
            "title": "Output profile",
            "description": "Site load and total consumption per minute.",
            "how": "output_profile_kw + aux_consumption_kw = total_consumption_kw from config.",
        },
        "04_battery_capacity_cycles": {
            "title": "Battery capacity & degradation",
            "description": "Capacity degrades with cycle count.",
            "how": "capacity_now = nominal × (1 − cycles × degradation_per_cycle). Linear degradation model.",
        },
        "05_excess_deficit_power": {
            "title": "Excess / deficit power",
            "description": "Surplus or shortfall vs consumption each minute.",
            "how": "excess = max(generation − consumption, 0), deficit = max(consumption − generation, 0).",
        },
        "06_battery_opening_closing": {
            "title": "Battery state",
            "description": "Energy in battery at start and end of each minute (kW-min).",
            "how": "opening = prior closing; closing = opening − draw + store, bounded by capacity.",
        },
        "07_power_from_battery": {
            "title": "Power from battery",
            "description": "Discharge: required draw, C-rate, losses, net delivered.",
            "how": "Draw meets deficit. Loss from discharge_loss_table(C-rate). C-rate = power / capacity.",
        },
        "08_consume_from_grid": {
            "title": "Grid import",
            "description": "Power bought from grid when battery cannot cover deficit.",
            "how": "grid_buy = max(deficit − battery_draw_delivered, 0).",
        },
        "09_power_to_battery": {
            "title": "Power to battery",
            "description": "Charge: available store, C-rate, losses, net stored.",
            "how": "Store surplus up to headroom. Loss from charge_loss_table(C-rate).",
        },
        "10_sell_to_grid": {
            "title": "Grid export",
            "description": "Power sold to grid when surplus exceeds battery headroom.",
            "how": "grid_sell = max(excess − battery_store_available, 0).",
        },
        "11_soc_calculations": {
            "title": "State of charge",
            "description": "SOC in kW-min, fraction (0–1), and percent.",
            "how": "soc_fraction = closing_kw_min / nominal_capacity_kw_min; soc_pct = 100 × fraction.",
        },
        "12_battery_charge_cycles": {
            "title": "Cycle counts",
            "description": "Equivalent full charge/discharge cycles.",
            "how": "Discharge and charge cycles = cumulative energy / capacity. cum_charge_count = both combined.",
        },
        "13_identity_equation_1": {
            "title": "Energy balance identity",
            "description": "Checks: sources = uses + losses.",
            "how": "Sources: generation + draw + grid buy. Uses: consumption + store + grid sell. Losses: charge + discharge.",
        },
        "14_identity_equation_2": {
            "title": "BESS state identity",
            "description": "Checks battery state consistency. Includes identity_2_error_kw_min and battery_closing_kw_min for diagnostics.",
            "how": "closing = start − discharge − loss + charge − loss. identity_2_ok = 1 when |bess_finish − battery_closing| ≤ tolerance.",
        },
    }

    for key, info in insights_map.items():
        if base.endswith(key) or key in base:
            return info
    return None


def list_output_files(config: SimulationConfig) -> list[OutputFileInfo]:
    """List output files for the current plant, newest first."""
    output_dir = Path(config.output_dir)
    if not output_dir.exists():
        return []

    files: list[Path] = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            files.append(path)

    visible: list[OutputFileInfo] = []
    for path in files:
        stat = path.stat()
        visible.append(
            OutputFileInfo(
                name=path.name,
                relative_path=str(path.relative_to(output_dir)),
                absolute_path=path,
                size_kb=stat.st_size / 1024.0,
                modified_at=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
    visible.sort(key=lambda item: item.relative_path)
    return visible


def choose_default_output_file(config: SimulationConfig, outputs: list[OutputFileInfo]) -> str | None:
    """Pick the most useful default file for dashboard inspection."""
    if not outputs:
        return None

    preferred = [
        f"{config.plant_name}_sections/00_aligned_input.csv",
        f"{config.plant_name}_sections/11_soc_calculations.csv",
        f"{config.plant_name}_sections/06_battery_opening_closing.csv",
        f"{config.plant_name}_summary.csv",
    ]
    by_path = {item.relative_path: item for item in outputs}
    for relative_path in preferred:
        if relative_path in by_path:
            return relative_path

    csv_outputs = [item.relative_path for item in outputs if item.name.endswith(".csv")]
    return csv_outputs[0] if csv_outputs else outputs[0].relative_path


@dataclass(frozen=True)
class EnergyTableRow:
    """One row in the energy balance table (SOURCES, USES, LOSS)."""

    category: str
    element: str
    value_kw_min: float


def load_energy_table(config: SimulationConfig) -> list[EnergyTableRow] | None:
    """Load energy table from the latest simulation output when available."""
    energy_path = Path(config.output_dir) / f"{config.plant_name}_energy_table.csv"
    if not energy_path.exists():
        return None
    df = pl.read_csv(energy_path)
    if df.height == 0:
        return []
    return [
        EnergyTableRow(
            category=str(row["category"]),
            element=str(row["element"]),
            value_kw_min=float(row.get("value_kw_min", row.get("value_kwh", 0) * 60)),
        )
        for row in df.to_dicts()
    ]


def load_sizing_results(config: SimulationConfig) -> list[dict[str, Any]] | None:
    """Load sizing sweep results from CSV when available."""
    sizing_path = Path(config.output_dir) / f"{config.plant_name}_sizing_results.csv"
    if not sizing_path.exists():
        return None
    df = pl.read_csv(sizing_path)
    if df.height == 0:
        return []
    return df.to_dicts()


def run_sizing_with_progress(
    config_path: Path,
    progress_yield: Callable[[str, float, str], None],
) -> tuple[SimulationConfig, list[dict[str, Any]], dict[str, Any] | None]:
    """Run sizing sweep, calling progress_yield(stage, pct, detail) at each checkpoint."""

    def progress_cb(stage: str, pct: float, detail: str) -> None:
        progress_yield(stage, round(pct, 1), detail)

    config = SimulationConfig.from_yaml(config_path)
    sizing = config.sizing or SizingConfig(
        capacities_kwh=[
            config.battery.capacity_kwh * f
            for f in (0.5, 0.75, 1.0, 1.25, 1.5)
        ]
    )
    if not sizing.enabled:
        sizing = SizingConfig(capacities_kwh=sizing.capacities_kwh)

    progress_cb("Sizing sweep", 0, f"Running {len(sizing.capacities_kwh)} capacities")
    results = run_sizing_sweep(config, sizing.capacities_kwh, progress_callback=progress_cb)
    constraints = {}
    if sizing.min_self_consumption_pct is not None:
        constraints["min_self_consumption_pct"] = sizing.min_self_consumption_pct
    if sizing.max_cycles_per_year is not None:
        constraints["max_cycles_per_year"] = sizing.max_cycles_per_year
    optimal = select_optimal(results, sizing.objective, constraints)

    # Persist results
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
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_csv(output_dir / f"{config.plant_name}_sizing_results.csv")

    progress_cb("Done", 100, f"Recommended: {optimal['capacity_kwh']} kWh" if optimal else "No solution")
    return config, results, optimal


def load_metric_cards(config: SimulationConfig) -> list[MetricCard]:
    """Load KPI cards from the latest summary output; all plant summary columns plus green section."""
    summary_path = Path(config.output_dir) / f"{config.plant_name}_summary.csv"
    if not summary_path.exists():
        return [
            MetricCard("Plant", config.plant_name, "Current configuration"),
            MetricCard("Export Limit", _format_number(config.grid.export_limit_kw), "kW"),
            MetricCard("Battery", _format_number(config.battery.capacity_kwh), "kWh (config)"),
            MetricCard("Outputs", str(len(list_output_files(config))), "Generated files"),
        ]

    summary_df = pl.read_csv(summary_path)
    if summary_df.height == 0:
        return []
    row = summary_df.to_dicts()[0]

    def _kw_min(val: str, kwh_fallback: str) -> float:
        """Prefer kW-min column; fallback: convert kWh to kW-min (×60)."""
        v = row.get(val)
        if v is not None:
            return float(v)
        v = row.get(kwh_fallback)
        return float(v) * 60.0 if v is not None else 0.0

    cards: list[MetricCard] = [
        MetricCard("Rows", _format_number(row.get("rows", 0), digits=0), "Minute rows"),
        MetricCard("Grid Import", _format_number(_kw_min("grid_import_kw_min", "grid_import_energy_kwh")) + " kW-min", "Energy from grid"),
        MetricCard(
            "Self-Consumption",
            _format_number(row.get("self_consumption_pct", 0), digits=1) + "%",
            "Profile coverage (renewables+battery)",
        ),
        MetricCard("Grid Export", _format_number(_kw_min("grid_export_kw_min", "grid_export_energy_kwh")) + " kW-min", "Energy to grid"),
        MetricCard(
            "Degraded Capacity",
            _format_number(_kw_min("final_degraded_capacity_kw_min", "final_degraded_capacity_kwh")) + " kW-min",
            "Final battery capacity",
        ),
        MetricCard("Final SOC", _format_number(row.get("final_soc_pct", 0), digits=1) + "%", "State of charge"),
        MetricCard(
            "Cumulative Drawn",
            _format_number(_kw_min("cumulative_drawn_kw_min", "cumulative_drawn_energy_kwh")) + " kW-min",
            "Total from battery",
        ),
        MetricCard(
            "Cumulative Stored",
            _format_number(_kw_min("cumulative_stored_kw_min", "cumulative_stored_energy_kwh")) + " kW-min",
            "Total to battery",
        ),
        MetricCard(
            "Charge Count",
            _format_number(row.get("cumulative_charge_count", 0), digits=1),
            "Equivalent full cycles",
        ),
        MetricCard("Identity 1 Failures", str(row.get("identity_1_failures", 0)), "Energy balance violations"),
        MetricCard("Identity 2 Failures", str(row.get("identity_2_failures", 0)), "BESS state violations"),
        MetricCard(
            "Max Identity Error",
            _format_number(row.get("max_identity_error_kw", 0)) + " kW",
            "Identity 1 max error",
        ),
    ]
    if "identity_2_max_error_kw_min" in row:
        cards.append(
            MetricCard(
                "Identity 2 Max Error",
                _format_number(row.get("identity_2_max_error_kw_min", 0)) + " kW-min",
                "BESS state max error",
            )
        )
    return cards


def resolve_output_file(config: SimulationConfig, relative_path: str) -> Path:
    """Resolve a user-selected output file inside the output directory."""
    output_dir = Path(config.output_dir).resolve()
    target = (output_dir / relative_path).resolve()
    if output_dir not in target.parents and target != output_dir:
        raise ValueError("Output file is outside the configured output directory.")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"Output file not found: {relative_path}")
    return target


def load_csv_page(
    path: Path,
    page: int,
    page_size: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> CsvPage:
    """Load one page of CSV rows using the stdlib reader."""
    safe_page = max(page, 1)
    safe_size = max(1, min(page_size, 200))
    start_index = (safe_page - 1) * safe_size
    end_index = start_index + safe_size

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        timestamp_column = _detect_timestamp_header(columns)
        predicate = _build_row_date_predicate(start_date, end_date, timestamp_column)
        total_rows = 0
        rows: list[dict[str, str]] = []
        row_numbers: list[int] = []
        for index, row in enumerate(reader):
            if predicate is not None and not predicate(row):
                continue
            if start_index <= total_rows < end_index:
                formatted_row = {k: _format_cell_value(v) for k, v in row.items()}
                rows.append(formatted_row)
                row_numbers.append(index)
            total_rows += 1

    total_pages = max(1, math.ceil(total_rows / safe_size)) if total_rows else 1
    if safe_page > total_pages:
        return load_csv_page(path, total_pages, safe_size, start_date=start_date, end_date=end_date)
    return CsvPage(
        columns=columns,
        rows=rows,
        row_numbers=row_numbers,
        page=safe_page,
        page_size=safe_size,
        total_rows=total_rows,
        total_pages=total_pages,
    )


def save_csv_page_edits(path: Path, page: int, page_size: int, form: dict[str, str]) -> None:
    """Persist edited values for one page of a CSV file."""
    safe_page = max(page, 1)
    safe_size = max(1, min(page_size, 200))
    start = (safe_page - 1) * safe_size
    end = start + safe_size

    with path.open("r", newline="", encoding="utf-8") as source_handle:
        reader = csv.DictReader(source_handle)
        fieldnames = reader.fieldnames or []
        if not fieldnames:
            raise ValueError("CSV has no header row.")

        with tempfile.NamedTemporaryFile(
            "w",
            newline="",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as temp_handle:
            writer = csv.DictWriter(temp_handle, fieldnames=fieldnames)
            writer.writeheader()
            for index, row in enumerate(reader):
                if start <= index < end:
                    for column in fieldnames:
                        key = f"cell__{index}__{column}"
                        if key in form:
                            row[column] = form[key]
                writer.writerow(row)
            temp_path = Path(temp_handle.name)

    temp_path.replace(path)


def recalculate_from_edited_output(config: SimulationConfig, relative_path: str) -> list[Path]:
    """Recalculate all section outputs after an aligned-input edit."""
    path = resolve_output_file(config, relative_path)
    section_dir = Path(config.output_dir) / f"{config.plant_name}_sections"
    if path.parent.resolve() != section_dir.resolve() or path.name != "00_aligned_input.csv":
        raise ValueError("Only the aligned input CSV can trigger recalculation.")

    current_df = pl.read_csv(path, try_parse_dates=True)
    context = SimulationContext(config=config, logger=__import__("logging").getLogger("bess_model.web"))
    result_df = current_df
    for stage in FLOW_STAGES:
        result_df = stage(result_df, context)
    written: list[Path] = [path]
    written.extend(write_section_outputs(result_df, section_dir))

    summary = compute_summary_metrics(result_df, config.plant_name)
    write_simulation_outputs(
        SimulationResult(minute_flows=result_df, summary_metrics=summary),
        config.output_dir,
        config.plant_name,
    )
    return written


def load_filtered_csv(
    path: Path,
    start_date: str | None = None,
    end_date: str | None = None,
) -> FilteredCsvData:
    """Load a CSV and optionally filter it by inclusive day range."""
    df = pl.read_csv(path, try_parse_dates=True)
    filtered_df = _filter_df_by_date(df, start_date=start_date, end_date=end_date)
    return FilteredCsvData(
        df=filtered_df,
        date_filter=_build_date_filter_state(
            df,
            filtered_rows=filtered_df.height,
            total_rows=df.height,
            start_date=start_date,
            end_date=end_date,
        ),
    )


def build_preview_table(
    path: Path | None = None,
    limit: int = 20,
    df: pl.DataFrame | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Load a lightweight preview table for dashboard display."""
    preview_df = (df if df is not None else pl.read_csv(path, try_parse_dates=True)).head(limit)
    rows = preview_df.to_dicts()
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized_rows.append(
            {
                key: _format_cell_value(value)
                for key, value in row.items()
            }
        )
    return preview_df.columns, normalized_rows


def build_chart_svg(
    path: Path | None = None,
    preferred_columns: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    df: pl.DataFrame | None = None,
) -> str | None:
    """Render a small multi-series SVG line chart for a CSV output."""
    source_df = df if df is not None else load_filtered_csv(path, start_date=start_date, end_date=end_date).df
    return build_chart_svg_from_df(source_df, preferred_columns)


def build_chart_cards(
    path: Path | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    df: pl.DataFrame | None = None,
) -> list[ChartCard]:
    """Build richer chart cards for the selected CSV output."""
    if path is not None and path.suffix.lower() != ".csv":
        return []

    df = df if df is not None else load_filtered_csv(path, start_date=start_date, end_date=end_date).df
    columns = set(df.columns)
    charts: list[ChartCard] = []

    if {"soc_pct"}.issubset(columns):
        charts.append(_chart_card(df, "SOC Profile", "Battery SOC over time", ["soc_pct"]))

    if {"battery_capacity_kwh", "grid_import_energy_kwh"}.issubset(columns):
        charts.extend(
            [
                _chart_card(
                    df,
                    "Grid Outcome",
                    "Grid buy and sale versus capacity",
                    ["grid_export_energy_kwh", "grid_import_energy_kwh"],
                    x_column="battery_capacity_kwh",
                ),
                _chart_card(
                    df,
                    "Battery Usage",
                    "Charge count versus capacity",
                    ["cumulative_charge_count"],
                    x_column="battery_capacity_kwh",
                ),
            ]
        )

    if {"battery_opening_kw_min", "battery_closing_kw_min"}.issubset(columns):
        charts.append(
            _chart_card(
                df,
                "Battery State Window",
                "Opening and closing battery state",
                ["battery_opening_kw_min", "battery_closing_kw_min"],
            )
        )

    if {"grid_buy_kw", "grid_sell_kw"}.issubset(columns):
        charts.append(
            _chart_card(
                df,
                "Grid Buy / Sale",
                "Grid consumption and sale",
                ["grid_buy_kw", "grid_sell_kw"],
            )
        )

    if {"capacity_now_kwh"}.issubset(columns):
        charts.append(
            _chart_card(
                df,
                "Degraded Capacity",
                "Available battery capacity after degradation",
                ["capacity_now_kwh"],
            )
        )

    if {"cum_charge_count"}.issubset(columns):
        charts.append(
            _chart_card(
                df,
                "Cumulative Charge Count",
                "Cumulative charge count",
                ["cum_charge_count"],
            )
        )

    if not charts:
        svg = build_chart_svg_from_df(df)
        if svg:
            charts.append(ChartCard("Preview Chart", "Auto-selected numeric columns", svg))
    return [chart for chart in charts if chart.svg]


def build_chart_svg_from_df(
    df: pl.DataFrame,
    preferred_columns: list[str] | None = None,
    x_column: str = "timestamp",
    width: int = 1100,
    height: int = 380,
) -> str | None:
    """Render a multi-series SVG line chart from an existing DataFrame."""
    if df.height == 0:
        return None

    numeric_columns = [
        column
        for column, dtype in zip(df.columns, df.dtypes, strict=True)
        if column != x_column and dtype.is_numeric()
    ]
    if not numeric_columns:
        return None

    requested = preferred_columns or []
    columns = [column for column in requested if column in numeric_columns]
    if not columns:
        columns = numeric_columns[:4]
    if not columns:
        return None

    max_points = 360
    if df.height > max_points:
        step = max(1, math.ceil(df.height / max_points))
        df = df.gather_every(step)

    left_padding = 66
    right_padding = 18
    top_padding = 40
    bottom_padding = 46
    chart_height = height - top_padding - bottom_padding
    chart_width = width - left_padding - right_padding
    y_axis_label = _infer_y_axis_label(columns)
    x_axis_label = _infer_x_axis_label(x_column)

    x_values, x_tick_values, x_tick_labels = _build_x_axis_scale(df, x_column)
    if x_column in df.columns:
        original_x_values = df[x_column].to_list()
    else:
        original_x_values = [str(int(val)) for val in x_values]
    max_value = max(float(df.select(pl.max_horizontal([pl.col(column) for column in columns]).max()).item()), 1.0)
    colors = ["#4f46e5", "#10b981", "#f59e0b", "#f43f5e", "#8b5cf6"]

    series_svg: list[str] = []
    hover_svg: list[str] = []
    x_min = min(x_values)
    x_max = max(x_values)
    x_span = max(x_max - x_min, 1.0)
    for color_index, column in enumerate(columns):
        values = df[column].cast(pl.Float64).to_list()
        points: list[str] = []
        color = colors[color_index % len(colors)]
        for index, value in enumerate(values):
            if value is None:
                continue
            x = left_padding + ((x_values[index] - x_min) / x_span) * chart_width
            y = height - bottom_padding - ((float(value) / max_value) * chart_height)
            points.append(f"{x:.2f},{y:.2f}")

            # Custom SVG tooltip group
            tooltip_x = max(min(x, width - 110), 110)
            tooltip_y = max(y - 20, 60)
            x_str = str(original_x_values[index])

            hover_svg.append(
                f'<g class="chart-point-group">'
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="6" fill="transparent" class="chart-point-hover" />'
                f'<g class="chart-tooltip-group">'
                f'<rect x="{tooltip_x - 100:.2f}" y="{tooltip_y - 44:.2f}" width="200" height="38" fill="var(--ink)" fill-opacity="0.9" rx="6" style="filter: drop-shadow(0 4px 6px rgba(0,0,0,0.15))" />'
                f'<text x="{tooltip_x:.2f}" y="{tooltip_y - 28:.2f}" text-anchor="middle" fill="#94a3b8" font-size="10" font-weight="500" pointer-events="none">'
                f'{html.escape(x_str)}'
                f'</text>'
                f'<text x="{tooltip_x:.2f}" y="{tooltip_y - 12:.2f}" text-anchor="middle" fill="white" font-size="11" font-weight="600" pointer-events="none">'
                f'{html.escape(column)}: {_format_number(value)}'
                f'</text>'
                f'</g>'
                f'</g>'
            )

        legend_x = left_padding + (color_index * 130)
        series_svg.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{" ".join(points)}" />'
        )
        series_svg.append(
            f'<rect x="{legend_x}" y="10" width="10" height="10" fill="{color}" rx="2" />'
            f'<text x="{legend_x + 16}" y="19" fill="#475569" font-size="11" font-weight="600">{html.escape(column)}</text>'
        )

    y_ticks = _build_y_ticks(max_value)
    tick_svg: list[str] = []
    for tick_value in y_ticks:
        y = height - bottom_padding - ((tick_value / max_value) * chart_height)
        tick_svg.append(
            f'<line x1="{left_padding - 5}" y1="{y:.2f}" x2="{left_padding}" y2="{y:.2f}" stroke="#cbd5e1" stroke-width="1" />'
        )
        tick_svg.append(
            f'<text x="{left_padding - 9}" y="{y + 3:.2f}" text-anchor="end" fill="#64748b" font-size="10">{html.escape(_format_tick_value(tick_value))}</text>'
        )
        tick_svg.append(
            f'<line x1="{left_padding}" y1="{y:.2f}" x2="{width - right_padding}" y2="{y:.2f}" stroke="#f1f5f9" stroke-width="1" />'
        )

    for tick_value, tick_label in zip(x_tick_values, x_tick_labels, strict=True):
        x = left_padding + ((tick_value - x_min) / x_span) * chart_width
        tick_svg.append(
            f'<line x1="{x:.2f}" y1="{height - bottom_padding}" x2="{x:.2f}" y2="{height - bottom_padding + 5}" stroke="#cbd5e1" stroke-width="1" />'
        )
        tick_svg.append(
            f'<text x="{x:.2f}" y="{height - bottom_padding + 16}" text-anchor="middle" fill="#64748b" font-size="10">{html.escape(tick_label)}</text>'
        )

    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" '
        f'class="chart-svg" role="img" aria-label="Flow chart" '
        f'data-x-min="{x_min}" data-x-max="{x_max}" data-chart-width="{width}" data-chart-height="{height}">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" rx="12" />'
        f'<line x1="{left_padding}" y1="{height - bottom_padding}" x2="{width - right_padding}" y2="{height - bottom_padding}" '
        f'stroke="#cbd5e1" stroke-width="1.5" />'
        f'<line x1="{left_padding}" y1="{top_padding}" x2="{left_padding}" y2="{height - bottom_padding}" '
        f'stroke="#cbd5e1" stroke-width="1.5" />'
        f'{"".join(tick_svg)}'
        f'<text x="{left_padding + (chart_width / 2):.2f}" y="{height - 8}" text-anchor="middle" fill="#475569" font-weight="500" font-size="11">{html.escape(x_axis_label)}</text>'
        f'<text x="16" y="{top_padding + (chart_height / 2):.2f}" text-anchor="middle" fill="#475569" font-weight="500" font-size="11" transform="rotate(-90 16 {top_padding + (chart_height / 2):.2f})">{html.escape(y_axis_label)}</text>'
        f'{"".join(series_svg)}'
        f'{"".join(hover_svg)}'
        "</svg>"
    )


def _chart_card(
    df: pl.DataFrame,
    title: str,
    subtitle: str,
    columns: list[str],
    x_column: str = "timestamp",
) -> ChartCard:
    svg = build_chart_svg_from_df(df, columns, x_column=x_column) or ""
    return ChartCard(title=title, subtitle=subtitle, svg=svg)


def _format_number(value: Any, digits: int = 2) -> str:
    """Format numeric values for the dashboard."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if digits == 0:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


def _infer_x_axis_label(x_column: str) -> str:
    if x_column == "timestamp":
        return "Time"
    if x_column.endswith("_kw"):
        return f"{_humanize_column_name(x_column.removesuffix('_kw'))} (kW)"
    if x_column.endswith("_kwh"):
        return f"{_humanize_column_name(x_column.removesuffix('_kwh'))} (kWh)"
    if x_column.endswith("_pct"):
        return f"{_humanize_column_name(x_column.removesuffix('_pct'))} (%)"
    return _humanize_column_name(x_column)


def _infer_y_axis_label(columns: list[str]) -> str:
    if len(columns) == 1:
        column = columns[0]
        if column.endswith("_kw_min"):
            return f"{_humanize_column_name(column.removesuffix('_kw_min'))} (kW-min)"
        if column.endswith("_kw"):
            return f"{_humanize_column_name(column.removesuffix('_kw'))} (kW)"
        if column.endswith("_kwh"):
            return f"{_humanize_column_name(column.removesuffix('_kwh'))} (kWh)"
        if column.endswith("_pct"):
            return f"{_humanize_column_name(column.removesuffix('_pct'))} (%)"
        return _humanize_column_name(column)

    suffixes = {_column_unit_suffix(column) for column in columns}
    if suffixes == {"kw_min"}:
        return "Battery State (kW-min)"
    if suffixes == {"kw"}:
        return "Power (kW)"
    if suffixes == {"kwh"}:
        return "Energy (kWh)"
    if suffixes == {"pct"}:
        return "Percent (%)"
    return "Value"


def _column_unit_suffix(column: str) -> str:
    for suffix in ("kw_min", "kw", "kwh", "pct"):
        if column.endswith(f"_{suffix}"):
            return suffix
    return ""


def _humanize_column_name(column: str) -> str:
    words = column.replace("_", " ").split()
    normalized = ["SOC" if word.lower() == "soc" else word.capitalize() for word in words]
    return " ".join(normalized)


def _build_x_axis_scale(df: pl.DataFrame, x_column: str) -> tuple[list[float], list[float], list[str]]:
    if x_column in df.columns:
        series = df[x_column]
        dtype = df.schema[x_column]
        if dtype.is_temporal():
            datetimes = [value for value in series.to_list() if value is not None]
            if not datetimes:
                return _fallback_x_axis(df.height)
            numeric_values = [value.timestamp() for value in datetimes]
            tick_indices = _select_tick_indices(len(datetimes))
            tick_values = [numeric_values[index] for index in tick_indices]
            tick_labels = [_format_time_tick(datetimes[index], datetimes[0], datetimes[-1]) for index in tick_indices]
            return numeric_values, tick_values, tick_labels
        if dtype.is_numeric():
            numeric_values = [float(value) for value in series.cast(pl.Float64).to_list()]
            tick_indices = _select_tick_indices(len(numeric_values))
            tick_values = [numeric_values[index] for index in tick_indices]
            tick_labels = [_format_tick_value(numeric_values[index]) for index in tick_indices]
            return numeric_values, tick_values, tick_labels
    return _fallback_x_axis(df.height)


def _fallback_x_axis(length: int) -> tuple[list[float], list[float], list[str]]:
    numeric_values = [float(index) for index in range(max(length, 1))]
    tick_indices = _select_tick_indices(len(numeric_values))
    tick_values = [numeric_values[index] for index in tick_indices]
    tick_labels = [str(index + 1) for index in tick_indices]
    return numeric_values, tick_values, tick_labels


def _select_tick_indices(length: int, tick_count: int = 4) -> list[int]:
    if length <= 1:
        return [0]
    if length <= tick_count:
        return list(range(length))
    indices = [round(step * (length - 1) / (tick_count - 1)) for step in range(tick_count)]
    deduped: list[int] = []
    for index in indices:
        if index not in deduped:
            deduped.append(index)
    return deduped


def _build_y_ticks(max_value: float, tick_count: int = 4) -> list[float]:
    if max_value <= 0:
        return [0.0]
    return [max_value * step / tick_count for step in range(tick_count + 1)]


def _format_tick_value(value: float) -> str:
    absolute = abs(value)
    if absolute >= 1000:
        return f"{value:,.0f}"
    if absolute >= 10:
        return f"{value:.0f}"
    if absolute >= 1:
        return f"{value:.1f}"
    return f"{value:.2f}"


def _format_time_tick(value: datetime, start: datetime, end: datetime) -> str:
    if start.date() == end.date():
        return value.strftime("%H:%M")
    if start.year == end.year:
        return value.strftime("%d %b")
    return value.strftime("%Y-%m-%d")


def normalize_date_input(value: str | None) -> str:
    """Normalize a query/form date string to ISO format."""
    if not value:
        return ""
    value = value.strip()
    try:
        if " " in value or "T" in value:
             return datetime.fromisoformat(value.replace(" ", "T")).isoformat(sep=" ")
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return ""


def _write_stage_snapshots(
    config: SimulationConfig,
    result: SimulationResult | None = None,
    progress_callback: Callable[[str, float, str], None] | None = None,
) -> list[Path]:
    """Write aligned input and each section CSV once. Uses existing result if provided to avoid re-running and OOM with float64."""
    section_dir = Path(config.output_dir) / f"{config.plant_name}_sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    if result is not None:
        # Use already-computed minute_flows: write 00 from input columns, then section CSVs in chunks (avoids re-run + OOM)
        df = result.minute_flows
        aligned_cols = [c for c in ("timestamp", "wind_kw", "solar_kw", "total_generation_kw") if c in df.columns]
        if aligned_cols:
            if progress_callback:
                progress_callback("Writing sections", 93.0, "Writing 00_aligned_input.csv")
            input_path = section_dir / "00_aligned_input.csv"
            _write_csv_chunked(df, input_path, columns=aligned_cols)
            written.append(input_path)
        written.extend(
            write_section_outputs(df, section_dir, progress_callback=progress_callback)
        )
        return written

    # Legacy path: load and run pipeline (e.g. recalculate from edited CSV)
    if progress_callback:
        progress_callback("Writing sections", 93.0, "Writing 00_aligned_input.csv")
    aligned_input, context = load_aligned_inputs(config)
    input_path = section_dir / "00_aligned_input.csv"
    _write_csv_chunked(aligned_input, input_path)
    written.append(input_path)

    result_df = aligned_input
    for stage in FLOW_STAGES:
        result_df = stage(result_df, context)
    written.extend(write_section_outputs(result_df, section_dir))
    return written


def _write_csv_chunked(
    df: pl.DataFrame,
    path: Path,
    chunk_rows: int = 50_000,
    columns: list[str] | None = None,
) -> None:
    """Write a DataFrame to CSV in row chunks to limit peak memory (no full-frame select)."""
    cols = columns or df.columns
    cols = [c for c in cols if c in df.columns]
    n_rows = df.height
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for start in range(0, n_rows, chunk_rows):
            chunk = df.slice(start, chunk_rows).select(cols)
            for row in chunk.iter_rows():
                writer.writerow(row)


def _detect_timestamp_column(df: pl.DataFrame) -> str | None:
    for column, dtype in zip(df.columns, df.dtypes, strict=True):
        if column == "timestamp":
            return column
        if dtype.is_temporal():
            return column
    return None


def _detect_timestamp_header(columns: list[str]) -> str | None:
    if "timestamp" in columns:
        return "timestamp"
    return None


def _filter_df_by_date(df: pl.DataFrame, start_date: str | None, end_date: str | None) -> pl.DataFrame:
    timestamp_column = _detect_timestamp_column(df)
    if not timestamp_column:
        return df

    normalized_start = normalize_date_input(start_date) if start_date else ""
    normalized_end = normalize_date_input(end_date) if end_date else ""
    if not normalized_start and not normalized_end:
        return df

    filtered = df
    if normalized_start:
        if " " in normalized_start:
            start_dt = datetime.fromisoformat(normalized_start.replace(" ", "T"))
        else:
            start_dt = datetime.combine(date.fromisoformat(normalized_start), time.min)
        filtered = filtered.filter(pl.col(timestamp_column) >= pl.lit(start_dt))
    if normalized_end:
        if " " in normalized_end:
            end_dt = datetime.fromisoformat(normalized_end.replace(" ", "T"))
        else:
            end_dt = datetime.combine(date.fromisoformat(normalized_end) + timedelta(days=1), time.min)
        filtered = filtered.filter(pl.col(timestamp_column) < pl.lit(end_dt))
    return filtered


def _build_date_filter_state(
    df: pl.DataFrame,
    filtered_rows: int,
    total_rows: int,
    start_date: str | None,
    end_date: str | None,
) -> DateFilterState:
    timestamp_column = _detect_timestamp_column(df)
    if not timestamp_column or df.height == 0:
        return DateFilterState(
            enabled=False,
            start_date="",
            end_date="",
            min_date="",
            max_date="",
            filtered_rows=filtered_rows,
            total_rows=total_rows,
        )

    values = df.select(
        pl.col(timestamp_column).min().alias("min_timestamp"),
        pl.col(timestamp_column).max().alias("max_timestamp"),
    ).to_dicts()[0]
    min_timestamp = values["min_timestamp"]
    max_timestamp = values["max_timestamp"]
    min_date = min_timestamp.date().isoformat() if hasattr(min_timestamp, "date") else ""
    max_date = max_timestamp.date().isoformat() if hasattr(max_timestamp, "date") else ""
    normalized_start = normalize_date_input(start_date) if start_date else ""
    normalized_end = normalize_date_input(end_date) if end_date else ""
    return DateFilterState(
        enabled=True,
        start_date=normalized_start or min_date,
        end_date=normalized_end or max_date,
        min_date=min_date,
        max_date=max_date,
        filtered_rows=filtered_rows,
        total_rows=total_rows,
    )


def _format_cell_value(val: Any) -> Any:
    """Format a cell value for display, applying reasonable float rounding."""
    if isinstance(val, str):
        try:
            if len(val) >= 19 and val[4] == '-' and val[7] == '-' and val[13] == ':':
                dt = datetime.fromisoformat(val.replace(" ", "T"))
                return dt.strftime("%d %b %Y %H:%M:%S")
        except ValueError:
            pass
    if hasattr(val, "isoformat"):
        return val.isoformat(sep=" ")

    if isinstance(val, float):
        if math.isnan(val):
            return "NaN"
        return round(val, 6)

    if isinstance(val, str):
        try:
            if "." in val or "e" in val.lower():
                fval = float(val)
                if math.isnan(fval):
                    return "NaN"
                # Keep it as a string to preserve the CSV DictReader format semantics
                return str(round(fval, 6))
        except ValueError:
            pass

    return val

def _build_row_date_predicate(
    start_date: str | None,
    end_date: str | None,
    timestamp_column: str | None,
):
    normalized_start = normalize_date_input(start_date) if start_date else ""
    normalized_end = normalize_date_input(end_date) if end_date else ""
    if not timestamp_column or (not normalized_start and not normalized_end):
        return None

    if normalized_start:
        if " " in normalized_start:
            start_bound = datetime.fromisoformat(normalized_start.replace(" ", "T"))
        else:
            start_bound = datetime.combine(date.fromisoformat(normalized_start), time.min)
    else:
        start_bound = None

    if normalized_end:
        if " " in normalized_end:
            end_bound = datetime.fromisoformat(normalized_end.replace(" ", "T"))
        else:
            end_bound = datetime.combine(date.fromisoformat(normalized_end) + timedelta(days=1), time.min)
    else:
        end_bound = None

    def predicate(row: dict[str, str]) -> bool:
        timestamp_value = _parse_timestamp_text(row.get(timestamp_column, ""))
        if timestamp_value is None:
            return False
        if start_bound and timestamp_value < start_bound:
            return False
        if end_bound and timestamp_value >= end_bound:
            return False
        return True

    return predicate


def _parse_timestamp_text(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("T", " ")
    for parser in (
        lambda text: datetime.fromisoformat(text),
        lambda text: datetime.strptime(text, "%Y-%m-%d %H:%M:%S"),
        lambda text: datetime.strptime(text, "%Y-%m-%d %H:%M"),
    ):
        try:
            return parser(normalized)
        except ValueError:
            continue
    return None
