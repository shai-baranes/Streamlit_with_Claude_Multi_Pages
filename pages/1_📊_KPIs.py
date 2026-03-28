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

if df.empty:
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

total_rev    = df["Revenue"].sum()
total_profit = df["Profit"].sum()
avg_margin   = df["Margin_%"].mean()
total_deals  = len(df)
win_rate     = df["Deal_Won"].mean() * 100
full_rev     = df_full["Revenue"].sum()

col1.metric("Total Revenue",  f"${total_rev/1e6:.2f}M",  f"{((total_rev/full_rev)-1)*100:.1f}% of total")
col2.metric("Total Profit",   f"${total_profit/1e6:.2f}M")
col3.metric("Avg Margin",     f"{avg_margin:.1f}%")
col4.metric("Deals",          f"{total_deals:,}")
col5.metric("Win Rate",       f"{win_rate:.1f}%")

st.markdown("---")

# ── Revenue breakdown table ───────────────────────────────────────────────────
st.subheader("Revenue & Profit by Category")
summary = (
    df.groupby("Category")[["Revenue", "Profit", "Units"]]
    .sum()
    .sort_values("Revenue", ascending=False)
    .reset_index()
)
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
    st.dataframe(df[numeric_cols].describe().round(2))

st.markdown("---")
st.caption(f"Showing {len(df):,} of {len(df_full):,} records")
