"""Flask application for managing the BESS model from the browser."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence
import math

from flask import Flask, flash, redirect, render_template, request, send_file, url_for

from bess_model.config import SimulationConfig
from bess_model.web.services import (
    build_chart_cards,
    build_chart_svg,
    build_preview_table,
    choose_default_output_file,
    list_output_files,
    load_metric_cards,
    load_config_text,
    load_csv_page,
    load_filtered_csv,
    normalize_date_input,
    recalculate_from_edited_output,
    resolve_output_file,
    run_simulation_from_frontend,
    run_sizing_from_frontend,
    save_config_text,
    save_csv_page_edits,
)


def create_app(config_path: str | Path = "config.example.yaml") -> Flask:
    """Create the Flask app instance."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = "bess-model-dev"
    app.config["CONFIG_PATH"] = str(Path(config_path).resolve())

    def generate_page_window(current_page: int, total_pages: int, max_window: int = 7) -> list[int | None]:
        """Generate a list of page numbers and None for ellipses."""
        if total_pages <= max_window:
            return list(range(1, total_pages + 1))
        
        # We always want the first, last, and current page.
        # Figure out the layout like: 1 ... 4 5 6 ... 100
        window = []
        if current_page < 5:
            window.extend(range(1, 6))
            window.append(None)
            window.append(total_pages)
        elif current_page > total_pages - 4:
            window.append(1)
            window.append(None)
            window.extend(range(total_pages - 4, total_pages + 1))
        else:
            window.append(1)
            window.append(None)
            window.extend(range(current_page - 1, current_page + 2))
            window.append(None)
            window.append(total_pages)
        return window

    app.jinja_env.globals["generate_page_window"] = generate_page_window

    @app.get("/")
    def dashboard():
        config_file = Path(app.config["CONFIG_PATH"])
        config_text = load_config_text(config_file)
        config = SimulationConfig.from_yaml(config_file)
        outputs = list_output_files(config)
        selected = request.args.get("file")
        start_date = normalize_date_input(request.args.get("start_date"))
        end_date = normalize_date_input(request.args.get("end_date"))
        if not selected:
            selected = choose_default_output_file(config, outputs)
        preview_columns: list[str] = []
        preview_rows: list[dict[str, object]] = []
        chart_svg = None
        chart_cards = []
        date_filter = None
        metric_cards = load_metric_cards(config)
        
        page = int(request.args.get("page", "1"))
        page_size = int(request.args.get("page_size", "20"))
        total_rows = 0
        total_pages = 1

        if selected:
            selected_path = resolve_output_file(config, selected)
            if selected_path.suffix == ".csv":
                filtered_csv = load_filtered_csv(selected_path, start_date=start_date, end_date=end_date)
                total_rows = filtered_csv.df.height
                total_pages = max(1, math.ceil(total_rows / page_size))
                page = max(1, min(page, total_pages))
                
                start_idx = (page - 1) * page_size
                paginated_df = filtered_csv.df.slice(start_idx, page_size)

                preview_columns, preview_rows = build_preview_table(df=paginated_df, limit=page_size)
                chart_svg = build_chart_svg(df=filtered_csv.df)
                chart_cards = build_chart_cards(df=filtered_csv.df)
                date_filter = filtered_csv.date_filter

        return render_template(
            "dashboard.html",
            config_path=str(config_file),
            config_text=config_text,
            outputs=outputs,
            selected_file=selected,
            metric_cards=metric_cards,
            plant_name=config.plant_name,
            output_dir=config.output_dir,
            preview_columns=preview_columns,
            preview_rows=preview_rows,
            chart_svg=chart_svg,
            chart_cards=chart_cards,
            date_filter=date_filter,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            total_rows=total_rows,
        )

    @app.post("/config/save")
    def save_config():
        config_file = Path(app.config["CONFIG_PATH"])
        try:
            save_config_text(config_file, request.form["config_text"])
            flash("Configuration saved.", "success")
        except Exception as exc:  # pragma: no cover - surfaced in UI only.
            flash(f"Failed to save config: {exc}", "error")
        return redirect(url_for("dashboard"))

    @app.post("/run/simulate")
    def run_simulation():
        config_file = Path(app.config["CONFIG_PATH"])
        try:
            save_config_text(config_file, request.form["config_text"])
            config, result, _ = run_simulation_from_frontend(config_file)
            flash(
                f"Simulation completed for {config.plant_name}. "
                f"Rows: {result.summary_metrics['rows']}.",
                "success",
            )
        except Exception as exc:  # pragma: no cover - surfaced in UI only.
            flash(f"Simulation failed: {exc}", "error")
        return redirect(url_for("dashboard"))

    @app.post("/run/size")
    def run_size():
        config_file = Path(app.config["CONFIG_PATH"])
        try:
            save_config_text(config_file, request.form["config_text"])
            config, result_path = run_sizing_from_frontend(config_file)
            flash(f"Sizing completed for {config.plant_name}: {result_path.name}", "success")
        except Exception as exc:  # pragma: no cover - surfaced in UI only.
            flash(f"Sizing failed: {exc}", "error")
        return redirect(url_for("dashboard"))

    @app.get("/files/<path:relative_path>")
    def download_file(relative_path: str):
        config = SimulationConfig.from_yaml(app.config["CONFIG_PATH"])
        path = resolve_output_file(config, relative_path)
        return send_file(path, as_attachment=True)

    @app.route("/edit/<path:relative_path>", methods=["GET", "POST"])
    def edit_csv(relative_path: str):
        config = SimulationConfig.from_yaml(app.config["CONFIG_PATH"])
        path = resolve_output_file(config, relative_path)
        if path.suffix.lower() != ".csv":
            flash("Only CSV files can be edited in the browser.", "error")
            return redirect(url_for("dashboard", file=relative_path))

        page = int(request.values.get("page", "1"))
        page_size = int(request.values.get("page_size", "25"))
        start_date = normalize_date_input(request.values.get("start_date"))
        end_date = normalize_date_input(request.values.get("end_date"))

        if request.method == "POST":
            try:
                save_csv_page_edits(path, page, page_size, request.form.to_dict())
                if request.form.get("recalculate") == "1":
                    recalculate_from_edited_output(config, relative_path)
                    flash("CSV changes saved and downstream outputs recalculated.", "success")
                else:
                    flash("CSV changes saved.", "success")
            except Exception as exc:  # pragma: no cover - surfaced in UI only.
                flash(f"Failed to save CSV changes: {exc}", "error")
            return redirect(
                url_for(
                    "edit_csv",
                    relative_path=relative_path,
                    page=page,
                    page_size=page_size,
                    start_date=start_date,
                    end_date=end_date,
                )
            )

        filtered_csv = load_filtered_csv(path, start_date=start_date, end_date=end_date)
        csv_page = load_csv_page(path, page, page_size, start_date=start_date, end_date=end_date)
        chart_svg = build_chart_svg(df=filtered_csv.df)
        chart_cards = build_chart_cards(df=filtered_csv.df)
        return render_template(
            "editor.html",
            relative_path=relative_path,
            file_name=path.name,
            csv_page=csv_page,
            chart_svg=chart_svg,
            chart_cards=chart_cards,
            date_filter=filtered_csv.date_filter,
        )

    return app


def main(argv: Sequence[str] | None = None) -> int:
    """Run the development web server."""
    parser = argparse.ArgumentParser(description="BESS web frontend")
    parser.add_argument("--config", default="config.example.yaml", help="Path to the YAML config file")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind the web server")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind the web server")
    args = parser.parse_args(argv)

    app = create_app(args.config)
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
