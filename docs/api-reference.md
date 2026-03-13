# API Reference

## HTTP Routes

### Dashboard

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | `/` | `dashboard` | Main dashboard with config, outputs, preview, charts |

### Configuration

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| POST | `/config/save` | `save_config` | Save config from Raw YAML text (`config_text`) |
| POST | `/config/save-form` | `save_config_form_route` | Save config from visual form fields |

### Simulation

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| POST | `/run/simulate` | `run_simulation` | Save YAML + run simulation |
| POST | `/run/simulate-form` | `run_simulation_form` | Save form + run simulation |

### Files

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | `/files/<path:relative_path>` | `download_file` | Download output file as attachment |

### Editor

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | `/edit/<path:relative_path>` | `edit_csv` | Render CSV editor |
| POST | `/edit/<path:relative_path>` | `edit_csv` | Save edits; optional `recalculate=1` |

### API (JSON)

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | `/api/render-charts/<path:relative_path>` | `api_render_charts` | Return chart data for a CSV file |

#### Query Parameters

- `start_date` (optional): ISO date or datetime
- `end_date` (optional): ISO date or datetime

#### Response

```json
[
  {
    "title": "SOC Profile",
    "subtitle": "Battery SOC over time",
    "svg": "<svg>...</svg>"
  },
  ...
]
```

On error: `{"error": "message"}` with 404 or 500.

## Services (bess_model.web.services)

| Function | Purpose |
|----------|---------|
| `load_config_text` | Read config YAML as string |
| `save_config_text` | Validate and save YAML |
| `save_config_form` | Update nested YAML from flat form keys |
| `run_simulation_from_frontend` | Run simulation, write outputs |
| `run_simulation_from_form_frontend` | Save form, then run |
| `list_output_files` | List output dir files |
| `choose_default_output_file` | Pick default for dashboard |
| `resolve_output_file` | Resolve relative path safely |
| `load_csv_page` | Paginated CSV rows |
| `save_csv_page_edits` | Persist edited cells |
| `load_filtered_csv` | CSV with date filter |
| `recalculate_from_edited_output` | Re-run pipeline from edited aligned input |
| `load_metric_cards` | Build KPI cards from summary |
| `build_chart_svg` | Single SVG chart |
| `build_chart_cards` | Multiple ChartCard objects |
| `build_preview_table` | Preview table for dashboard |
