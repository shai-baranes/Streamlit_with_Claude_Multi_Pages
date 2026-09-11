"""Pure operations used by generic engineering pages and regression tests."""
import numpy as np
import pandas as pd

def filter_values(frame, column, values):
    return frame[frame[column].isin(values)]

def filter_range(frame, column, low, high):
    return frame[frame[column].between(low, high)]

def aggregate(frame, groups, metric, operation):
    return frame.groupby(groups, dropna=False)[metric].agg(operation).reset_index()

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
