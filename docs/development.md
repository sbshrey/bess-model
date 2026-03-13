# Development

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .[dev]
```

## Running

### CLI Simulation

```bash
bess-model --config config.example.yaml
bess-model --config config.example.yaml --dump-sections
bess-model --config config.example.yaml --log-level DEBUG
```

Or:

```bash
python main.py --config config.example.yaml --mode simulate
python main.py --config config.example.yaml --dump-sections
```

### Web App (Development)

```bash
bess-model-web --config config.example.yaml --host 127.0.0.1 --port 5000
```

### Production (Gunicorn)

```bash
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
```

`wsgi.py` loads the app via `create_app()`; use `BESS_CONFIG_PATH` and `PORT` env vars.

### Health Check

`GET /health` returns `{"status": "ok"}` and 200. Use for load balancer health checks and monitoring.

## Testing

```bash
pytest
pytest -v
pytest tests/test_section_outputs.py
```

### Test Layout

| File | Scope |
|------|-------|
| `tests/test_loaders.py` | CSV loaders |
| `tests/test_preprocessing.py` | Alignment, gap fill |
| `tests/test_section_outputs.py` | Section accounting logic |
| `tests/test_pipeline.py` | Pipeline, summary metrics |
| `tests/test_integration.py` | End-to-end runs |
| `tests/test_web_app.py` | Routes, services |

## Project Layout (pyproject.toml)

- **Scripts**: `bess-model`, `bess-model-web`
- **Dependencies**: Flask, gunicorn, numba, numpy, polars, PyYAML
- **Dev**: pytest
- **Package data**: `bess_model.web` includes `templates/*.html`, `static/*.css`, `static/*.js`

## Deployment (Render)

`render.yaml` defines a web service. The app runs with Gunicorn; `PORT` is provided by Render.
