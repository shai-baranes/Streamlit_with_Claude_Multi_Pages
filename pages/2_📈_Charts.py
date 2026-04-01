"""
pages/2_📈_Charts.py  — Dynamic Charts page.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from utils import inject_css, require_data, sidebar_filters, tutorial_box

st.set_page_config(page_title="Charts", page_icon="📈", layout="wide")
inject_css()

df_full = require_data()
df      = sidebar_filters(df_full)

st.title("📈 Dynamic Charts")

if df.empty:
    st.warning("⚠️ No data matches the current filters.")
    st.stop()

tutorial_box("""
<b>📘 Tutorial: Reactive Widgets</b><br>
Every widget change triggers a full rerun. Widget return values are plain Python
variables — no callbacks needed. Use <code>go.Figure</code> with <code>.tolist()</code>
for reliable rendering on Streamlit 1.12 / older Plotly.
""")

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
        showlegend=False, plot_bgcolor="#ffffff", paper_bgcolor="#f5f7fa",
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
        plot_bgcolor="#ffffff", paper_bgcolor="#f5f7fa",
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
    fig_scatter.update_layout(plot_bgcolor="#ffffff", paper_bgcolor="#f5f7fa")
    st.plotly_chart(fig_scatter, use_container_width=True)

with c4:
    st.subheader("Treemap — Hierarchical Revenue")
    tree_metric = st.selectbox("Size metric", ["Revenue","Profit","Units"], key="tree_metric")
    fig_tree = px.treemap(
        df, path=["Region","Category","Segment"], values=tree_metric,
        color=tree_metric, color_continuous_scale="Tealgrn", template="plotly_white",
        title=f"Treemap: {tree_metric} by Region → Category → Segment",
    )
    fig_tree.update_layout(paper_bgcolor="#f5f7fa")
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
fig_box.update_layout(plot_bgcolor="#ffffff", paper_bgcolor="#f5f7fa", showlegend=False)
st.plotly_chart(fig_box, use_container_width=True)

# ══════════════════════════════════════════════
# ROW 4: Profit over Time
# ══════════════════════════════════════════════
st.subheader("📉 Aggregated Profit over Time")
tutorial_box("""
<b>📘 Tutorial: Time-axis aggregation</b><br>
<code>df.set_index("Date").resample(freq)</code> buckets rows into regular intervals.
<code>.cumsum()</code> gives a running total. <code>go.Figure + add_trace()</code>
overlays bars and a line on the same axes.
""")

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
                                name="Period Profit", marker_color="#6366f1", opacity=0.65))
    fig_profit.add_trace(go.Scatter(x=profit_ts["Date"].tolist(), y=profit_ts[y_col].tolist(),
                                    name=y_label, mode="lines+markers",
                                    line=dict(color="#0ea5e9", width=2.5), marker=dict(size=5)))
    fig_profit.update_layout(
        title=f"{'Cumulative' if show_cumulative else 'Aggregated'} Profit — {profit_freq}",
        xaxis_title="Date", yaxis_title="Profit ($)", template="plotly_white",
        plot_bgcolor="#ffffff", paper_bgcolor="#f5f7fa",
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
        template="plotly_white", plot_bgcolor="#ffffff", paper_bgcolor="#f5f7fa",
        hovermode="x unified", legend=dict(orientation="h", y=1.08),
    )

st.plotly_chart(fig_profit, use_container_width=True)


# ══════════════════════════════════════════════
# ROW 5: Shared-X Multi-metric — Option 1 (Stacked Subplots)
# ══════════════════════════════════════════════
st.markdown("---")
st.markdown("<div class='section-header'>🔀 Multi-Metric Shared-X Charts</div>", unsafe_allow_html=True)

tutorial_box("""
<b>📘 Tutorial: Shared-X stacked subplots — make_subplots()</b><br>
<code>make_subplots(rows=3, cols=1, shared_xaxes=True)</code> stacks three
independent charts with a single aligned X axis.<br><br>
• Each subplot has its own Y scale — no misleading comparisons<br>
• <code>shared_xaxes=True</code> shows X labels only on the bottom subplot<br>
• <code>vertical_spacing</code> controls the gap between rows<br>
• Mix <code>go.Bar</code> and <code>go.Scatter</code> freely across rows<br>
• Add traces with <code>fig.add_trace(..., row=N, col=1)</code>
""")

from plotly.subplots import make_subplots

sub_group = st.selectbox(
    "Group by (time dimension)",
    ["Monthly", "Quarterly", "Year"],
    key="sub_group",
)
sub_color = st.selectbox(
    "Color breakdown",
    ["None", "Category", "Region", "Segment", "Channel"],
    key="sub_color",
)

# Build the time-aggregated DataFrame
if sub_group == "Monthly":
    sub_df = df.groupby(["Year", "MonthNum", "Month"])[["Revenue","Profit","Units"]].sum().reset_index()
    sub_df["Period"] = sub_df["Year"].astype(str) + "-" + sub_df["MonthNum"].astype(str).str.zfill(2)
    sub_df = sub_df.sort_values("Period").reset_index(drop=True)
elif sub_group == "Quarterly":
    sub_df = df.groupby(["Year", "Quarter"])[["Revenue","Profit","Units"]].sum().reset_index()
    sub_df["Period"] = sub_df["Year"].astype(str) + " " + sub_df["Quarter"]
    sub_df = sub_df.sort_values(["Year","Quarter"]).reset_index(drop=True)
else:
    sub_df = df.groupby("Year")[["Revenue","Profit","Units"]].sum().reset_index()
    sub_df["Period"] = sub_df["Year"].astype(str)
    sub_df = sub_df.sort_values("Period").reset_index(drop=True)

_periods = sub_df["Period"].tolist()

fig_sub = make_subplots(
    rows=3, cols=1,
    shared_xaxes=True,          # X ticks aligned, only shown on bottom subplot
    vertical_spacing=0.06,      # tighter gap than default
    subplot_titles=["Revenue ($)", "Profit ($)", "Units"],
)

if sub_color == "None":
    fig_sub.add_trace(go.Bar(
        x=_periods,
        y=sub_df["Revenue"].tolist(),
        name="Revenue",
        marker_color="#3969AC",
        hovertemplate="<b>%{x}</b><br>Revenue: $%{y:,.0f}<extra></extra>",
    ), row=1, col=1)
    fig_sub.add_trace(go.Scatter(
        x=_periods,
        y=sub_df["Profit"].tolist(),
        name="Profit",
        mode="lines+markers",
        line=dict(color="#11A579", width=2),
        marker=dict(size=5),
        hovertemplate="<b>%{x}</b><br>Profit: $%{y:,.0f}<extra></extra>",
    ), row=2, col=1)
    fig_sub.add_trace(go.Bar(
        x=_periods,
        y=sub_df["Units"].tolist(),
        name="Units",
        marker_color="#E73F74",
        hovertemplate="<b>%{x}</b><br>Units: %{y:,.0f}<extra></extra>",
    ), row=3, col=1)
else:
    # With color breakdown — one trace per group per subplot
    if sub_group == "Monthly":
        sub_df2 = df.groupby(["Year","MonthNum","Month", sub_color])[["Revenue","Profit","Units"]].sum().reset_index()
        sub_df2["Period"] = sub_df2["Year"].astype(str) + "-" + sub_df2["MonthNum"].astype(str).str.zfill(2)
        sub_df2 = sub_df2.sort_values("Period").reset_index(drop=True)
    elif sub_group == "Quarterly":
        sub_df2 = df.groupby(["Year","Quarter", sub_color])[["Revenue","Profit","Units"]].sum().reset_index()
        sub_df2["Period"] = sub_df2["Year"].astype(str) + " " + sub_df2["Quarter"]
        sub_df2 = sub_df2.sort_values(["Year","Quarter"]).reset_index(drop=True)
    else:
        sub_df2 = df.groupby(["Year", sub_color])[["Revenue","Profit","Units"]].sum().reset_index()
        sub_df2["Period"] = sub_df2["Year"].astype(str)
        sub_df2 = sub_df2.sort_values("Period").reset_index(drop=True)

    _groups = sorted(sub_df2[sub_color].unique().tolist())
    _lp = px.colors.qualitative.Bold
    for i, grp in enumerate(_groups):
        _g = sub_df2[sub_df2[sub_color] == grp]
        _col = _lp[i % len(_lp)]
        _show = (i == 0)   # only first trace shows in legend per subplot to avoid duplication
        fig_sub.add_trace(go.Bar(
            x=_g["Period"].tolist(), y=_g["Revenue"].tolist(),
            name=str(grp), marker_color=_col, legendgroup=str(grp),
            showlegend=_show,
            hovertemplate=f"<b>{grp}</b><br>%{{x}}<br>Revenue: $%{{y:,.0f}}<extra></extra>",
        ), row=1, col=1)
        fig_sub.add_trace(go.Scatter(
            x=_g["Period"].tolist(), y=_g["Profit"].tolist(),
            name=str(grp), mode="lines+markers",
            line=dict(color=_col, width=2), marker=dict(size=4),
            legendgroup=str(grp), showlegend=False,
            hovertemplate=f"<b>{grp}</b><br>%{{x}}<br>Profit: $%{{y:,.0f}}<extra></extra>",
        ), row=2, col=1)
        fig_sub.add_trace(go.Bar(
            x=_g["Period"].tolist(), y=_g["Units"].tolist(),
            name=str(grp), marker_color=_col,
            legendgroup=str(grp), showlegend=False,
            hovertemplate=f"<b>{grp}</b><br>%{{x}}<br>Units: %{{y:,.0f}}<extra></extra>",
        ), row=3, col=1)

fig_sub.update_layout(
    height=600,
    template="plotly_white",
    plot_bgcolor="#ffffff",
    paper_bgcolor="#f5f7fa",
    hovermode="x unified",
    barmode="stack" if sub_color != "None" else "relative",
    legend=dict(orientation="h", y=-0.08),
)
# Force Y axes to linear with comma formatting
for r in [1, 2, 3]:
    fig_sub.update_yaxes(tickformat=",.0f", row=r, col=1)
# X axis type: category on all rows
for r in [1, 2, 3]:
    fig_sub.update_xaxes(type="category", tickangle=-35, row=r, col=1)

st.plotly_chart(fig_sub, use_container_width=True)


# ══════════════════════════════════════════════
# ROW 6: Shared-X Multi-metric — Option 3 (Normalized / same scale)
# ══════════════════════════════════════════════
tutorial_box("""
<b>📘 Tutorial: Normalized multi-series (0–1 scale)</b><br>
When metrics have very different magnitudes (Revenue in millions, Units in
hundreds), plotting them on the same Y axis is misleading.<br><br>
Normalizing each series to 0–1 (divide by its max) lets you compare
<b>trends and relative movements</b> rather than absolute values.<br><br>
<code>df[col] / df[col].max()</code> — simple min-max normalization<br>
All three series share one Y axis labelled "Normalized (0–1)"
""")

norm_group = st.selectbox(
    "Group by (time dimension)",
    ["Monthly", "Quarterly", "Year"],
    key="norm_group",
)

# Build aggregated data (same logic as above, no color breakdown for normalized view)
if norm_group == "Monthly":
    norm_df = df.groupby(["Year","MonthNum","Month"])[["Revenue","Profit","Units"]].sum().reset_index()
    norm_df["Period"] = norm_df["Year"].astype(str) + "-" + norm_df["MonthNum"].astype(str).str.zfill(2)
    norm_df = norm_df.sort_values("Period").reset_index(drop=True)
elif norm_group == "Quarterly":
    norm_df = df.groupby(["Year","Quarter"])[["Revenue","Profit","Units"]].sum().reset_index()
    norm_df["Period"] = norm_df["Year"].astype(str) + " " + norm_df["Quarter"]
    norm_df = norm_df.sort_values(["Year","Quarter"]).reset_index(drop=True)
else:
    norm_df = df.groupby("Year")[["Revenue","Profit","Units"]].sum().reset_index()
    norm_df["Period"] = norm_df["Year"].astype(str)
    norm_df = norm_df.sort_values("Period").reset_index(drop=True)

# Normalize each column to 0-1 range
for col in ["Revenue", "Profit", "Units"]:
    _max = norm_df[col].max()
    norm_df[col + "_norm"] = (norm_df[col] / _max).round(4) if _max != 0 else 0

_norm_periods = norm_df["Period"].tolist()
fig_norm = go.Figure()
fig_norm.add_trace(go.Scatter(
    x=_norm_periods,
    y=norm_df["Revenue_norm"].tolist(),
    name="Revenue",
    mode="lines+markers",
    line=dict(color="#3969AC", width=2.5),
    marker=dict(size=6),
    hovertemplate="<b>%{x}</b><br>Revenue (norm): %{y:.3f}<extra></extra>",
))
fig_norm.add_trace(go.Scatter(
    x=_norm_periods,
    y=norm_df["Profit_norm"].tolist(),
    name="Profit",
    mode="lines+markers",
    line=dict(color="#11A579", width=2.5),
    marker=dict(size=6),
    hovertemplate="<b>%{x}</b><br>Profit (norm): %{y:.3f}<extra></extra>",
))
fig_norm.add_trace(go.Scatter(
    x=_norm_periods,
    y=norm_df["Units_norm"].tolist(),
    name="Units",
    mode="lines+markers",
    line=dict(color="#E73F74", width=2.5),
    marker=dict(size=6),
    hovertemplate="<b>%{x}</b><br>Units (norm): %{y:.3f}<extra></extra>",
))
fig_norm.update_layout(
    title=f"Revenue, Profit & Units — Normalized (0–1) by {norm_group}",
    template="plotly_white",
    plot_bgcolor="#ffffff",
    paper_bgcolor="#f5f7fa",
    xaxis=dict(type="category", tickangle=-35),
    yaxis=dict(
        title="Normalized value (0 = min, 1 = max)",
        range=[-0.05, 1.1],
        tickformat=".2f",
    ),
    hovermode="x unified",
    legend=dict(orientation="h", y=1.08),
    height=400,
)
st.plotly_chart(fig_norm, use_container_width=True)

st.markdown("---")
st.caption(f"Showing {len(df):,} of {len(df_full):,} records")
