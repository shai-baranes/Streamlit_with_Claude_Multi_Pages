"""
pages/2_📈_Charts.py  — Dynamic Charts page.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from utils import inject_css, require_data, sidebar_filters_2

st.set_page_config(page_title="Charts", page_icon="📈", layout="wide")
inject_css()

df_full = require_data()
df      = sidebar_filters_2(df_full)

st.title("📈 Dynamic Charts")

if df.empty:
    st.warning("⚠️ No data matches the current filters.")
    st.stop()

st.markdown("""
<div class='tutorial-box'>
<b>📘 Tutorial: Reactive Widgets</b><br>
Every widget change triggers a full rerun. Widget return values are plain Python
variables — no callbacks needed. Use <code>go.Figure</code> with <code>.tolist()</code>
for reliable rendering on Streamlit 1.12 / older Plotly.
</div>
""", unsafe_allow_html=True)

_palette = ["#7F3C8D","#11A579","#3969AC","#F2B701","#E73F74",
            "#80BA5A","#E68310","#008695","#CF1C90","#f97b72"]

# ══════════════════════════════════════════════
# ROW 1: Bar + Line
# ══════════════════════════════════════════════
c1, c2 = st.columns(2)

with c1:
    st.subheader("Bar Chart — Revenue Breakdown")
    bar_group = st.selectbox("Group by", ["Category","Region","Segment","Channel","Year","Quarter"], key="bar_group")
    bar_metric = st.radio("Metric", ["Revenue","Profit","Units"], horizontal=True, key="bar_metric")
    bar_orientation = st.radio("Orientation", ["Vertical","Horizontal"], horizontal=True, key="bar_orient")

    bar_df = (
        df.groupby(bar_group)[bar_metric]
        .sum()
        .reset_index()
        .sort_values(bar_metric, ascending=False)
        .reset_index(drop=True)
    )
    _colors = [_palette[i % len(_palette)] for i in range(len(bar_df))]

    if bar_orientation == "Horizontal":
        bar_df_plot = bar_df.sort_values(bar_metric, ascending=False).reset_index(drop=True)
        _hx = bar_df_plot[bar_metric].tolist()
        _hy = bar_df_plot[bar_group].tolist()
        fig_bar = go.Figure(go.Bar(
            x=_hx, y=_hy, orientation="h", marker_color=_colors,
            hovertemplate=f"<b>%{{y}}</b><br>{bar_metric}: %{{x:,.0f}}<extra></extra>",
        ))
        fig_bar.update_layout(
            xaxis=dict(type="linear", range=[0, max(_hx)*1.15], tickformat=",.0f"),
            yaxis=dict(type="category"),
            xaxis_title=bar_metric, yaxis_title=bar_group,
        )
    else:
        _x = bar_df[bar_group].tolist()[::-1]
        _y = bar_df[bar_metric].tolist()[::-1]
        fig_bar = go.Figure(go.Bar(
            x=_x, y=_y, marker_color=_colors,
            hovertemplate=f"<b>%{{x}}</b><br>{bar_metric}: %{{y:,.0f}}<extra></extra>",
        ))
        fig_bar.update_layout(
            xaxis=dict(type="category"),
            yaxis=dict(type="linear", range=[0, max(_y)*1.15], tickformat=",.0f"),
            xaxis_title=bar_group, yaxis_title=bar_metric,
        )
    fig_bar.update_layout(
        title=f"{bar_metric} by {bar_group}", template="plotly_white",
        showlegend=False, plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
    )
    st.plotly_chart(fig_bar, use_container_width=True)

with c2:
    st.subheader("Time-Series Line Chart")
    line_metric = st.selectbox("Metric", ["Revenue","Profit","Units","Margin_%"], key="line_metric")
    line_color  = st.selectbox("Color dimension", ["Category","Region","Segment","Channel"], key="line_color")
    line_freq   = st.radio("Granularity", ["Monthly","Quarterly"], horizontal=True, key="line_freq")

    if line_freq == "Monthly":
        line_df = df.groupby(["Year","MonthNum","Month", line_color])[line_metric].sum().reset_index()
        line_df["Period"] = line_df["Year"].astype(str) + "-" + line_df["MonthNum"].astype(str).str.zfill(2)
        line_df = line_df.sort_values("Period")
    else:
        line_df = df.groupby(["Year","Quarter", line_color])[line_metric].sum().reset_index()
        line_df["Period"] = line_df["Year"].astype(str) + " " + line_df["Quarter"]
        line_df = line_df.sort_values(["Year","Quarter"])

    _lp = px.colors.qualitative.Vivid
    _groups = sorted(line_df[line_color].unique().tolist())
    fig_line = go.Figure()
    for i, grp in enumerate(_groups):
        _g = line_df[line_df[line_color] == grp].sort_values("Period")
        fig_line.add_trace(go.Scatter(
            x=_g["Period"].tolist(), y=_g[line_metric].tolist(),
            mode="lines+markers", name=str(grp),
            line=dict(color=_lp[i % len(_lp)], width=2), marker=dict(size=5),
            hovertemplate=f"<b>{grp}</b><br>%{{x}}<br>{line_metric}: %{{y:,.1f}}<extra></extra>",
        ))
    fig_line.update_layout(
        title=f"{line_metric} over Time by {line_color}", template="plotly_white",
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        xaxis=dict(type="category", tickangle=-35),
        yaxis=dict(type="linear", tickformat=",.0f"),
        legend=dict(orientation="h", y=-0.25), hovermode="x unified",
    )
    st.plotly_chart(fig_line, use_container_width=True)

# ══════════════════════════════════════════════
# ROW 2: Scatter + Treemap
# ══════════════════════════════════════════════
c3, c4 = st.columns(2)

with c3:
    st.subheader("Scatter Plot — Revenue vs Profit")
    scatter_color = st.selectbox("Color by", ["Category","Segment","Region","Channel"], key="scatter_color")
    scatter_size  = st.selectbox("Bubble size", ["Units","Revenue","Profit"], key="scatter_size")
    scatter_df = df.sample(min(500, len(df)), random_state=1)
    fig_scatter = px.scatter(
        scatter_df, x="Revenue", y="Profit", color=scatter_color, size=scatter_size,
        hover_data=["Product","Country","Sales_Rep"], template="plotly_white",
        color_discrete_sequence=px.colors.qualitative.Pastel,
        title=f"Revenue vs Profit (colored by {scatter_color})", opacity=0.75,
    )
    fig_scatter.update_layout(plot_bgcolor="#ffffff", paper_bgcolor="#ffffff")
    st.plotly_chart(fig_scatter, use_container_width=True)

with c4:
    st.subheader("Treemap — Hierarchical Revenue")
    tree_metric = st.selectbox("Size metric", ["Revenue","Profit","Units"], key="tree_metric")
    fig_tree = px.treemap(
        df, path=["Region","Category","Segment"], values=tree_metric,
        color=tree_metric, color_continuous_scale="Tealgrn", template="plotly_white",
        title=f"Treemap: {tree_metric} by Region → Category → Segment",
    )
    fig_tree.update_layout(paper_bgcolor="#ffffff")
    st.plotly_chart(fig_tree, use_container_width=True)

# ══════════════════════════════════════════════
# ROW 3: Box plot
# ══════════════════════════════════════════════
st.subheader("Box Plot — Margin Distribution")
box_x = st.selectbox("X-axis grouping", ["Category","Segment","Channel","Region","Year"], key="box_x")
fig_box = px.box(
    df, x=box_x, y="Margin_%", color=box_x, points="outliers",
    template="plotly_white", color_discrete_sequence=px.colors.qualitative.Antique,
    title=f"Margin % Distribution by {box_x}",
)
fig_box.update_layout(plot_bgcolor="#ffffff", paper_bgcolor="#ffffff", showlegend=False)
st.plotly_chart(fig_box, use_container_width=True)

# ══════════════════════════════════════════════
# ROW 4: Profit over Time
# ══════════════════════════════════════════════
st.subheader("📉 Aggregated Profit over Time")
st.markdown("""
<div class='tutorial-box'>
<b>📘 Tutorial: Time-axis aggregation</b><br>
<code>df.set_index("Date").resample(freq)</code> buckets rows into regular intervals.
<code>.cumsum()</code> gives a running total. <code>go.Figure + add_trace()</code>
overlays bars and a line on the same axes.
</div>
""", unsafe_allow_html=True)

p1, p2, p3 = st.columns(3)
with p1:
    profit_freq = st.radio("Granularity", ["Daily","Weekly","Monthly","Quarterly"], index=2, horizontal=True, key="profit_freq")
with p2:
    profit_breakdown = st.selectbox("Color breakdown", ["None","Category","Region","Segment","Channel"], key="profit_breakdown")
with p3:
    show_cumulative = st.checkbox("Cumulative", value=False, key="profit_cumul")

freq_map   = {"Daily":"D","Weekly":"W","Monthly":"ME","Quarterly":"QE"}
freq_alias = freq_map[profit_freq]

if profit_breakdown == "None":
    profit_ts = df.set_index("Date").resample(freq_alias)["Profit"].sum().reset_index()
    profit_ts.columns = ["Date","Profit"]
    if show_cumulative:
        profit_ts["CumulativeProfit"] = profit_ts["Profit"].cumsum()
        y_col, y_label = "CumulativeProfit", "Cumulative Profit ($)"
    else:
        y_col, y_label = "Profit", "Profit ($)"
    fig_profit = go.Figure()
    fig_profit.add_trace(go.Bar(x=profit_ts["Date"].tolist(), y=profit_ts["Profit"].tolist(),
                                name="Period Profit", marker_color="#6366f1", opacity=0.50))
    fig_profit.add_trace(go.Scatter(x=profit_ts["Date"].tolist(), y=profit_ts[y_col].tolist(),
                                    name=y_label, mode="lines+markers",
                                    line=dict(color="#22d3ee", width=2.5), marker=dict(size=5)))
    fig_profit.update_layout(
        title=f"{'Cumulative' if show_cumulative else 'Aggregated'} Profit — {profit_freq}",
        xaxis_title="Date", yaxis_title="Profit ($)", template="plotly_white",
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        legend=dict(orientation="h", y=1.08), hovermode="x unified", barmode="overlay",
    )
else:
    profit_ts = (
        df.groupby([pd.Grouper(key="Date", freq=freq_alias), profit_breakdown])["Profit"]
        .sum().reset_index()
    )
    if show_cumulative:
        profit_ts = profit_ts.sort_values("Date")
        profit_ts["Profit"] = profit_ts.groupby(profit_breakdown)["Profit"].cumsum()
    _lp2 = px.colors.qualitative.Bold
    _pgroups = sorted(profit_ts[profit_breakdown].unique().tolist())
    fig_profit = go.Figure()
    for i, grp in enumerate(_pgroups):
        _g = profit_ts[profit_ts[profit_breakdown] == grp].sort_values("Date")
        fig_profit.add_trace(go.Scatter(
            x=_g["Date"].tolist(), y=_g["Profit"].tolist(),
            mode="lines+markers", name=str(grp),
            line=dict(color=_lp2[i % len(_lp2)], width=2), marker=dict(size=4),
        ))
    fig_profit.update_layout(
        title=f"{'Cumulative' if show_cumulative else 'Aggregated'} Profit by {profit_breakdown} — {profit_freq}",
        template="plotly_white", plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        hovermode="x unified", legend=dict(orientation="h", y=1.08),
    )

st.plotly_chart(fig_profit, use_container_width=True)

st.markdown("---")
st.caption(f"Showing {len(df):,} of {len(df_full):,} records")
