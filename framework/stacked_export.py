"""On-demand standalone Seconds event table."""
from dataclasses import asdict
from pathlib import Path

import json

import pandas as pd

from framework.config import MAX_INTERACTIVE_EXPORT_MB, MAX_PREVIEW
from framework.export_payload import InteractiveExportTooLarge, PayloadWriter, json_cell
from framework.stacked_presets import PresetError, PresetStore


def payload(frame, state, presets, limit):
    # Nullable extension arrays propagate NA through pandas ne/shift. In a
    # selection mask (and any(axis=1)) that comparison contributes no change.
    nullable = [i + 1 for i, dtype in enumerate(frame.dtypes)
                if getattr(dtype, "na_value", None) is pd.NA]
    settings = dict(columns=list(frame), nullable=nullable, selected=state["selected_columns_ordered"],
                    mode=state["view_mode"], exclusions=state["stacked_exclusion_cols"],
                    active=state.get("active_preset_id"), source=state.get("selected_source_row"),
                    presets=[asdict(p) for p in presets], pageSize=MAX_PREVIEW)
    writer = PayloadWriter(limit)
    writer.write(json.dumps(settings)[:-1])
    writer.write(',"rows":')
    writer.array([str(index), *map(json_cell, values)]
                 for index, *values in frame.itertuples(index=True, name=None))
    writer.write("}")
    return writer.finish()


def export_stacked_table(report, frame, state):
    def build():
        return payload(frame, state, PresetStore().list(), MAX_INTERACTIVE_EXPORT_MB * 1024**2)

    try:
        report.component("renderStacked", build, html="", css="""
        .stacked-scroll {overflow:auto;max-height:65vh}
        .stacked-scroll th {position:sticky;top:0;background:white;z-index:1}
        .stacked-scroll :is(td,th):nth-child(-n+2) {position:sticky;background:#f7f9fc}
        .stacked-scroll :is(td,th):first-child {left:0;width:9rem;min-width:9rem;max-width:9rem;overflow:hidden}
        .stacked-scroll :is(td,th):nth-child(2) {left:9rem}
        .stacked-scroll th:nth-child(-n+2) {z-index:2}
        .stacked-scroll tr[aria-selected=true]{background:#def}
        .stacked-controls button,.stacked-controls select{margin:.2rem}
        """, js=Path(__file__).with_suffix(".js").read_text(encoding="utf8"))
    except InteractiveExportTooLarge:
        report.error = ("Interactive HTML exceeds the configured size limit. "
                        "Narrow the filters or load fewer columns and export again.")
    except (ValueError, PresetError) as exc:
        report.error = str(exc)
