"""Schema-independent exploration without loading unselected CSV fields."""
import pandas as pd
import plotly.express as px
import streamlit as st
from framework.state import ui
from framework.analysis import filter_range, aggregate, reduce_points
from framework.config import MAX_PREVIEW, MAX_POINTS
from utils import inject_css, require_data

st.set_page_config(page_title='Engineering Explorer', layout='wide')
st = ui(__file__)
inject_css()
st.title('Engineering Explorer')
st.divider()
st.subheader("Grouping for statistics")
df = require_data()
columns = list(df.columns)
num = df.select_dtypes(include='number').columns.tolist()
if num:
    # Keep the related aggregation inputs on one row so editable controls read as
    # one compact section against the shared light-grey application background.
    group_control, value_control, aggregation_control = st.columns([2, 1, 1])
    with group_control:
        group = st.multiselect('Group by', columns)
    with value_control:
        metric = st.selectbox('Value field', num)
    with aggregation_control:
        operation = st.selectbox('Aggregation', ['sum', 'mean', 'count', 'min', 'max', 'median'])
    if metric in group:
        st.info('Choose a value field that is not also a grouping field.')
    elif group:
        result = aggregate(df, group, metric, operation)
        st.dataframe(result.head(MAX_PREVIEW))

    st.divider()

    st.subheader("Dynamic chart")
    x = st.selectbox('Time - X field', columns)
    xtype = st.radio('X interpretation', ['Original', 'Numeric', 'Datetime'])
    y = st.multiselect('Trend - Y field/s (only numeric fields)', num, default=[metric])
    kind = st.radio('Chart type', ['Line', 'Scatter'])
    chart = df[list(dict.fromkeys([x] + y))].copy()
    if xtype == 'Numeric':
        chart[x] = pd.to_numeric(chart[x], errors='coerce')
    elif xtype == 'Datetime':
        numeric_x = pd.to_numeric(chart[x], errors='coerce')
        year_like = (
            numeric_x.notna().any()
            and numeric_x.dropna().between(1000, 9999).all()
            and numeric_x.dropna().mod(1).eq(0).all()
        )
        if year_like:
            # Four-digit numeric fields represent calendar years; pandas otherwise
            # interprets them as nanoseconds after the Unix epoch.
            chart[x] = pd.to_datetime(
                numeric_x.astype('Int64').astype('string'),
                format='%Y',
                errors='coerce',
            )
        else:
            chart[x] = pd.to_datetime(chart[x], errors='coerce', dayfirst=True)
    if xtype != 'Original' and chart[x].isna().any():
        st.caption('Rows with invalid X values are excluded from the chart.')
        chart = chart.dropna(subset=[x])
    if xtype != 'Original' and not chart.empty:
        low, high = chart[x].min(), chart[x].max()
        if low < high:
            if xtype == 'Datetime':
                low, high = low.to_pydatetime(), high.to_pydatetime()
            else:
                low, high = float(low), float(high)
            if low < high:
                # Numeric and datetime sliders need separate persisted identities;
                # otherwise a previous float range is compared with datetime bounds.
                bounds = st.slider(
                    'Chart X range',
                    low,
                    high,
                    (low, high),
                    key=f'chart_x_range:{x}:{xtype}',
                )
                chart = filter_range(chart, x, *bounds)
    if len(chart) > MAX_POINTS:
        st.caption(f'Chart reduced deterministically to {MAX_POINTS:,} points per trace; aggregates use all matching rows.')
    chart = reduce_points(chart, MAX_POINTS)
    if y:
        st.plotly_chart((px.line if kind == 'Line' else px.scatter)(chart, x=x, y=y))
    st.divider()
