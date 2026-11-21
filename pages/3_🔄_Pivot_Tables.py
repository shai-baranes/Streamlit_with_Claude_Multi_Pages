"""
pages/3_🔄_Pivot_Tables.py  — Pivot Tables & Heatmap page.
"""

import streamlit as st
# Namespace widget persistence so legacy pages retain independent selections.
from framework.state import current_html_export, ui
st = ui(__file__)
import numpy as np
import plotly.express as px
import matplotlib  # required by pandas Styler.background_gradient()
from utils import inject_css, require_data, sidebar_filters, tutorial_box, render_csv_metadata

PIVOT_ROWS = ("Region", "Category", "Segment", "Channel", "Year", "Quarter")
PIVOT_COLUMNS = ("Category", "Region", "Segment", "Channel", "Year", "Quarter")
PIVOT_VALUES = ("Revenue", "Profit", "Units", "Margin_%")
AGGREGATIONS = {"sum": "sum", "mean": "mean", "count": "count", "median": np.median, "max": "max"}
HEATMAP_TUTORIAL = """
<b>📘 Tutorial: Plotly Heatmap from Pivot</b><br>
Convert a pivot table to <code>px.imshow()</code>.
<code>.values</code> extracts the numpy array; row/col labels come from
<code>.index</code> and <code>.columns</code>.
"""

st.set_page_config(page_title="Pivot Tables", page_icon="🔄", layout="wide")
inject_css()

render_csv_metadata()
df_full = require_data()
# Sales views require their original schema; generic CSVs use Engineering Explorer.
from framework.config import ALWAYS_LOAD_COLUMNS
_missing = set(ALWAYS_LOAD_COLUMNS) - set(df_full.columns)
if _missing:
    st.info("This sales view needs: " + ", ".join(sorted(_missing)) + ". Use Engineering Explorer for other schemas.")
    st.stop()
st = st.exportable_page(
    title="Pivot Tables",
    help="The file includes the six pivot dimensions and four value fields for every row matching the sidebar filters.",
)
df = sidebar_filters(df_full)

st.title("🔄 Pivot Tables")

if df.empty:
    st.warning("⚠️ No data matches the current filters.")
    st.caption(f"Showing 0 of {len(df_full):,} records")
    st.stop()

tutorial_box("""
<b>📘 Tutorial: pd.pivot_table()</b><br>
<code>pd.pivot_table(df, values, index, columns, aggfunc)</code><br><br>
• <b>values</b>  — column to aggregate (Revenue, Profit …)<br>
• <b>index</b>   — pivot rows<br>
• <b>columns</b> — pivot columns<br>
• <b>aggfunc</b> — 'sum', 'mean', 'count', np.median, etc.<br>
• <b>margins=True</b> adds row/column totals automatically<br><br>
Use <code>.style.background_gradient()</code> for heatmap colouring (requires matplotlib).
""")

st.begin_export_exclusion()
pv1, pv2, pv3, pv4 = st.columns(4)
with pv1: pivot_rows = st.selectbox("Pivot Rows", PIVOT_ROWS)
with pv2: pivot_cols = st.selectbox("Pivot Columns", PIVOT_COLUMNS, index=0 if st.is_batch_export() else 1)
with pv3: pivot_val = st.selectbox("Values", PIVOT_VALUES)
with pv4: pivot_agg = st.selectbox("Aggregation", AGGREGATIONS)
st.end_export_exclusion()

# The standalone component owns the controls and both outputs. Capture it even
# when the current selections are invalid so recipients can correct them offline.
report = current_html_export()
if report is not None:
    from framework.pivot_export import export_pivot

    export_pivot(
        report, df,
        settings={"rows": pivot_rows, "columns": pivot_cols, "value": pivot_val, "operation": pivot_agg},
        options={"rows": PIVOT_ROWS, "columns": PIVOT_COLUMNS, "value": PIVOT_VALUES,
                 "operation": tuple(AGGREGATIONS)},
        tutorial=HEATMAP_TUTORIAL,
    )

record_count = f"Showing {len(df):,} of {len(df_full):,} records"

if pivot_rows == pivot_cols:
    st.begin_export_exclusion()
    st.warning("⚠️ Rows and Columns must be different dimensions.")
    st.end_export_exclusion()
    st.caption(record_count)
    st.stop()

st.begin_export_exclusion()
pivot_table = (
    df.pivot_table(
        values=pivot_val, index=pivot_rows, columns=pivot_cols,
        aggfunc=AGGREGATIONS[pivot_agg], margins=True, margins_name="TOTAL", fill_value=0,
    )
)

pivot_numeric = pivot_table.iloc[:-1, :-1]
styled = (
    pivot_numeric
    .style
    .background_gradient(cmap="YlOrRd", axis=None)
    .format(lambda x: f"${x:,.0f}" if pivot_val in ["Revenue","Profit"]
                      else (f"{x:.1f}%" if pivot_val == "Margin_%" else f"{int(x):,}"))
)
st.dataframe(styled)
st.caption(f"Pivot: {pivot_agg}({pivot_val}) — {pivot_rows} × {pivot_cols} — {len(pivot_table)-1} row groups")

# ── Heatmap ───────────────────────────────────────────────────────────────────
st.subheader("Pivot as Plotly Heatmap")
tutorial_box(HEATMAP_TUTORIAL)

heat_data = pivot_table.iloc[:-1, :-1]
fig_heat = px.imshow(
    heat_data, color_continuous_scale="Viridis", template="plotly_white",
    title=f"Heatmap: {pivot_agg}({pivot_val}) — {pivot_rows} × {pivot_cols}",
    aspect="auto", text_auto=True,
)
fig_heat.update_layout(paper_bgcolor="#ffffff")
st.plotly_chart(fig_heat)
st.end_export_exclusion()

st.markdown("---")
st.caption(record_count)
st.finish_html_export()
