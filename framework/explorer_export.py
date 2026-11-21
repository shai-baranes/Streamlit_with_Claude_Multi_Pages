"""Build the standalone Engineering Explorer on an explicit export request."""
from pathlib import Path

import pandas as pd
from pandas.api.types import is_integer_dtype, is_unsigned_integer_dtype

from framework.analysis import interpret_chart_x
from framework.config import MAX_INTERACTIVE_EXPORT_MB, MAX_POINTS, MAX_PREVIEW
from framework.export_payload import InteractiveExportTooLarge, PayloadWriter, json_cell


def _datetime_cell(value):
    if pd.isna(value):
        return None
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("UTC").tz_localize(None)
    # Fixed width preserves chronological order at sub-millisecond precision.
    return stamp.isoformat(timespec="nanoseconds")


def explorer_payload(frame, numeric_columns, settings, limit):
    columns = list(frame)
    settings = settings.copy()
    if settings.get("bounds") and settings["xtype"] == "Datetime":
        settings["bounds"] = [_datetime_cell(value) for value in settings["bounds"]]
    writer = PayloadWriter(limit)
    writer.write('{"schema":')
    writer.value([
        {
            "name": name,
            "numeric": name in numeric_columns,
            "integer": is_integer_dtype(dtype),
            "unsigned": is_unsigned_integer_dtype(dtype),
            "date": pd.api.types.is_datetime64_any_dtype(dtype),
        }
        for name, dtype in frame.dtypes.items()
    ])
    writer.write(',"settings":')
    writer.value(settings)
    writer.write(',"preview":')
    writer.value(MAX_PREVIEW)
    writer.write(',"points":')
    writer.value(MAX_POINTS)
    writer.write(',"original":[')
    for index, name in enumerate(columns):
        if index:
            writer.write(",")
        writer.array(map(json_cell, frame[name]))
    writer.write('],"converted":[')
    if numeric_columns:
        for index, name in enumerate(columns):
            if index:
                writer.write(",")
            writer.write('{"Numeric":')
            # Numeric pandas columns can share the original array for Numeric X.
            if name in numeric_columns:
                writer.value(None)
            else:
                writer.array(map(json_cell, interpret_chart_x(frame[name], "Numeric")))
            writer.write(',"Datetime":')
            writer.array(map(_datetime_cell, interpret_chart_x(frame[name], "Datetime")))
            writer.write("}")
    writer.write("]}")
    return writer.finish()


def export_explorer(report, frame, numeric_columns, settings):
    try:
        report.component(
            "renderExplorer",
            lambda: explorer_payload(frame, numeric_columns, settings, MAX_INTERACTIVE_EXPORT_MB * 1024**2),
            html="""
            <h2>Grouping for statistics</h2>
            <div data-no-numeric hidden>No numeric fields are available for statistics or plotting.</div>
            <div data-explorer-controls hidden>
              <div class="explorer-controls">
                <div data-group></div>
                <label>Value field<select data-metric></select></label>
                <label>Aggregation<select data-operation></select></label>
              </div>
              <p data-group-message role="status"></p>
              <div class="explorer-results" data-results></div>
              <h2>Dynamic chart</h2>
              <div class="explorer-controls">
                <label>Time - X field<select data-x></select></label>
                <label>X interpretation<select data-interpretation></select></label>
                <label>Chart type<select data-kind></select></label>
                <div data-y></div>
              </div>
              <fieldset data-range hidden>
                <legend>Chart X range</legend>
                <div class="explorer-controls">
                  <label>Minimum<input data-low></label>
                  <label>Maximum<input data-high></label>
                  <button type="button" data-reset-range>Reset range</button>
                </div>
                <small data-range-note></small>
              </fieldset>
              <p data-chart-message role="status"></p>
              <div class="explorer-chart" data-chart></div>
            </div>
            """,
            css="""
            .explorer-controls {display:flex;flex-wrap:wrap;align-items:flex-start;gap:.75rem 1rem}
            .explorer-controls > * {flex:1 1 12rem;min-width:0}
            .explorer-controls :is(select,input) {display:block;width:100%;font:inherit}
            .explorer-controls select {text-overflow:ellipsis}
            .explorer-controls :is(select,input,button) {padding:.28rem .4rem}
            .explorer-controls button {font:inherit}
            .explorer-fields {margin:.4rem 0;padding-left:1.5rem;overflow-wrap:anywhere}
            .explorer-fields li {margin:.2rem 0}
            .explorer-fields button {font:inherit;font-size:.8rem;margin-left:.3rem}
            [data-range] {min-width:0;margin:1rem 0 0;border:1px solid #cbd5e1}
            [data-range] button {flex-grow:0;align-self:end}
            .explorer-results {overflow:auto}
            .explorer-chart {min-width:0}
            """,
            js=Path(__file__).with_suffix(".js").read_text(encoding="utf-8"),
            dependencies=("plotly",) if numeric_columns else (),
        )
    except InteractiveExportTooLarge:
        report.error = (
            "Interactive HTML exceeds the configured size limit. Load fewer columns or "
            "narrow the Seconds interval on the CSV loader page and export again."
        )
