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


def interpret_chart_x(series, interpretation):
    if interpretation == 'Numeric':
        return pd.to_numeric(series, errors='coerce')
    if interpretation == 'Datetime':
        numeric = pd.to_numeric(series, errors='coerce')
        present = numeric.dropna()
        if (not present.empty and present.between(1000, 9999).all()
                and present.mod(1).eq(0).all()):
            # Four-digit numeric fields represent calendar years rather than epoch nanoseconds.
            return pd.to_datetime(numeric.astype('Int64').astype('string'), format='%Y', errors='coerce')
        try:
            return pd.to_datetime(series, errors='coerce', dayfirst=True)
        except ValueError as error:
            if "Mixed timezones" not in str(error):
                raise
            return pd.to_datetime(series, errors='coerce', dayfirst=True, utc=True)
    return series
