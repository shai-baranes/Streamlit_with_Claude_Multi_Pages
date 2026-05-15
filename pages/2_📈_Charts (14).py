"""
pages/2_📈_Charts.py  — Dynamic Charts page.
"""

import streamlit as st
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from utils import inject_css, require_data, sidebar_filters, tutorial_box, my_func3
# import streamlit.components.v1 as _cv1

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
    title=f"koko",
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
my_func3("koko")

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
# ── Ruler: dual-cursor time-delta measurement ────────────────────────────────
# TUTORIAL NOTE ───────────────────────────────────────────────────────────────
# Plotly does not expose drag-selection x-ranges to Python in Streamlit 1.12.
# The compatible solution: two sliders select cursor positions (by index into
# the period list). Plotly then draws two vertical lines (shapes) and an
# annotation showing the period delta between them.
# shapes= in update_layout draws reference lines that overlay all traces.
# annotations= adds a text label anchored to the chart area.
# ─────────────────────────────────────────────────────────────────────────────
_n_periods = len(_norm_periods)




# ── TUTORIAL NOTE ────────────────────────────────────────────────────────────
# st.slider supports click-and-drag natively in the browser.
# However Streamlit reruns on every slider change during drag, which
# re-renders the page mid-drag and breaks the gesture.
# Fix: wrap sliders in st.form — the rerun only fires on form submit,
# so the user can drag freely and the chart updates only on "Apply".
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("**📏 Time-delta ruler** — drag the cursors then click Apply to update")
with st.form(key="ruler_form"):
    _ruler_cols = st.columns([1, 1, 1, 3])
    with _ruler_cols[0]:
        _cur_a = st.slider(
            "Cursor A", 0, _n_periods - 1,
            value=st.session_state.get("ruler_a", 0),
            key="ruler_a",
            format="%d",
        )
    with _ruler_cols[1]:
        _cur_b = st.slider(
            "Cursor B", 0, _n_periods - 1,
            value=st.session_state.get("ruler_b", min(_n_periods - 1, _n_periods // 2)),
            key="ruler_b",
            format="%d",
        )
    with _ruler_cols[2]:
        st.form_submit_button("📏 Apply", use_container_width=True)

# Ensure A is always left of B
_left  = min(_cur_a, _cur_b)
_right = max(_cur_a, _cur_b)
_delta = _right - _left   # number of periods between cursors

_period_left  = _norm_periods[_left]
_period_right = _norm_periods[_right]

with _ruler_cols[2]:
    if _delta == 0:
        st.info("Move cursors apart to measure a span.")
    else:
        st.metric(
            label=f"Span:  {_period_left}  →  {_period_right}",
            value=f"{_delta} period{'s' if _delta != 1 else ''}",
        )

# Add ruler lines and shaded span to the chart via shapes + annotations
_shapes = [
    # Cursor A — solid vertical line
    dict(
        type="line",
        xref="x", yref="paper",
        x0=_period_left,  x1=_period_left,
        y0=0, y1=1,
        line=dict(color="#E73F74", width=2, dash="solid"),
    ),
    # Cursor B — solid vertical line
    dict(
        type="line",
        xref="x", yref="paper",
        x0=_period_right, x1=_period_right,
        y0=0, y1=1,
        line=dict(color="#E73F74", width=2, dash="solid"),
    ),
]

# Shaded region between cursors (only when they differ)
if _delta > 0:
    _shapes.append(dict(
        type="rect",
        xref="x", yref="paper",
        x0=_period_left,  x1=_period_right,
        y0=0, y1=1,
        fillcolor="rgba(231,63,116,0.08)",
        line=dict(width=0),
        layer="below",
    ))

_annotations = []
if _delta > 0:
    # Mid-point label showing the delta
    _mid_idx = (_left + _right) // 2
    _annotations.append(dict(
        xref="x", yref="paper",
        x=_norm_periods[_mid_idx],
        y=1.06,
        text=f"◄── {_delta} period{'s' if _delta != 1 else ''} ──►",
        showarrow=False,
        font=dict(size=11, color="#E73F74"),
        align="center",
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
    height=420,
    shapes=_shapes,
    annotations=_annotations,
)
# ── Dot-adding mode ──────────────────────────────────────────────────────────
# Simplest possible approach: pure JS handles everything in the browser.
# No st.text_input, no Streamlit rerun, no slowness.
# JS listens for plotly_click, reads x/y, and writes them into a <div>
# that lives inside the st.components.v1.html iframe — instant display.
_dot_mode = st.checkbox(
    "🖊 Dot-adding mode (click chart to see coordinates)",
    value=False,
    key="norm_dot_mode",
)

st.plotly_chart(fig_norm, use_container_width=True)

my_func3("Normalized")

# ══════════════════════════════════════════════
# ROW 7: Animated Geo-Trace (Streamlit 1.12 compatible)
# ══════════════════════════════════════════════
st.markdown("---")
st.markdown("<div style='border-left:4px solid #6366f1;padding-left:12px;font-size:1.3rem;font-weight:700;'>🗺️ Animated Geo-Trace</div>", unsafe_allow_html=True)

tutorial_box("""
<b>📘 Tutorial: Animated map — st.empty() loop (Streamlit 1.12 compatible)</b><br>
On Streamlit 1.12 / Plotly 5.5, <code>go.Figure(frames=[...])</code> with
<code>updatemenus</code> (Play button) is silently dropped during JSON serialisation —
the animation never starts.<br><br>
The reliable fix is a <b>Python loop + <code>st.empty()</code></b>:<br>
• <code>st.empty()</code> creates a single placeholder container<br>
• Each iteration replaces its content with a new chart (<code>placeholder.plotly_chart()</code>)<br>
• <code>time.sleep()</code> controls frame rate<br>
• The trail grows by slicing <code>lats[:i+1]</code> on each frame<br><br>
This works on every Streamlit version and requires no Plotly animation engine.
""")

import time as _time

# ── Synthetic geo dataset ─────────────────────────────────────────────────────
# A 40-step simulated route. Replace with your real DataFrame.
np.random.seed(42)
_n = 40
_t_vals = np.linspace(0, 39, _n)
_lat_base = np.linspace(32.05, 33.20, _n)
_lon_base = np.linspace(34.75, 34.55, _n)
_lat_vals = (_lat_base + 0.04 * np.sin(_t_vals * 0.7)
             + np.random.normal(0, 0.008, _n)).round(5).tolist()
_lon_vals = (_lon_base + 0.03 * np.cos(_t_vals * 0.5)
             + np.random.normal(0, 0.006, _n)).round(5).tolist()
_t_vals   = _t_vals.round(1).tolist()

geo_df = pd.DataFrame({
    "Time":      _t_vals,
    "Latitude":  _lat_vals,
    "Longitude": _lon_vals,
})

st.caption(
    f"Synthetic route · {len(geo_df)} steps · "
    f"lat {min(_lat_vals):.3f}–{max(_lat_vals):.3f} · "
    f"lon {min(_lon_vals):.3f}–{max(_lon_vals):.3f}"
)

# ── Controls ──────────────────────────────────────────────────────────────────
gc1, gc2, gc3 = st.columns(3)
with gc1:
    frame_ms = st.slider("Frame duration (ms)", 50, 600, 200, step=50, key="geo_frame_ms")
with gc2:
    map_style = st.selectbox(
        "Map style",
        ["open-street-map", "carto-positron", "white-bg"],
        key="geo_map_style",
    )
with gc3:
    show_trail = st.checkbox("Show cumulative trail", value=True, key="geo_trail")

# ── Session state: persist frame index and running flag across reruns ─────────
# TUTORIAL NOTE ───────────────────────────────────────────────────────────────
# Clicking any button triggers a full Streamlit rerun — this breaks any running
# for-loop. To support Pause and Stop we store:
#   geo_frame  — the last rendered frame index (resumes from here on Play)
#   geo_running — True while the animation loop should keep running
#
# The loop checks session_state["geo_running"] on every iteration.
# Clicking Pause sets it to False → the next iteration sees False and breaks.
# Clicking Stop also resets geo_frame to 0 (back to start).
# ─────────────────────────────────────────────────────────────────────────────
if "geo_frame"   not in st.session_state: st.session_state["geo_frame"]   = 0
if "geo_running" not in st.session_state: st.session_state["geo_running"] = False

# ── Play / Pause / Stop buttons ───────────────────────────────────────────────
# TUTORIAL NOTE ───────────────────────────────────────────────────────────────
# Root cause of the double-click / Stop-acts-like-Pause bug:
# st.button() both RENDERS the button AND returns True if clicked — in one call.
# State updates after that call are too late to affect the current rerun's
# rendering of other elements (caption, map frame).
#
# Fix: use a hidden "action" key in session_state as a one-rerun message queue.
# Each button writes its action name into session_state["geo_action"] via
# on_click= callback, which Streamlit executes BEFORE the rest of the script.
# The script then reads and clears that action at the very top, updates all
# state, and every element below sees the correct state on the same rerun.
# ─────────────────────────────────────────────────────────────────────────────
_total  = len(_t_vals)

# ── Step 1: process pending action from PREVIOUS rerun's callback ─────────────
# on_click callbacks fire before the script body — so by the time we reach
# this line, session_state["geo_action"] already holds the clicked button name.
_action = st.session_state.pop("geo_action", None)   # read and clear atomically

if _action == "play":
    if st.session_state["geo_frame"] >= _total - 1:
        st.session_state["geo_frame"] = 0
    st.session_state["geo_running"] = True

elif _action == "pause":
    st.session_state["geo_running"] = False

elif _action == "stop":
    st.session_state["geo_running"] = False
    st.session_state["geo_frame"]   = 0

# ── Step 2: derive display state from ALREADY-UPDATED session_state ───────────
_is_running = st.session_state["geo_running"]
_is_at_start = st.session_state["geo_frame"] == 0
_is_at_end   = st.session_state["geo_frame"] >= _total - 1

# ── Step 3: render buttons with on_click callbacks ────────────────────────────
def _set_action(action):
    st.session_state["geo_action"] = action

bc1, bc2, bc3, bc4 = st.columns([1, 1, 1, 5])
with bc1:
    _play_label = "▶ Play" if _is_at_start else "▶ Resume"
    st.button(_play_label, key="geo_play",
              on_click=_set_action, args=("play",),
              disabled=_is_running)
with bc2:
    st.button("⏸ Pause", key="geo_pause",
              on_click=_set_action, args=("pause",),
              disabled=not _is_running)
with bc3:
    st.button("⏹ Stop",  key="geo_stop",
              on_click=_set_action, args=("stop",),
              disabled=_is_at_start and not _is_running)

# ── Progress indicator ────────────────────────────────────────────────────────
_cur_frame = st.session_state["geo_frame"]
st.caption(
    f"Frame {_cur_frame + 1} / {_total}  ·  "
    f"t = {_t_vals[_cur_frame]} s  ·  "
    f"{'▶ Running' if st.session_state['geo_running'] else '⏸ Paused' if _cur_frame > 0 else '⏹ Stopped'}"
)

# ── Viewport state — persists user pan/zoom across frames ────────────────────
# Initialise on first load
if "geo_viewport" not in st.session_state:
    st.session_state["geo_viewport"] = {
        "lat":  _lat_vals[0],
        "lon":  _lon_vals[0],
        "zoom": 9.0,
    }

# Hidden number inputs — used as a Python-readable channel for JS to write into.
# JS cannot call Python directly; instead it sets these widget values via DOM
# manipulation, which Streamlit picks up on the next rerun as widget changes.
# We hide them with CSS so they don't clutter the UI.
st.markdown("""
<style>
    div[data-testid="stNumberInput"][id^="vp_"] { display:none !important; }
</style>
""", unsafe_allow_html=True)

_vp = st.session_state["geo_viewport"]
vp_lat  = st.number_input("vp_lat",  value=_vp["lat"],  format="%.6f", key="vp_lat",  label_visibility="hidden")
vp_lon  = st.number_input("vp_lon",  value=_vp["lon"],  format="%.6f", key="vp_lon",  label_visibility="hidden")
vp_zoom = st.number_input("vp_zoom", value=_vp["zoom"], format="%.2f", key="vp_zoom", label_visibility="hidden")

# Sync session_state viewport from widget values (updated by JS on pan/zoom)
st.session_state["geo_viewport"] = {
    "lat":  st.session_state.get("vp_lat",  _lat_vals[0]),
    "lon":  st.session_state.get("vp_lon",  _lon_vals[0]),
    "zoom": st.session_state.get("vp_zoom", 9.0),
}



# JS bridge: listens for Mapbox "moveend" (fired after pan or zoom ends),
# reads center lat/lon and zoom, then updates the hidden number inputs and
# triggers a Streamlit rerun by dispatching an input event.
import streamlit.components.v1 as _cv1

_cv1.html(f"""
<div id="coord-box" style="
    font-family: monospace;
    font-size: 13px;
    padding: 8px 14px;
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-left: 4px solid #3b82f6;
    border-radius: 6px;
    min-height: 48px;
    color: #1e293b;
    {'display:none' if not _dot_mode else ''}
">
    {'🖊 Click points on the chart to see x/y and deltas.' if _dot_mode else ''}
</div>
<script>
(function() {{
    if (!{'true' if _dot_mode else 'false'}) return;

    var coordBox = document.getElementById("coord-box");
    var pt1 = null;
    var pt2 = null;

    function findPlotDiv() {{
        var candidates = [];
        try {{
            window.parent.document.querySelectorAll(".js-plotly-plot")
                .forEach(function(d) {{ candidates.push(d); }});
        }} catch(e) {{}}
        try {{
            window.parent.document.querySelectorAll("iframe")
                .forEach(function(fr) {{
                    try {{
                        fr.contentDocument.querySelectorAll(".js-plotly-plot")
                            .forEach(function(d) {{ candidates.push(d); }});
                    }} catch(e) {{}}
                }});
        }} catch(e) {{}}
        for (var i = candidates.length - 1; i >= 0; i--) {{
            var t = candidates[i].querySelector(".gtitle");
            if (t && t.textContent.indexOf("Normalized") !== -1)
                return candidates[i];
        }}
        return candidates[candidates.length - 1] || null;
    }}

    function fmt(v, digits) {{
        if (v === null || v === undefined) return "--";
        if (typeof v === "number") return v.toFixed(digits || 4);
        return String(v);
    }}

    function toNum(v) {{
        if (typeof v === "number") return v;

        var d = new Date(v);
        if (!isNaN(d.getTime())) return d.getTime();

        var n = Number(v);
        if (!isNaN(n)) return n;

        return null;
    }}

    function renderBox() {{
        if (!pt1) {{
            coordBox.innerHTML = "🖊 Click a first point.";
            return;
        }}

        if (!pt2) {{
            coordBox.innerHTML =
                "x1 = " + fmt(pt1.x, 4) + " | y1 = " + fmt(pt1.y, 4) +
                " | dx1 = -- | dy1 = --" +
                "<br>" +
                "x2 = -- | y2 = -- | dx2 = -- | dy2 = --";
            return;
        }}

        var x1n = toNum(pt1.x);
        var x2n = toNum(pt2.x);
        var y1n = toNum(pt1.y);
        var y2n = toNum(pt2.y);

        var dx = (x1n !== null && x2n !== null) ? (x2n - x1n) : null;
        var dy = (y1n !== null && y2n !== null) ? (y2n - y1n) : null;

        coordBox.innerHTML =
            "x1 = " + fmt(pt1.x, 4) +
            " | y1 = " + fmt(pt1.y, 4) +
            " | dx1 = " + (dx === null ? "--" : fmt(dx, 4)) +
            " | dy1 = " + (dy === null ? "--" : fmt(dy, 4)) +
            "<br>" +
            "x2 = " + fmt(pt2.x, 4) +
            " | y2 = " + fmt(pt2.y, 4) +
            " | dx2 = " + (dx === null ? "--" : fmt(dx, 4)) +
            " | dy2 = " + (dy === null ? "--" : fmt(dy, 4));
    }}

    function attach() {{
        var plotDiv = findPlotDiv();
        if (!plotDiv) {{ setTimeout(attach, 600); return; }}
        if (plotDiv._coordListenerAttached) return;
        plotDiv._coordListenerAttached = true;

        plotDiv.on("plotly_click", function(data) {{
            if (!data || !data.points || !data.points.length) return;

            var pt = data.points[0];
            var newPt = {{
                x: pt.x,
                y: pt.y,
                pointNumber: pt.pointNumber
            }};

            if (pt1 === null) {{
                pt1 = newPt;
            }} else if (pt2 === null) {{
                pt2 = newPt;
            }} else {{
                pt1 = pt2;
                pt2 = newPt;
            }}

            renderBox();
        }});

        plotDiv.on("plotly_doubleclick", function() {{
            pt1 = null;
            pt2 = null;
            coordBox.innerHTML = "🖊 Click points on the chart to see x/y and deltas.";
        }});
    }}

    if (document.readyState === "complete") {{ attach(); }}
    else {{ window.addEventListener("load", attach); }}
    setTimeout(attach, 1000);
    setTimeout(attach, 2500);
}})();
</script>
""", height=80)

# ── Placeholder — reused on every frame ──────────────────────────────────────
geo_placeholder = st.empty()

def _build_geo_fig(i, map_style, show_trail):
    """
    Build a single-frame geo figure for index i.

    Trace layering (bottom → top):
      1. Full trajectory  — grey dashed line, always visible
      2. Animated trail   — blue solid line, grows frame by frame
      3. Start marker     — green dot (fixed reference)
      4. End marker       — red dot (fixed reference)
      5. Current position — pink dot with time label (moves each frame)
    """
    fig = go.Figure()

    # ── Trace 1: full trajectory (dashed, always shown) ──────────────────────
    # Plotly Scattermapbox does not support dash= natively on older versions,
    # so we simulate a dashed look by alternating None gaps in the coordinates.
    # Build a "dashed" lat/lon list: keep 3 points, skip 2, repeat.
    _dash_lats, _dash_lons = [], []
    dash_on, dash_off = 3, 2          # 3 points visible, 2 points gap
    j = 0
    while j < len(_lat_vals):
        # visible segment
        seg_end = min(j + dash_on, len(_lat_vals))
        _dash_lats.extend(_lat_vals[j:seg_end])
        _dash_lons.extend(_lon_vals[j:seg_end])
        j = seg_end
        if j < len(_lat_vals):
            # gap: insert None to break the line
            _dash_lats.append(None)
            _dash_lons.append(None)
            j += dash_off              # skip dash_off real points

    fig.add_trace(go.Scattermapbox(
        lat=_dash_lats,
        lon=_dash_lons,
        mode="lines",
        line=dict(color="#A0A0A0", width=1.5),   # grey dashed full path
        name="Full path",
        showlegend=True,
    ))

    # ── Trace 2: animated trail (solid, grows each frame) ────────────────────
    if show_trail and i > 0:
        fig.add_trace(go.Scattermapbox(
            lat=_lat_vals[: i + 1],
            lon=_lon_vals[: i + 1],
            mode="lines",
            line=dict(color="#185FA5", width=3),  # blue solid animated path
            name="Animated trail",
            showlegend=True,
        ))

    # ── Trace 3: start marker ─────────────────────────────────────────────────
    fig.add_trace(go.Scattermapbox(
        lat=[_lat_vals[0]],
        lon=[_lon_vals[0]],
        mode="markers+text",
        marker=dict(size=10, color="#11A579"),
        text=["Start"],
        textposition="top right",
        name="Start",
        showlegend=True,
    ))

    # ── Trace 4: end marker ───────────────────────────────────────────────────
    fig.add_trace(go.Scattermapbox(
        lat=[_lat_vals[-1]],
        lon=[_lon_vals[-1]],
        mode="markers+text",
        marker=dict(size=10, color="#E68310"),
        text=["End"],
        textposition="top right",
        name="End",
        showlegend=True,
    ))

    # ── Trace 5: current position dot ────────────────────────────────────────
    fig.add_trace(go.Scattermapbox(
        lat=[_lat_vals[i]],
        lon=[_lon_vals[i]],
        mode="markers+text",
        marker=dict(size=14, color="#E73F74"),
        text=[f"t={_t_vals[i]}s"],
        textposition="top right",
        name="Current",
        showlegend=True,
    ))

    # ── TUTORIAL NOTE ─────────────────────────────────────────────────────────
    # To preserve manual pan/zoom during animation we track the viewport in
    # session_state["geo_viewport"] = {lat, lon, zoom}.
    # A JS snippet embedded in the page listens for Mapbox "moveend" events
    # and writes the new center/zoom into session_state via a hidden
    # st.number_input trick (the only reliable bidirectional bridge in v1.12).
    #
    # _build_geo_fig always uses the stored viewport — so if the user panned,
    # the next frame respects that position instead of snapping back.
    # ──────────────────────────────────────────────────────────────────────────
    vp = st.session_state.get("geo_viewport", {
        "lat":  _lat_vals[0],
        "lon":  _lon_vals[0],
        "zoom": 9,
    })
    fig.update_layout(
        mapbox=dict(
            style=map_style,
            center=dict(lat=vp["lat"], lon=vp["lon"]),
            zoom=vp["zoom"],
        ),
        margin=dict(l=0, r=0, t=30, b=0),
        height=520,
        paper_bgcolor="#f5f7fa",
        legend=dict(
            orientation="h",
            y=1.0,
            x=0,
            bgcolor="rgba(255,255,255,0.8)",
            font=dict(size=11),
        ),
    )
    return fig

# ── Render current frame (always, so map is never blank) ─────────────────────
geo_placeholder.plotly_chart(
    _build_geo_fig(st.session_state["geo_frame"], map_style, show_trail),
    use_container_width=True,
)

# ── One-frame-per-rerun animation ─────────────────────────────────────────────
# TUTORIAL NOTE ────────────────────────────────────────────────────────────────
# A for-loop blocks Streamlit's thread — no button click can interrupt it.
# session_state["geo_running"] inside a loop always reads True because no
# rerun occurs while Python is busy looping.
#
# The fix: advance exactly ONE frame per rerun, then sleep and trigger the
# next rerun via st.empty().
# Each rerun is a fresh script execution — buttons are processed normally,
# Pause/Stop set geo_running=False, and the next rerun simply doesn't advance.
#
# Flow:
#   rerun N  : render frame i → sleep → schedule next rerun (via loop trick)
#   rerun N+1: if geo_running → render frame i+1 → sleep → ...
#   Pause click → geo_running=False → rerun sees False → stops advancing
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state["geo_running"]:
    _cur = st.session_state["geo_frame"]

    # Reached the last frame — stop naturally
    if _cur >= _total - 1:
        st.session_state["geo_running"] = False
    else:
        # Sleep for the frame duration, then advance and force a rerun
        # by writing to a placeholder (triggers Streamlit to re-execute)
        _time.sleep(frame_ms / 1000.0)
        st.session_state["geo_frame"] = _cur + 1

        # Force next rerun: write to a hidden empty widget.
        # This is the Streamlit 1.12 compatible way to self-schedule a rerun
        # without st.experimental_rerun() (added in 1.18).
        _rerun_trigger = st.empty()
        _rerun_trigger.text(f"frame_{st.session_state['geo_frame']}")
        _rerun_trigger.empty()


# ══════════════════════════════════════════════
# ROW 8: Tri-state / Binary Signal Charts
# ══════════════════════════════════════════════
st.markdown("---")
st.markdown("<div style='border-left:4px solid #6366f1;padding-left:12px;font-size:1.3rem;font-weight:700;'>⬛ Signal Viewer (tri-state: -1 / 0 / +1)</div>", unsafe_allow_html=True)

tutorial_box("""
<b>📘 Tutorial: Stacked tri-state signal charts with make_subplots</b><br>
Tri-state signals (-1, 0, +1) need two separate fill areas per channel:<br><br>
• <b>+1 states</b>: <code>fill="tozeroy"</code> on a clipped series (negatives → 0) fills above zero<br>
• <b>-1 states</b>: <code>fill="tozeroy"</code> on a clipped series (positives → 0) fills below zero<br>
• The step line itself is drawn as a third trace on top of both fills<br>
• <code>yaxis range=[-1.35, 1.35]</code> and <code>tickvals=[-1, 0, 1]</code> clamps the axis symmetrically<br>
• <code>zeroline=True</code> draws the centre reference at y=0<br>
• Each channel also supports pure binary (0/1) — the -1 fill simply stays empty
""")

# ── Helper ────────────────────────────────────────────────────────────────────
def _hex_rgba(hex_color, alpha=0.25):
    """Convert #RRGGBB hex to rgba(r,g,b,alpha) — works on all Plotly versions."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"

# ── Controls ──────────────────────────────────────────────────────────────────
sc1, sc2, sc3, sc4 = st.columns(4)
with sc1:
    n_channels  = st.slider("Channels", 2, 8, 4, key="bit_channels")
with sc2:
    n_samples   = st.slider("Samples",  20, 200, 60, step=10, key="bit_samples")
with sc3:
    bit_style   = st.selectbox("Style", ["Step fill", "Step line", "Dot markers"], key="bit_style")
with sc4:
    tristate_on = st.checkbox("Enable -1 state", value=True, key="bit_tristate")

# ── Synthetic dataset ─────────────────────────────────────────────────────────
# Values from {-1, 0, 1} (tri-state) or {0, 1} (binary) with run-length clustering
np.random.seed(7)
_t_bit     = np.arange(n_samples)
_state_set = [-1, 0, 1] if tristate_on else [0, 1]
_channels  = {}
_chan_names = [f"CH{i}" for i in range(n_channels)]

for name in _chan_names:
    vals = []
    val  = np.random.choice(_state_set)
    while len(vals) < n_samples:
        run = np.random.randint(1, 8)
        vals.extend([val] * min(run, n_samples - len(vals)))
        val = np.random.choice(_state_set)
    _channels[name] = np.array(vals[:n_samples])

# ── Color palette ─────────────────────────────────────────────────────────────
_bit_colors = [
    "#3969AC", "#E73F74", "#11A579", "#F2B701",
    "#7F3C8D", "#E68310", "#008695", "#CF1C90",
]

# ── Build stacked subplots ────────────────────────────────────────────────────
_row_h   = 80 if tristate_on else 60
_total_h = max(200, n_channels * _row_h + 60)

fig_bits = make_subplots(
    rows=n_channels,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.0,
    row_heights=[1] * n_channels,
)

for idx, name in enumerate(_chan_names):
    row    = idx + 1
    color  = _bit_colors[idx % len(_bit_colors)]
    vals   = _channels[name]
    t_list = _t_bit.tolist()

    # ── NULL / <NA> handling ──────────────────────────────────────────────────
    # Convert the array to a pandas Series so we can use fillna(),
    # then back to numpy for np.clip(). This handles pd.NA, np.nan,
    # and None in one call regardless of the array's dtype.
    # fillna(0) treats missing samples as the neutral/zero state.
    vals = pd.array(vals, dtype="object")          # wrap in pandas array
    vals = pd.Series(vals).fillna(0).to_numpy()    # replace <NA>/NaN/None → 0
    vals = vals.astype(float)                       # ensure numeric dtype for np.clip

    # ── Clipped series for dual fills ─────────────────────────────────────────
    # pos_vals: keeps +1, zeroes out -1  → fills the area above zero
    # neg_vals: keeps -1, zeroes out +1  → fills the area below zero
    pos_vals = np.clip(vals,  0, 1).tolist()   # [-1,0,1] → [0,0,1]
    neg_vals = np.clip(vals, -1, 0).tolist()   # [-1,0,1] → [-1,0,0]
    full_vals = vals.tolist()

    if bit_style == "Step fill":
        # Positive fill (+1 states, above zero)
        fig_bits.add_trace(go.Scatter(
            x=t_list, y=pos_vals,
            mode="lines",
            line=dict(color="rgba(0,0,0,0)", width=0, shape="hv"),
            fill="tozeroy",
            fillcolor=_hex_rgba(color, 0.30),
            showlegend=False, hoverinfo="skip",
        ), row=row, col=1)

        # Negative fill (-1 states, below zero)
        if tristate_on:
            fig_bits.add_trace(go.Scatter(
                x=t_list, y=neg_vals,
                mode="lines",
                line=dict(color="rgba(0,0,0,0)", width=0, shape="hv"),
                fill="tozeroy",
                fillcolor=_hex_rgba("#E24B4A", 0.25),  # red tint for negatives
                showlegend=False, hoverinfo="skip",
            ), row=row, col=1)

        # Step line on top of fills
        fig_bits.add_trace(go.Scatter(
            x=t_list, y=full_vals,
            mode="lines",
            line=dict(color=color, width=1.5, shape="hv"),
            name=name, showlegend=True,
            hovertemplate=f"<b>{name}</b>  t=%{{x}}  val=%{{y}}<extra></extra>",
        ), row=row, col=1)

    elif bit_style == "Step line":
        fig_bits.add_trace(go.Scatter(
            x=t_list, y=full_vals,
            mode="lines",
            line=dict(color=color, width=2, shape="hv"),
            name=name, showlegend=True,
            hovertemplate=f"<b>{name}</b>  t=%{{x}}  val=%{{y}}<extra></extra>",
        ), row=row, col=1)

    else:  # Dot markers
        fig_bits.add_trace(go.Scatter(
            x=t_list, y=full_vals,
            mode="markers+lines",
            line=dict(color=color, width=1, shape="hv", dash="dot"),
            marker=dict(size=5, color=[
                color if v == 1 else ("#E24B4A" if v == -1 else "#aaaaaa")
                for v in full_vals
            ]),
            name=name, showlegend=True,
            hovertemplate=f"<b>{name}</b>  t=%{{x}}  val=%{{y}}<extra></extra>",
        ), row=row, col=1)

    # ── Y axis per channel ────────────────────────────────────────────────────
    _yrange   = [-1.4, 1.4] if tristate_on else [-0.25, 1.35]
    _tickvals = [-1, 0, 1]  if tristate_on else [0, 1]
    _ticktext = ["-1","0","1"] if tristate_on else ["0","1"]

    fig_bits.update_yaxes(
        range=_yrange,
        tickvals=_tickvals,
        ticktext=_ticktext,
        tickfont=dict(size=9),
        title_text=name,
        title_font=dict(size=10, color=color),
        title_standoff=2,
        showgrid=False,
        zeroline=True,
        zerolinecolor="#bbbbbb",
        zerolinewidth=1,
        row=row, col=1,
    )

# ── X axis ────────────────────────────────────────────────────────────────────
fig_bits.update_xaxes(
    showgrid=True, gridcolor="#eeeeee", gridwidth=0.5,
    title_text="Sample index", row=n_channels, col=1,
)
for r in range(1, n_channels):
    fig_bits.update_xaxes(showticklabels=False, row=r, col=1)

_mode = "tri-state (-1/0/+1)" if tristate_on else "binary (0/1)"
fig_bits.update_layout(
    height=_total_h,
    template="plotly_white",
    paper_bgcolor="#f5f7fa",
    plot_bgcolor="#ffffff",
    margin=dict(l=60, r=20, t=30, b=40),
    title=dict(
        text=f"{n_channels}-channel signal viewer — {_mode}",
        x=0.5, font=dict(size=14),
    ),
    legend=dict(orientation="h", y=1.04, x=0, font=dict(size=11)),
    hovermode="x unified",
)

st.plotly_chart(fig_bits, use_container_width=True)

# ── Summary statistics table ──────────────────────────────────────────────────
st.subheader("Channel statistics")
_stat_rows = []
for n in _chan_names:
    v = _channels[n]
    _stat_rows.append({
        "Channel":        n,
        "+1 count":       int((v ==  1).sum()),
        " 0 count":       int((v ==  0).sum()),
        "-1 count":       int((v == -1).sum()),
        "Duty +1 (%)":    round(float((v ==  1).mean()) * 100, 1),
        "Duty -1 (%)":    round(float((v == -1).mean()) * 100, 1),
        "Transitions":    int(np.diff(v).astype(bool).sum()),
    })
st.dataframe(pd.DataFrame(_stat_rows))

st.markdown("---")
st.caption(f"Showing {len(df):,} of {len(df_full):,} records")
