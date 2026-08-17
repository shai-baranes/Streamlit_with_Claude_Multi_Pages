"""
pages/1_📊_KPIs.py  — Key Performance Indicators page.
"""

import streamlit as st
from utils import inject_css, require_data, sidebar_filters, tutorial_box

st.set_page_config(page_title="KPIs", page_icon="📊", layout="wide")
inject_css()

df_full = require_data()
df      = sidebar_filters(df_full)

st.title("⚡ Key Performance Indicators")

# Robust emptiness check compatible with pandas and Dask DataFrames
try:
    df_is_empty = df.empty
except Exception:
    # Dask doesn't implement .empty; head(1) is cheap and returns a pandas DataFrame
    df_is_empty = df.head(1).empty

if df_is_empty:
    st.warning("⚠️ No data matches the current filters.")
    st.stop()

tutorial_box("""
<b>📘 Tutorial: st.metric()</b><br>
<code>st.metric(label, value, delta)</code> renders a KPI card.
<code>delta</code> shows a green ↑ or red ↓ arrow automatically.
Use <code>st.columns(n)</code> to lay out widgets side-by-side.
</div>
""")

col1, col2, col3, col4, col5 = st.columns(5)

# Helper to compute Dask scalars or return plain Python scalars unchanged
def _compute_if_dask(x):
    try:
        if hasattr(x, "compute"):
            return x.compute()
    except Exception:
        pass
    return x

# Compute metrics safely whether df is pandas or Dask
total_rev = _compute_if_dask(df["Revenue"].sum())
total_profit = _compute_if_dask(df["Profit"].sum())
avg_margin = _compute_if_dask(df["Margin_%"].mean())
# total_deals: len(df) may be unsupported for Dask, fall back to counting a column
try:
    total_deals = len(df)
except Exception:
    try:
        total_deals = int(_compute_if_dask(df.shape[0]))
    except Exception:
        total_deals = int(_compute_if_dask(df["Revenue"].count()))

win_rate = _compute_if_dask(df["Deal_Won"].mean()) * 100
full_rev = _compute_if_dask(df_full["Revenue"].sum())

# Defensive formatting: ensure numeric types
try:
    total_rev = float(total_rev)
except Exception:
    total_rev = 0.0
try:
    full_rev = float(full_rev)
except Exception:
    full_rev = 1.0  # avoid division by zero

pct_of_total = ((total_rev / full_rev) - 1) * 100 if full_rev else 0.0

col1.metric("Total Revenue", f"${total_rev/1e6:.2f}M", f"{pct_of_total:.1f}% of total")
col2.metric("Total Profit", f"${total_profit/1e6:.2f}M")
col3.metric("Avg Margin", f"{avg_margin:.1f}%")
col4.metric("Deals", f"{total_deals:,}")
col5.metric("Win Rate", f"{win_rate:.1f}%")

st.markdown("---")

# ── Revenue breakdown table ───────────────────────────────────────────────────
st.subheader("Revenue & Profit by Category")
summary = (
    df.groupby("Category")[
        ["Revenue", "Profit", "Units"]
    ]
    .sum()
    .sort_values("Revenue", ascending=False)
    .reset_index()
)
# If summary is a Dask DataFrame, compute it to get a pandas DataFrame
if hasattr(summary, "compute"):
    summary = summary.compute()
summary["Margin_%"] = (summary["Profit"] / summary["Revenue"] * 100).round(1)
st.dataframe(summary)

# ── Summary stats expander ────────────────────────────────────────────────────
with st.expander("📋 Descriptive Statistics  (df.describe())"):
    # tutorial_box("""
    st.markdown("""
    <div class='tutorial-box'>
    <b>📘 Tutorial: st.expander()</b><br>
    Wrap content in <code>with st.expander("title"):</code> to make it collapsible.
    </div>
    """, unsafe_allow_html=True)
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    desc = df[numeric_cols].describe()
    if hasattr(desc, "compute"):
        desc = desc.compute()
    st.dataframe(desc.round(2))

st.markdown("---")

# Compute display counts safely
try:
    shown = len(df)
except Exception:
    try:
        shown = int(_compute_if_dask(df.shape[0]))
    except Exception:
        shown = int(_compute_if_dask(df["Revenue"].count()))

try:
    total_count = len(df_full)
except Exception:
    try:
        total_count = int(_compute_if_dask(df_full.shape[0]))
    except Exception:
        total_count = int(_compute_if_dask(df_full["Revenue"].count()))

st.caption(f"Showing {shown:,} of {total_count:,} records")
