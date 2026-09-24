"""Pure operations used by generic engineering pages and regression tests."""
import numpy as np
import pandas as pd

def filter_values(frame, column, values):
    return frame[frame[column].isin(values)]

def filter_range(frame, column, low, high):
    return frame[frame[column].between(low, high)]

def aggregate(frame, groups, metric, operation):
    return frame.groupby(groups, dropna=False)[metric].agg(operation).reset_index()

def chronological_order(frame, column, numeric=False, secondary=None):
    """Return a stable chronological view without replacing source-row indexes."""
    primary = (
        pd.to_numeric(frame[column], errors='coerce')
        if numeric
        else pd.to_datetime(frame[column], errors='coerce', dayfirst=True)
    )
    ordered = frame.assign(__chronological_primary=primary)
    sort_columns = ['__chronological_primary']
    if secondary and secondary in frame.columns:
        # Seconds restores source chronology within repeated sample dates.
        ordered = ordered.assign(
            __chronological_secondary=pd.to_numeric(frame[secondary], errors='coerce')
        )
        sort_columns.append('__chronological_secondary')
    return ordered.sort_values(sort_columns, kind='stable', na_position='last').drop(
        columns=sort_columns
    )

def reduce_points(frame, limit):
    if len(frame) <= limit:
        return frame
    return frame.iloc[np.linspace(0, len(frame) - 1, limit, dtype=int)]

def transitions(frame, columns):
    previous = frame[columns].shift()
    changed = ~(frame[columns].eq(previous) | (frame[columns].isna() & previous.isna())).all(axis=1)
    if len(changed):
        changed.iloc[0] = True
    return frame.loc[changed]
