# Tender-Driven Output Profile Update

## Summary
Replace the current flat `load.output_profile_kw` model with a backward-compatible tender profile system that supports both attached profile families and adds compliance reporting.

Use these source rules as the canonical inputs:
- FDRE-V latest profile: [RfS dated November 28, 2023](https://www.seci.co.in/Upload/New/638367927613448418.pdf) plus [Amendment-03 dated June 3, 2024](https://www.seci.co.in/Upload/Tender/SECI000126-979316-Amendment-03-SECI-FDRE-V-finalupload.pdf), which changes FDRE-V to 24 hourly blocks, lowers monthly DFR to `75%`, and changes annual energy to `5,589,988 × C` kWh.
- FDRE-II profile: [Revised Annexure-B uploaded August 21, 2023](https://www.seci.co.in/Upload/Tender/SECI000116-2493087-RevisedAnnexure-BFDRE-II.pdf), read together with the [FDRE-II RfS dated July 31, 2023](https://www.seci.co.in/Upload/Tender/SECI000116-1201581-RfSfor1500MW-PunjabandMP-FDRE-II-finalupload.pdf) and [Amendment-01 dated December 4, 2023](https://www.seci.co.in/Upload/Tender/SECI000116-6407450-Amendment-01-SECI-FDRE-II-finalupload.pdf), which keeps 96 quarter-hour blocks, monthly DFR `90%`, and annual energy `5,759,734 × C` kWh.

## Key Changes
- Extend `load` config so runs can be either:
  - `flat` mode: current behavior, using `output_profile_kw`.
  - `template` mode: document-driven demand profile.
- Add these config fields:
  - `load.profile_mode`: `flat | template`, default `flat`
  - `load.profile_template_id`: `seci_fdre_v_amendment_03 | seci_fdre_ii_revised_annexure_b`
  - `load.contracted_capacity_mw`: required in `template` mode
  - Keep `load.output_profile_kw` for `flat` mode only
- Store tender profiles as packaged static assets plus metadata, not hardcoded arrays in simulation code.
  - Asset shape: one row per tender block, month columns `jan..dec`
  - Metadata per template: `base_capacity_mw`, `block_minutes`, `required_dfr`, `annual_energy_per_mw_kwh`, `source_doc`
- Add a profile-expansion step before section accounting:
  - Expand the tender profile over the aligned simulation year
  - Repeat each representative-day month profile for every day in that month
  - Scale by `contracted_capacity_mw / base_capacity_mw`
  - Convert MW tender values to the model’s `output_profile_kw`
  - For FDRE-V, each hourly block is constant across its 60 one-minute rows
  - For FDRE-II, each 15-minute block is constant across its 15 one-minute rows
- Keep `aux_consumption_kw` separate from the tender profile.
  - `total_consumption_kw = output_profile_kw + aux_consumption_kw`
  - Compliance metrics are computed against the tender `output_profile_kw` only
- Add compliance outputs:
  - Block-level compliance table grouped at the tender block cadence
  - Monthly compliance table with `monthly_dfr`, `required_dfr`, `dfr_ok`, target/supplied energy
  - Summary metrics extended with `profile_template_id`, `required_dfr_pct`, `min_monthly_dfr_pct`, `months_below_dfr_threshold`, `annual_energy_target_kwh`, `annual_profile_target_kwh`, `annual_profile_supplied_kwh`, and `annual_energy_gap_kwh`
- Define RPD supply used for DFR as project-supplied power allocated to the tender profile before aux load:
  - `project_supply_total_kw = total_consumption_kw - grid_buy_kw`
  - `project_supply_to_profile_kw = min(output_profile_kw, max(project_supply_total_kw, 0))`
  - Block DFR = `min(block_supply / block_target, 1)`
  - Monthly DFR = arithmetic mean of block DFRs for that calendar month
- Surface the feature in the app:
  - Update YAML/config parsing and docs
  - Update the web config form to choose `flat` vs `template`, template id, and contracted capacity
  - Update output metadata so `03_output_profile.csv` reflects time-varying tender output when template mode is active
  - Expose the monthly compliance CSV in the output/dashboard area

## Public Interfaces
- YAML additions under `load`:
  - `profile_mode`
  - `profile_template_id`
  - `contracted_capacity_mw`
- New output artifacts:
  - `{plant}_profile_compliance_blocks.csv`
  - `{plant}_profile_compliance_monthly.csv`
- Extended summary CSV fields for tender compliance.
- No penalty calculation in v1. Only pass/fail and gap metrics.

## Test Plan
- Config tests:
  - Flat-mode configs remain valid and unchanged.
  - Template mode requires both `profile_template_id` and `contracted_capacity_mw`.
- Profile expansion tests:
  - FDRE-V January `00:00-01:00` scales from `333/1000 × A` MW and repeats for all 60 minutes.
  - FDRE-II January `00:00-00:15` scales from `650/1500 × A` MW and repeats for all 15 minutes.
  - Representative-day profiles repeat for every day in the month.
  - Leap-year timelines still fill correctly month by month.
- Compliance tests:
  - DFR is computed at tender block granularity, not by raw minute averaging.
  - FDRE-V uses `75%` required monthly DFR.
  - FDRE-II uses `90%` required monthly DFR.
  - Annual profile target from the expanded table matches the tender annual multiplier within a small tolerance.
- Regression tests:
  - Existing flat-profile pipeline tests continue to pass.
  - Web config round-trip preserves the new load fields.
  - `03_output_profile.csv` stays constant in flat mode and becomes time-varying in template mode.

## Assumptions
- Backward compatibility is mandatory, so `flat` remains the default mode.
- FDRE-V uses the latest amended profile from June 3, 2024, not the older 96-block version from November 28, 2023.
- FDRE-II compliance uses the attached revised demand profile together with the official FDRE-II RfS/amendment values for DFR and annual energy.
- Aux load remains an internal plant load and does not reduce tender-profile compliance if the profile itself is fully met.
- Penalty formulas and monetary settlement are explicitly out of scope for this update.
