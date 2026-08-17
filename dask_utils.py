"""
Utility helpers for creating Dask DataFrames from arbitrary DataFrame-like inputs
with automatic `meta` inference.

This module provides:
- infer_meta_from_df(df): returns an empty pandas.DataFrame whose dtypes match `df`.
- generate_dask_df(df, npartitions=None, desired_partition_size=100_000, return_meta=True):
    converts a pandas DataFrame to a dask DataFrame, infers a sensible number of
    partitions by size (if not provided) and returns (ddf, meta) by default.

The inferred `meta` is useful when calling dask operations that require explicit
meta (for example, map_partitions, apply with unknown output dtypes, etc.)

Example:
    import streamlit as st
    import pandas as pd
    from dask_utils import generate_dask_df

    df = pd.read_csv("big.csv")
    ddf, meta = generate_dask_df(df)
    # use `ddf` for Dask computations; pass `meta` when a dask function needs it

"""

from typing import Tuple, Optional
import math

import pandas as pd

try:
    import dask.dataframe as dd
except Exception:  # pragma: no cover - dask may not be installed in minimal env
    dd = None


def infer_meta_from_df(df: pd.DataFrame) -> pd.DataFrame:
    """Infer and return an empty pandas DataFrame (meta) that matches the
    columns and dtypes of `df`.

    This does the same thing you'd normally want from reading df.info() but in
    programmatic form: an empty DataFrame with the correct dtypes. It preserves
    column dtypes and the index dtype/name.

    Args:
        df: A pandas DataFrame (or any object with `.dtypes` and `.iloc`).

    Returns:
        A pandas DataFrame with zero rows and the same columns/dtypes as `df`.
    """
    # If df is already empty, df.head(0) gives the right empty frame with dtypes
    try:
        meta = df.head(0).copy()
        # Ensure series dtypes are preserved even for object-like columns
        for col, dtype in df.dtypes.items():
            if col in meta and meta[col].dtype != dtype:
                meta[col] = pd.Series(dtype=dtype)
    except Exception:
        # Fallback: build from dtypes mapping
        meta_cols = {}
        for col, dtype in getattr(df, "dtypes", {}).items():
            meta_cols[col] = pd.Series(dtype=dtype)
        meta = pd.DataFrame(meta_cols)

    # Preserve index dtype/name if possible
    try:
        meta.index = df.index[:0]
    except Exception:
        # ignore if index can't be set
        pass

    return meta


def _suggest_npartitions(length: Optional[int], desired_partition_size: int) -> int:
    if length is None or length <= 0:
        return 1
    return max(1, math.ceil(length / float(desired_partition_size)))


def generate_dask_df(
    df,
    npartitions: Optional[int] = None,
    desired_partition_size: int = 100_000,
    return_meta: bool = True,
) -> Tuple["dd.DataFrame", pd.DataFrame]:
    """Create a Dask DataFrame from `df` and infer an appropriate `meta`.

    This function is intentionally permissive: if `df` is already a Dask
    DataFrame it is returned as-is (and its _meta is returned if return_meta).
    If `df` is a pandas DataFrame it will be partitioned into a sensible
    number of partitions (based on desired_partition_size) when npartitions is
    not provided.

    Args:
        df: pandas.DataFrame or dask.dataframe.DataFrame.
        npartitions: explicit number of partitions to use. If None, an estimate
            based on `desired_partition_size` and len(df) will be used.
        desired_partition_size: target number of rows per partition used when
            npartitions is not provided (default 100k rows).
        return_meta: if True return a tuple (ddf, meta). If False return only ddf.

    Returns:
        (ddf, meta) if return_meta else ddf. `meta` is an empty pandas DataFrame
        with the same columns and dtypes as the input `df`.

    Notes:
        - Dask can usually infer metadata from a pandas DataFrame passed to
          dd.from_pandas; `meta` is provided because many dask APIs (map_partitions,
          apply, etc.) require an explicit meta argument for safe execution.
        - For extremely large datasets that are not held in memory as a single
          pandas DataFrame, consider constructing a Dask DataFrame using
          read_csv/parquet or from_delayed and providing a meta produced by
          this helper.
    """
    if dd is None:
        raise RuntimeError("dask is not available; please install dask to use this helper")

    # If given a Dask DataFrame already
    if hasattr(df, "__dask_graph__") and hasattr(df, "_meta"):
        ddf = df
        meta = df._meta
        if return_meta:
            return ddf, meta
        return ddf

    # Expect pandas-like object
    if not hasattr(df, "dtypes") or not hasattr(df, "iloc"):
        raise TypeError("generate_dask_df expects a pandas-like DataFrame or a dask DataFrame")

    # Infer meta
    meta = infer_meta_from_df(df)

    # Determine npartitions if not provided
    if npartitions is None:
        try:
            length = len(df)
        except Exception:
            length = None
        npartitions = _suggest_npartitions(length, desired_partition_size)

    # Create Dask DataFrame
    ddf = dd.from_pandas(df, npartitions=npartitions)

    # ddf._meta should already be correct, but return the explicit meta as well
    if return_meta:
        return ddf, meta
    return ddf


# Small convenience wrapper for Streamlit usage
def generate_and_cache_dask_df(
    df,
    npartitions: Optional[int] = None,
    desired_partition_size: int = 100_000,
    cache_decorator=None,
    return_meta: bool = False,
):
    """Convenience wrapper that applies a caching decorator (e.g. streamlit.cache_data)
    if provided.

    By default this function returns only the Dask DataFrame (dd.DataFrame).
    Set return_meta=True to receive a tuple (ddf, meta).

    Example:
        import streamlit as st
        ddf = generate_and_cache_dask_df(df, cache_decorator=st.cache_data)
        ddf, meta = generate_and_cache_dask_df(df, cache_decorator=st.cache_data, return_meta=True)
    """
    # Ensure the underlying generator respects the return_meta flag
    def _make(npartitions, desired_partition_size):
        return generate_dask_df(df, npartitions=npartitions, desired_partition_size=desired_partition_size, return_meta=return_meta)

    if cache_decorator is not None:
        @cache_decorator
        def _inner(data_repr, npartitions, desired_partition_size):
            # `data_repr` is expected to be something hashable derived from df
            return _make(npartitions, desired_partition_size)

        # Use length and column names as a cheap cache key if df is not hashable
        data_repr = None
        try:
            data_repr = (len(df), tuple(df.columns))
        except Exception:
            data_repr = 0
        return _inner(data_repr, npartitions, desired_partition_size)

    return _make(npartitions, desired_partition_size)
