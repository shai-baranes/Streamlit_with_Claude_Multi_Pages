"""Pure preparation and playback helpers for dataset-backed trajectories."""

from dataclasses import dataclass
import hashlib

import numpy as np
import pandas as pd


TRAJECTORY_COLUMNS = ("Seconds", "longitude", "latitude", "Altitude")


@dataclass(frozen=True)
class PreparedTrajectory:
    """Validated trajectory samples and preparation details for the UI."""

    frame: pd.DataFrame
    source_rows: int
    invalid_rows: int
    reduced: bool


def missing_trajectory_columns(frame: pd.DataFrame) -> list[str]:
    """Return required trajectory fields that are absent from a dataset."""

    return [column for column in TRAJECTORY_COLUMNS if column not in frame.columns]


def prepare_trajectory(frame: pd.DataFrame, max_frames: int = 300) -> PreparedTrajectory:
    """Validate, time-sort, and deterministically reduce trajectory records."""

    missing = missing_trajectory_columns(frame)
    if missing:
        raise ValueError("Missing trajectory fields: " + ", ".join(missing))
    if max_frames < 2:
        raise ValueError("max_frames must be at least 2.")

    source_rows = len(frame)
    prepared = frame.loc[:, TRAJECTORY_COLUMNS].copy()
    for column in TRAJECTORY_COLUMNS:
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    valid = prepared.notna().all(axis=1)
    valid &= prepared["longitude"].between(-180, 180)
    valid &= prepared["latitude"].between(-90, 90)
    prepared = prepared.loc[valid]
    # Mergesort preserves source order for records with the same elapsed time.
    prepared = prepared.sort_values("Seconds", kind="mergesort").reset_index(drop=True)
    invalid_rows = source_rows - len(prepared)

    reduced = len(prepared) > max_frames
    if reduced:
        # Linspace retains both route endpoints while distributing frames uniformly.
        positions = np.linspace(0, len(prepared) - 1, max_frames, dtype=int)
        prepared = prepared.iloc[positions].reset_index(drop=True)

    return PreparedTrajectory(prepared, source_rows, invalid_rows, reduced)


def trajectory_identity(frame: pd.DataFrame, dataset_version: str | None = None) -> str:
    """Return a stable identity used to reset playback after dataset replacement."""

    if dataset_version:
        return str(dataset_version)
    missing = missing_trajectory_columns(frame)
    if missing:
        return "missing:" + ",".join(missing)
    hashed = pd.util.hash_pandas_object(
        frame.loc[:, TRAJECTORY_COLUMNS], index=True
    ).values.tobytes()
    return hashlib.sha256(hashed).hexdigest()


def advance_frame(index: int, frame_count: int) -> tuple[int, bool]:
    """Advance one frame and report whether playback reached the endpoint."""

    if frame_count <= 0:
        return 0, True
    next_index = min(max(index, 0) + 1, frame_count - 1)
    return next_index, next_index == frame_count - 1
