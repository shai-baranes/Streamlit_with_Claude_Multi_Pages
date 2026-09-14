"""
pages/4_🗂️_Data_Explorer.py  — Filtered Data Table & Download page.
"""

import streamlit as st
# Namespace widget persistence so legacy pages retain independent selections.
from framework.state import ui
st = ui(__file__)
from framework.exports import render_csv_export, shared_filter_context
from utils import inject_css, require_data, sidebar_filters, tutorial_box

st.set_page_config(page_title="Data Explorer", page_icon="🗂️", layout="wide")
inject_css() # check if applicable?

df_full = require_data()
# Sales views require their original schema; generic CSVs use Engineering Explorer.
from framework.config import ALWAYS_LOAD_COLUMNS
_missing = set(ALWAYS_LOAD_COLUMNS) - set(df_full.columns)
if _missing:
    st.info("This sales view needs: " + ", ".join(sorted(_missing)) + ". Use Engineering Explorer for other schemas.")
    st.stop()
df      = sidebar_filters(df_full)

st.title("🗂️ Filtered Data Explorer")

if df.empty:
    st.warning("⚠️ No data matches the current filters.")
    st.stop()

tutorial_box("""
<b>📘 Tutorial: st.dataframe() + date range filter</b><br>
• <code>st.dataframe(df)</code> — read-only, sortable table<br>
• Pre-format columns as strings before passing to <code>st.dataframe()</code> (v1.12 compatible)<br>
• <code>st.selectbox</code> over <code>df["Date"].dt.date.unique()</code> — type-safe date filtering<br>
• <code>st.download_button</code> — export the current view as CSV
</div>
""")

# ── Date range filter ─────────────────────────────────────────────────────────
# Exclude missing dates from picker options while retaining them in the source dataset.
_dates = sorted(df["Date"].dropna().dt.date.unique().tolist())
if not _dates:
    st.info("No valid dates are available for this view.")
    st.stop()
dt1, dt2 = st.columns(2)
with dt1:
    tbl_start = st.selectbox("📅 Start Date", options=_dates, index=0, key="tbl_start")
with dt2:
    tbl_end   = st.selectbox("📅 End Date",   options=_dates, index=len(_dates)-1, key="tbl_end")

if tbl_start > tbl_end:
    st.warning("⚠️ Start date is after end date.")
    st.stop()

df_table = df[(df["Date"].dt.date >= tbl_start) & (df["Date"].dt.date <= tbl_end)]
st.caption(f"Date range: **{tbl_start}** → **{tbl_end}**  |  {len(df_table):,} matching rows")

# ── Column selector + row limit ───────────────────────────────────────────────
display_cols = st.multiselect(
    "Columns to display",
    options=df.columns.tolist(),
    default=["Date","Region","Country","Category","Product","Segment",
             "Revenue","Profit","Margin_%","Deal_Won"],
)
n_rows = st.slider("Rows to preview", 10, 200, 50, step=10)

if display_cols:
    display_df = df_table[display_cols].head(n_rows).copy()
    if "Revenue"  in display_df.columns: display_df["Revenue"]  = display_df["Revenue"].apply(lambda x: f"${x:,.0f}")
    if "Profit"   in display_df.columns: display_df["Profit"]   = display_df["Profit"].apply(lambda x: f"${x:,.0f}")
    if "Cost"     in display_df.columns: display_df["Cost"]     = display_df["Cost"].apply(lambda x: f"${x:,.0f}")
    if "Margin_%" in display_df.columns: display_df["Margin_%"] = display_df["Margin_%"].apply(lambda x: f"{x:.1f}%")
    if "Date"     in display_df.columns: display_df["Date"]     = display_df["Date"].dt.strftime("%Y-%m-%d")
    st.dataframe(display_df)

# ── Download ──────────────────────────────────────────────────────────────────
# Generate the full export only after an explicit request.
render_csv_export(df_table, page=__file__, context=(shared_filter_context(), tbl_start, tbl_end))

st.markdown("---")
st.caption(f"Showing {len(df):,} of {len(df_full):,} records (date range further narrows to {len(df_table):,})")
