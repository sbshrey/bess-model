# BESS Model Documentation

Comprehensive documentation for the BESS (Battery Energy Storage System) Model framework—a Python tool for simulating and sizing battery storage from minute-level solar and wind generation data.

## Documentation Index

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | System design, directory structure, and data flow |
| [Configuration](configuration.md) | YAML config reference and dataclass models |
| [Simulation](simulation.md) | Section accounting logic and output columns |
| [Web UI](web-ui.md) | Flask dashboard, templates, and frontend behavior |
| [API Reference](api-reference.md) | HTTP routes and JSON responses |
| [Development](development.md) | Setup, testing, and deployment |

## Quick Links

- **CLI**: `bess-model --config config.example.yaml` or `python main.py --config config.example.yaml`
- **Web**: `bess-model-web --config config.example.yaml` → http://127.0.0.1:5000
- **Config**: `config.example.yaml` in project root

## Key Features

- Reads mismatched solar and wind CSV files, aligns to 1-minute grid
- Section-based accounting simulation with kWh constraints
- Battery charge/discharge, SOC, degradation, C-rate loss tables
- Minute-level Parquet + summary CSV outputs
- Web dashboard: config editing, run simulation, chart previews, CSV editing with recalculation
