# Web UI

## Overview

The web application is a Flask/Jinja2 dashboard for configuring, running, and inspecting BESS simulations. Start with:

```bash
bess-model-web --config config.example.yaml --host 127.0.0.1 --port 5000
```

Then open http://127.0.0.1:5000.

## Pages

### Dashboard (`/`)

- **Sidebar**: Workspace info, config file path, output dir
- **Configuration panel**:
  - **Visual Form**: Fields for plant name, data paths, preprocessing, grid, load, battery (including charge/discharge loss tables)
  - **Raw YAML**: Edit full config YAML
  - **Save Config** / **Run Simulation** buttons
- **Output file list**: Select a CSV/Parquet from output dir
- **Date filter**: Optional start/end date for preview
- **Metric cards**: Net grid impact, cycles, SOH (from summary when available)
- **Charts**: SOC, grid buy/sell, battery state, etc. (auto-selected from CSV columns)
- **Data preview table**: Paginated CSV preview

### Editor (`/edit/<path>`)

- Edit a section CSV with pagination
- Date filter for preview
- Optional **Recalculate** to run pipeline from edited aligned input
- Charts for the selected output

## Templates

| Template | Role |
|----------|------|
| `base.html` | Layout, header, flash messages, chart modal |
| `dashboard.html` | Config form, file list, metrics, charts, preview table |
| `editor.html` | CSV edit form, charts |

## Chart Modal

- **Expand** button on each chart card opens a modal
- **Drag to zoom**: Draw a rectangle to zoom into a time range; chart re-renders from backend
- **Reset Zoom**: Restore full range (only shown when zoomed)
- **Close**: Close modal

## Frontend (app.js)

- **Sidebar toggle**: Collapse/expand, persisted in localStorage
- **Sidebar resizer**: Drag to resize
- **Chart modal**: Open, close, scale (legacy)
- **Interactive charts**: Brush zoom, Reset Zoom, API fetch for re-render
- **Progress bar**: Shows during simulation run

## Frontend (app.css)

- CSS variables for colors, spacing
- Layout: topbar, flash stack, sidebar, content panels
- Form styling: input-field, button-row, stacked-form
- Chart styling: chart-wrap, chart-brush, reset-zoom-btn, chart-modal
- Responsive breakpoints
