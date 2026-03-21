"""Workbook export helpers for stakeholder energy packages."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Sequence

import polars as pl

PACKAGE_SHEETS: tuple[tuple[str, str], ...] = (
    ("Energy Table", "energy_table_all_cases.csv"),
    ("Scenario Summary", "scenario_summary_all_cases.csv"),
    ("Scenario Index", "scenario_index.csv"),
)


def export_stakeholder_workbook(
    input_dir: str | Path,
    *,
    output: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write a compact workbook for a stakeholder package and refresh its zip."""
    package_dir = Path(input_dir).expanduser().resolve()
    if not package_dir.exists():
        raise FileNotFoundError(f"Stakeholder package directory not found: {package_dir}")
    if not package_dir.is_dir():
        raise NotADirectoryError(f"Stakeholder package path is not a directory: {package_dir}")

    workbook_path = _resolve_output_path(package_dir, output)
    sheet_frames = _load_sheet_frames(package_dir)
    _write_workbook(sheet_frames, workbook_path)
    zip_path = refresh_package_archive(package_dir)
    return workbook_path, zip_path


def refresh_package_archive(package_dir: str | Path) -> Path:
    """Rebuild the shareable zip beside the stakeholder package directory."""
    package_path = Path(package_dir).expanduser().resolve()
    archive_path = shutil.make_archive(
        str(package_path),
        "zip",
        root_dir=str(package_path.parent),
        base_dir=package_path.name,
    )
    return Path(archive_path)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for workbook export."""
    parser = argparse.ArgumentParser(
        description="Export a compact Excel workbook for a stakeholder energy package."
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Path to the stakeholder package directory.",
    )
    parser.add_argument(
        "--output",
        help=(
            "Optional workbook file name or path inside the package directory. "
            "Defaults to <input-dir>/<input-dir-name>.xlsx."
        ),
    )
    args = parser.parse_args(argv)

    try:
        workbook_path, zip_path = export_stakeholder_workbook(
            args.input_dir,
            output=args.output,
        )
    except Exception as exc:  # pragma: no cover - exercised via function tests
        parser.exit(1, f"Error: {exc}\n")

    print(f"Workbook written to {workbook_path}")
    print(f"Package zip refreshed at {zip_path}")
    return 0


def _resolve_output_path(package_dir: Path, output: str | Path | None) -> Path:
    if output is None:
        return package_dir / f"{package_dir.name}.xlsx"

    raw_output = Path(output)
    output_path = raw_output if raw_output.is_absolute() else package_dir / raw_output
    output_path = output_path.expanduser().resolve()

    try:
        output_path.relative_to(package_dir)
    except ValueError as exc:
        raise ValueError(
            "--output must point to a file inside the stakeholder package directory "
            "so the refreshed zip includes the workbook."
        ) from exc

    if output_path.suffix.lower() != ".xlsx":
        raise ValueError("Workbook output must use a .xlsx extension.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def _load_sheet_frames(package_dir: Path) -> list[tuple[str, pl.DataFrame]]:
    missing = [filename for _, filename in PACKAGE_SHEETS if not (package_dir / filename).exists()]
    if missing:
        joined = ", ".join(missing)
        raise FileNotFoundError(
            f"Missing required stakeholder package files in {package_dir}: {joined}"
        )

    return [
        (sheet_name, pl.read_csv(package_dir / filename))
        for sheet_name, filename in PACKAGE_SHEETS
    ]


def _write_workbook(sheet_frames: list[tuple[str, pl.DataFrame]], workbook_path: Path) -> None:
    import xlsxwriter

    workbook = xlsxwriter.Workbook(str(workbook_path))
    try:
        for sheet_name, frame in sheet_frames:
            frame.write_excel(
                workbook=workbook,
                worksheet=sheet_name,
                freeze_panes="A2",
                autofilter=True,
                autofit=True,
                float_precision=2,
                column_formats=_column_formats(frame),
            )
    finally:
        workbook.close()


def _column_formats(frame: pl.DataFrame) -> dict[str, str] | None:
    formats: dict[str, str] = {}
    for column_name, dtype in frame.schema.items():
        if dtype.is_float():
            formats[column_name] = "#,##0.00"
        elif dtype.is_integer():
            formats[column_name] = "#,##0"
    return formats or None


if __name__ == "__main__":
    raise SystemExit(main())
