from __future__ import annotations

import logging
from datetime import datetime

import polars as pl
import pytest

from bess_model.config import LoadConfig, SimulationConfig
from bess_model.core.pipeline import SimulationContext, run_pipeline
from bess_model.profile_templates import (
    build_load_profile_frame,
    compute_profile_compliance_tables,
    compute_profile_summary_metrics,
    get_tender_profile,
)
from bess_model.web.services import save_config_form


def test_flat_profile_mode_remains_backward_compatible() -> None:
    config = SimulationConfig.from_dict(_base_config_payload(load={"output_profile_kw": 400.0, "aux_consumption_kw": 20.0}))

    assert config.load.profile_mode == "flat"
    assert config.load.output_profile_kw == 400.0
    assert config.load.profile_template_id is None
    assert config.load.contracted_capacity_mw is None
    assert not config.load.uses_template_profile


def test_template_mode_requires_template_id_and_contracted_capacity() -> None:
    with pytest.raises(ValueError, match="profile_template_id"):
        SimulationConfig.from_dict(
            _base_config_payload(load={"profile_mode": "template", "aux_consumption_kw": 0.0})
        )

    with pytest.raises(ValueError, match="contracted_capacity_mw"):
        SimulationConfig.from_dict(
            _base_config_payload(
                load={
                    "profile_mode": "template",
                    "profile_template_id": "seci_fdre_v_amendment_03",
                    "aux_consumption_kw": 0.0,
                }
            )
        )


def test_fdre_v_profile_expansion_scales_and_repeats_daily() -> None:
    load = LoadConfig(
        profile_mode="template",
        profile_template_id="seci_fdre_v_amendment_03",
        contracted_capacity_mw=400.0,
        aux_consumption_kw=25.0,
    )
    timestamps = pl.Series(
        "timestamp",
        [
            datetime(2025, 1, 1, 0, 0),
            datetime(2025, 1, 1, 0, 59),
            datetime(2025, 1, 2, 0, 0),
            datetime(2025, 1, 1, 6, 0),
        ],
        dtype=pl.Datetime,
    )

    frame = build_load_profile_frame(timestamps, load)

    assert frame[0, "output_profile_kw"] == pytest.approx(133_200.0)
    assert frame[1, "output_profile_kw"] == pytest.approx(133_200.0)
    assert frame[2, "output_profile_kw"] == pytest.approx(133_200.0)
    assert frame[3, "output_profile_kw"] == pytest.approx(268_800.0)
    assert frame[0, "aux_consumption_kw"] == pytest.approx(25.0)
    assert frame[0, "total_consumption_kw"] == pytest.approx(133_225.0)


def test_fdre_ii_profile_expansion_scales_quarter_hour_blocks() -> None:
    load = LoadConfig(
        profile_mode="template",
        profile_template_id="seci_fdre_ii_revised_annexure_b",
        contracted_capacity_mw=300.0,
        aux_consumption_kw=0.0,
    )
    timestamps = pl.Series(
        "timestamp",
        [
            datetime(2025, 1, 1, 0, 0),
            datetime(2025, 1, 1, 0, 14),
            datetime(2025, 4, 1, 6, 0),
            datetime(2025, 4, 1, 6, 14),
        ],
        dtype=pl.Datetime,
    )

    frame = build_load_profile_frame(timestamps, load)

    assert frame[0, "output_profile_kw"] == pytest.approx(130_000.0)
    assert frame[1, "output_profile_kw"] == pytest.approx(130_000.0)
    assert frame[2, "output_profile_kw"] == pytest.approx(227_400.0)
    assert frame[3, "output_profile_kw"] == pytest.approx(227_400.0)


def test_template_profile_handles_leap_year_month_boundaries() -> None:
    load = LoadConfig(
        profile_mode="template",
        profile_template_id="seci_fdre_v_amendment_03",
        contracted_capacity_mw=100.0,
        aux_consumption_kw=0.0,
    )
    timestamps = pl.Series(
        "timestamp",
        [
            datetime(2024, 2, 29, 0, 0),
            datetime(2024, 2, 29, 23, 59),
            datetime(2024, 3, 1, 0, 0),
        ],
        dtype=pl.Datetime,
    )

    frame = build_load_profile_frame(timestamps, load)

    assert frame["output_profile_kw"].null_count() == 0
    assert frame[0, "output_profile_kw"] == pytest.approx(36_800.0)
    assert frame[2, "output_profile_kw"] == pytest.approx(45_700.0)


@pytest.mark.parametrize(
    ("template_id", "capacity_mw"),
    [
        ("seci_fdre_v_amendment_03", 400.0),
        ("seci_fdre_ii_revised_annexure_b", 300.0),
    ],
)
def test_annual_profile_target_matches_tender_multiplier(template_id: str, capacity_mw: float) -> None:
    timestamps = pl.datetime_range(
        datetime(2025, 1, 1, 0, 0),
        datetime(2025, 12, 31, 23, 59),
        interval="1m",
        eager=True,
    )
    load = LoadConfig(
        profile_mode="template",
        profile_template_id=template_id,
        contracted_capacity_mw=capacity_mw,
        aux_consumption_kw=0.0,
    )

    frame = build_load_profile_frame(timestamps, load)
    compliance_df = pl.DataFrame({"timestamp": timestamps}).hstack(frame).with_columns(
        grid_buy_kw=pl.lit(0.0)
    )
    block_df, monthly_df = compute_profile_compliance_tables(compliance_df, load)
    summary = compute_profile_summary_metrics(load, monthly_df, block_df)
    template = get_tender_profile(template_id)

    assert summary["annual_profile_target_kwh"] == pytest.approx(
        template.annual_energy_per_mw_kwh * capacity_mw,
        abs=100.0,
    )


def test_compliance_uses_block_level_arithmetic_mean_dfr() -> None:
    load = LoadConfig(
        profile_mode="template",
        profile_template_id="seci_fdre_v_amendment_03",
        contracted_capacity_mw=100.0,
        aux_consumption_kw=0.0,
    )
    df = pl.DataFrame(
        {
            "timestamp": pl.datetime_range(
                datetime(2025, 1, 1, 0, 0),
                datetime(2025, 1, 1, 1, 59),
                interval="1m",
                eager=True,
            ),
            "output_profile_kw": [100.0] * 60 + [1000.0] * 60,
            "total_consumption_kw": [100.0] * 60 + [1000.0] * 60,
            "grid_buy_kw": [0.0] * 60 + [500.0] * 60,
        }
    )

    block_df, monthly_df = compute_profile_compliance_tables(df, load)
    summary = compute_profile_summary_metrics(load, monthly_df, block_df)

    assert block_df is not None
    assert monthly_df is not None
    assert block_df.height == 2
    assert block_df[0, "block_dfr"] == pytest.approx(1.0)
    assert block_df[1, "block_dfr"] == pytest.approx(0.5)
    assert monthly_df[0, "monthly_dfr"] == pytest.approx(0.75)
    assert monthly_df[0, "required_dfr_pct"] == pytest.approx(75.0)
    assert bool(monthly_df[0, "dfr_ok"]) is True
    assert summary["required_dfr_pct"] == pytest.approx(75.0)
    assert summary["min_monthly_dfr_pct"] == pytest.approx(75.0)
    assert summary["months_below_dfr_threshold"] == 0


def test_web_form_round_trip_preserves_template_load_fields(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "plant_name: tender_web",
                f"output_dir: {tmp_path / 'output'}",
                "data:",
                "  solar_enabled: true",
                "  wind_enabled: true",
                "load:",
                "  profile_mode: flat",
                "  output_profile_kw: 400.0",
                "  aux_consumption_kw: 20.0",
                "grid:",
                "  export_limit_kw: 100.0",
                "  import_limit_kw:",
                "battery:",
                "  capacity_kwh: 1000.0",
                "  max_charge_kw: 200.0",
                "  max_discharge_kw: 200.0",
                "  charge_efficiency: 1.0",
                "  discharge_efficiency: 1.0",
                "  initial_soc_kwh: 0.0",
            ]
        ),
        encoding="utf-8",
    )

    config = save_config_form(
        config_path,
        {
            "plant_name": "tender_web",
            "output_dir": str(tmp_path / "output"),
            "data.solar_enabled": "true",
            "data.wind_enabled": "true",
            "grid.export_limit_kw": "100.0",
            "grid.import_limit_kw": "",
            "load.profile_mode": "template",
            "load.profile_template_id": "seci_fdre_v_amendment_03",
            "load.contracted_capacity_mw": "400",
            "load.output_profile_kw": "",
            "load.aux_consumption_kw": "20.0",
            "battery.capacity_kwh": "1000.0",
            "battery.max_charge_kw": "200.0",
            "battery.max_discharge_kw": "200.0",
            "battery.charge_efficiency": "1.0",
            "battery.discharge_efficiency": "1.0",
            "battery.initial_soc_kwh": "0.0",
        },
    )

    assert config.load.profile_mode == "template"
    assert config.load.profile_template_id == "seci_fdre_v_amendment_03"
    assert config.load.contracted_capacity_mw == pytest.approx(400.0)
    assert config.load.output_profile_kw is None


def test_output_profile_is_constant_in_flat_mode_and_time_varying_in_template_mode() -> None:
    timestamps = [
        datetime(2025, 1, 1, 0, 0),
        datetime(2025, 1, 1, 6, 0),
    ]
    base_df = pl.DataFrame(
        {
            "timestamp": timestamps,
            "solar_kw": [0.0, 0.0],
            "wind_kw": [0.0, 0.0],
            "total_generation_kw": [0.0, 0.0],
        }
    )

    flat_config = SimulationConfig.from_dict(
        _base_config_payload(load={"output_profile_kw": 400.0, "aux_consumption_kw": 0.0})
    )
    template_config = SimulationConfig.from_dict(
        _base_config_payload(
            load={
                "profile_mode": "template",
                "profile_template_id": "seci_fdre_v_amendment_03",
                "contracted_capacity_mw": 400.0,
                "aux_consumption_kw": 0.0,
            }
        )
    )

    flat_result = run_pipeline(base_df, SimulationContext(config=flat_config, logger=logging.getLogger("flat")))
    template_result = run_pipeline(
        base_df,
        SimulationContext(config=template_config, logger=logging.getLogger("template")),
    )

    assert flat_result["output_profile_kw"].n_unique() == 1
    assert template_result["output_profile_kw"].n_unique() == 2
    assert template_result[0, "output_profile_kw"] == pytest.approx(133_200.0)
    assert template_result[1, "output_profile_kw"] == pytest.approx(268_800.0)


def _base_config_payload(*, load: dict[str, object]) -> dict[str, object]:
    return {
        "plant_name": "tender_case",
        "output_dir": "output",
        "data": {"solar_path": "unused.csv", "wind_path": "unused.csv"},
        "preprocessing": {"frequency": "1m", "gap_fill": "linear_interpolate", "max_interpolation_gap_minutes": 15, "align_to_full_year": False},
        "grid": {"export_limit_kw": 100.0, "import_limit_kw": None},
        "load": load,
        "battery": {
            "capacity_kwh": 1000.0,
            "max_charge_kw": 200.0,
            "max_discharge_kw": 200.0,
            "charge_efficiency": 1.0,
            "discharge_efficiency": 1.0,
            "initial_soc_kwh": 0.0,
        },
    }
