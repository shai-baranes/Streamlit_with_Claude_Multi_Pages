"""Build the offline pivot from the fields available in the live controls."""
from pathlib import Path

import matplotlib
import pandas as pd

from framework.config import MAX_INTERACTIVE_EXPORT_MB
from framework.export_payload import InteractiveExportTooLarge, PayloadWriter, json_cell


def pivot_payload(frame, settings, options, limit):
    writer = PayloadWriter(limit)
    writer.write('{"settings":')
    writer.value(settings)
    writer.write(',"options":')
    writer.value(options)
    writer.write(',"dimensions":{')
    for index, name in enumerate(options["rows"]):
        if index:
            writer.write(",")
        writer.value(name)
        # Keep pandas' native value ordering and distinguish missing from literal labels.
        codes, labels = pd.factorize(frame[name], sort=True)
        writer.write(':{"labels":')
        writer.array(map(json_cell, labels))
        writer.write(',"codes":')
        writer.array(map(int, codes))
        writer.write("}")
        del codes, labels
    writer.write('},"values":{')
    for index, name in enumerate(options["value"]):
        if index:
            writer.write(",")
        writer.value(name)
        writer.write(":")
        writer.array(map(json_cell, frame[name]))
    writer.write('},"colors":')
    cmap = matplotlib.colormaps["YlOrRd"]
    writer.array(matplotlib.colors.to_hex(cmap(index)) for index in range(cmap.N))
    writer.write("}")
    return writer.finish()


def export_pivot(report, frame, *, settings, options, tutorial):
    try:
        report.component(
            "renderPivot",
            lambda: pivot_payload(frame, settings, options, MAX_INTERACTIVE_EXPORT_MB * 1024**2),
            # The tutorial is trusted page markup, shared with the live tutorial box.
            html=f"""
            <div class="pivot-controls">
              <label>Pivot Rows<select data-rows></select></label>
              <label>Pivot Columns<select data-columns></select></label>
              <label>Values<select data-value></select></label>
              <label>Aggregation<select data-operation></select></label>
            </div>
            <p data-pivot-status role="status"></p>
            <div data-pivot-output hidden>
              <div class="pivot-table" tabindex="0" role="region" aria-label="Pivot table">
                <table aria-label="Pivot results"></table>
              </div>
              <h3>Pivot as Plotly Heatmap</h3>
              <aside>{tutorial}</aside>
              <div data-pivot-plot></div>
            </div>
            """,
            css="""
            .pivot-controls {display:grid; grid-template-columns:repeat(auto-fit,minmax(8rem,1fr)); gap:.75rem}
            .pivot-controls select {display:block; width:100%; font:inherit; padding:.25rem}
            .pivot-table {overflow:auto}
            .pivot-table th,.pivot-table td {white-space:nowrap}
            """,
            js=Path(__file__).with_suffix(".js").read_text(encoding="utf-8"),
            dependencies=("plotly",),
        )
    except InteractiveExportTooLarge:
        report.error = "Interactive HTML exceeds the configured size limit. Narrow the sidebar filters and export again."
