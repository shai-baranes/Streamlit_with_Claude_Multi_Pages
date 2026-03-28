"""
pages/3_🔄_Pivot_Tables.py  — Pivot Tables & Heatmap page.
"""

import streamlit as st
import numpy as np
import plotly.express as px
import matplotlib  # required by pandas Styler.background_gradient()
from utils import inject_css, require_data, sidebar_filters, tutorial_box

st.set_page_config(page_title="Pivot Tables", page_icon="🔄", layout="wide")
inject_css()

df_full = require_data()
df      = sidebar_filters(df_full)

st.title("🔄 Pivot Tables")

if df.empty:
    st.warning("⚠️ No data matches the current filters.")
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
</div>
""")

pv1, pv2, pv3, pv4 = st.columns(4)
with pv1: pivot_rows = st.selectbox("Pivot Rows",    ["Region","Category","Segment","Channel","Year","Quarter"], index=0)
with pv2: pivot_cols = st.selectbox("Pivot Columns", ["Category","Region","Segment","Channel","Year","Quarter"], index=1)
with pv3: pivot_val  = st.selectbox("Values",        ["Revenue","Profit","Units","Margin_%"], index=0)
with pv4: pivot_agg  = st.selectbox("Aggregation",   ["sum","mean","count","median","max"])

agg_fn = {"sum":"sum","mean":"mean","count":"count","median":np.median,"max":"max"}[pivot_agg]

if pivot_rows == pivot_cols:
    st.warning("⚠️ Rows and Columns must be different dimensions.")
    st.stop()

pivot_table = (
    df.pivot_table(
        values=pivot_val, index=pivot_rows, columns=pivot_cols,
        aggfunc=agg_fn, margins=True, margins_name="TOTAL", fill_value=0,
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
tutorial_box("""
<b>📘 Tutorial: Plotly Heatmap from Pivot</b><br>
Convert a pivot table to <code>px.imshow()</code>.
<code>.values</code> extracts the numpy array; row/col labels come from
<code>.index</code> and <code>.columns</code>.
</div>
""")

heat_data = pivot_table.iloc[:-1, :-1]
fig_heat = px.imshow(
    heat_data, color_continuous_scale="Viridis", template="plotly_white",
    title=f"Heatmap: {pivot_agg}({pivot_val}) — {pivot_rows} × {pivot_cols}",
    aspect="auto", text_auto=True,
)
fig_heat.update_layout(paper_bgcolor="#ffffff")
st.plotly_chart(fig_heat, use_container_width=True)

st.markdown("---")
st.caption(f"Showing {len(df):,} of {len(df_full):,} records")
