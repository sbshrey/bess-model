# Architecture

## Overview

BESS Model is a Python framework for simulating Battery Energy Storage Systems from minute-level solar and wind generation data. It uses **Polars** for DataFrame handling and **NumPy** for the core simulation loop. The web UI is built with **Flask** and **Jinja2**.

## Directory Structure

```
bess-model/
├── bess_model/                 # Main Python package
│   ├── __init__.py
│   ├── main.py                 # CLI entrypoint (simulate)
│   ├── config.py               # Configuration dataclasses
│   ├── results.py              # SimulationResult model
│   ├── core/                   # Pipeline orchestration
│   │   ├── __init__.py
│   │   └── pipeline.py         # simulate_system, run_pipeline, write outputs
│   ├── data/                   # Input loading and preprocessing
│   │   ├── __init__.py
│   │   ├── loaders.py          # Load solar/wind CSV
│   │   └── preprocessing.py    # Align to 1-minute grid, gap fill
│   ├── flows/                  # Simulation logic
│   │   ├── __init__.py
│   │   └── section_outputs.py  # Section accounting stage, CSV exports
│   ├── battery/                # Placeholder (logic in flows)
│   │   └── __init__.py
│   └── web/                    # Flask web application
│       ├── __init__.py
│       ├── app.py              # Routes, create_app
│       ├── services.py         # Business logic for UI
│       ├── templates/          # Jinja2 HTML
│       │   ├── base.html
│       │   ├── dashboard.html
│       │   └── editor.html
│       └── static/
│           ├── app.css
│           └── app.js
├── tests/                      # pytest tests
├── docs/                       # This documentation
├── main.py                     # Thin wrapper for bess_model.main
├── wsgi.py                     # Gunicorn entry for production
├── config.example.yaml
├── pyproject.toml
└── render.yaml                 # Render.com deployment
```

## Entry Points

| Entry | Module | Purpose |
|-------|--------|---------|
| `bess-model` | `bess_model.main:main` | Run simulation from config |
| `bess-model-web` | `bess_model.web.app:main` | Start Flask dev server (port 5000) |
| `wsgi.py` | — | Production WSGI app for Gunicorn |

## Data Flow

```
┌─────────────────┐     ┌─────────────────┐
│ Solar CSV       │     │ Wind CSV        │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
         ┌───────────────────────┐
         │ data/loaders.py       │  load_generation_data
         │ Normalize timestamp   │
         │ and power columns     │
         └───────────┬───────────┘
                     ▼
         ┌───────────────────────┐
         │ preprocessing.py      │  align_generation_to_minute
         │ Resample to 1m        │
         │ Gap fill / interpolate│
         └───────────┬───────────┘
                     ▼
         Aligned DataFrame (timestamp, solar_kw, wind_kw, total_generation_kw)
                     │
                     ▼
         ┌───────────────────────┐
         │ core/pipeline.py      │  simulate_system
         │ run_pipeline(stages)  │
         └───────────┬───────────┘
                     ▼
         ┌───────────────────────┐
         │ flows/section_outputs │  section_accounting_stage
         │ Minute-by-minute      │
         │ BESS simulation       │
         └───────────┬───────────┘
                     ▼
         Full DataFrame (all section columns)
                     │
                     ▼
         ┌───────────────────────┐
         │ compute_summary_      │
         │ metrics               │
         │ write_simulation_     │
         │ outputs               │
         └───────────┬───────────┘
                     ▼
         Parquet + Summary CSV + Section CSVs (optional)
```

## Pipeline Stages

The simulation uses a staged pipeline defined in `core/pipeline.py`:

- **FLOW_STAGES**: List of `StageFn` (function that takes `(df, context)` → `pl.DataFrame`)
- Currently: `[section_accounting_stage]` — a single stage that appends all section columns
- `SimulationContext` holds `config` and `logger`; stages can use `context.validate_balance()` for identity checks

## Key Dependencies

| Package | Role |
|---------|------|
| Polars | DataFrames, CSV/Parquet I/O |
| NumPy | Simulation arrays, C-rate/loss math |
| PyYAML | Config parsing |
| Flask | Web server, templates, routes |
| Gunicorn | Production WSGI server |
