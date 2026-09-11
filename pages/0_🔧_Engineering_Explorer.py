"""Schema-independent exploration without loading unselected CSV fields."""
import pandas as pd
import plotly.express as px
import streamlit as st
from framework.state import ui
from framework.analysis import filter_values, filter_range, aggregate, reduce_points, transitions
from framework.config import MAX_PREVIEW, MAX_POINTS
from utils import require_data

st.set_page_config(page_title='Engineering Explorer', layout='wide')
st = ui(__file__)
st.title('Engineering Explorer')
df = require_data()
columns = list(df.columns)
filter_cols = st.multiselect('Filter fields', columns)
for column in filter_cols:
    values = df[column]
    if pd.api.types.is_numeric_dtype(values) and values.notna().any():
        low, high = float(values.min()), float(values.max())
        if low < high:
            bounds = st.slider(f'{column} range', low, high, (low, high))
            df = filter_range(df, column, *bounds)
    else:
        # Search before enumerating categories to keep very high cardinalities usable.
        search = st.text_input(f'Search {column} values')
        candidates = values.dropna().astype(str)
        if search:
            candidates = candidates[candidates.str.contains(search, regex=False)]
        choices = candidates.drop_duplicates().head(1000).tolist()
        selected = st.multiselect(f'{column} values (first 1,000 matches)', choices)
        if selected:
            df = df[df[column].astype(str).isin(selected)]
st.caption(f'{len(df):,} matching rows')
display = st.multiselect('Display fields', columns, default=columns[:min(10, len(columns))])
mode = st.radio('Table mode', ['Full', 'Stacked by Left', 'Stacked by All'])
view = df[display]
if display and mode != 'Full':
    view = transitions(view, display[:1] if mode == 'Stacked by Left' else display)
rows = st.number_input('Preview rows', min_value=1, max_value=MAX_PREVIEW, value=min(200, MAX_PREVIEW))
st.dataframe(view.head(rows))
if st.button('Prepare filtered CSV'):
    st.download_button('Download filtered CSV', df[display].to_csv(index=False).encode(), 'filtered.csv')
num = df.select_dtypes(include='number').columns.tolist()
if num:
    group = st.multiselect('Group by', columns)
    metric = st.selectbox('Value field', num)
    operation = st.selectbox('Aggregation', ['sum', 'mean', 'count', 'min', 'max', 'median'])
    if metric in group:
        st.info('Choose a value field that is not also a grouping field.')
    elif group:
        result = aggregate(df, group, metric, operation)
        st.dataframe(result.head(MAX_PREVIEW))
    x = st.selectbox('Time / X field', columns)
    xtype = st.radio('X interpretation', ['Original', 'Numeric', 'Datetime'])
    y = st.multiselect('Trend fields', num, default=[metric])
    kind = st.radio('Chart type', ['Line', 'Scatter'])
    chart = df[list(dict.fromkeys([x] + y))].copy()
    if xtype == 'Numeric':
        chart[x] = pd.to_numeric(chart[x], errors='coerce')
    elif xtype == 'Datetime':
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
            bounds = st.slider('Chart X range', low, high, (low, high))
            chart = filter_range(chart, x, *bounds)
    if len(chart) > MAX_POINTS:
        st.caption(f'Chart reduced deterministically to {MAX_POINTS:,} points per trace; aggregates use all matching rows.')
    chart = reduce_points(chart, MAX_POINTS)
    if y:
        st.plotly_chart((px.line if kind == 'Line' else px.scatter)(chart, x=x, y=y))
