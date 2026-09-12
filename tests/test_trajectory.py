from pathlib import Path

import pandas as pd
import pytest

from framework.config import ALWAYS_LOAD_COLUMNS
from framework.data import load_projection
from framework.trajectory import (
    advance_frame,
    missing_trajectory_columns,
    prepare_trajectory,
    trajectory_identity,
)


ROOT = Path(__file__).resolve().parents[1]


def test_sample_trajectory_profile():
    frame = pd.read_csv(ROOT / "synthetic_sales_data.csv")
    assert len(frame) == 1_500
    assert len(frame.columns) == 22
    assert frame.columns.is_unique
    assert {"longitude", "latitude", "Altitude"}.issubset(ALWAYS_LOAD_COLUMNS)
    assert frame[["Seconds", "longitude", "latitude", "Altitude"]].notna().all().all()
    assert frame["Seconds"].tolist() == pytest.approx(
        [index * 0.5 for index in range(len(frame))]
    )
    assert frame["longitude"].between(34.6, 35.9).all()
    assert frame["latitude"].between(31.9, 33.5).all()
    assert frame["Altitude"].between(250, 12_500).all()
    # The synthetic profile climbs, cruises high, and finishes after a descent.
    assert frame.loc[400:1100, "Altitude"].median() > 10_000
    assert frame["Altitude"].iloc[-1] < frame.loc[750, "Altitude"]


def test_preparation_coerces_sorts_filters_and_reduces():
    frame = pd.DataFrame(
        {
            "Seconds": [3, "1", 2, 4, 5],
            "longitude": [35, "34.8", 181, 35.2, 35.3],
            "latitude": [33, "32", 32.5, None, 33.2],
            "Altitude": [1000, "500", 800, 900, 1100],
        }
    )
    result = prepare_trajectory(frame, max_frames=2)
    assert result.source_rows == 5
    assert result.invalid_rows == 2
    assert result.reduced
    assert result.frame["Seconds"].tolist() == [1.0, 5.0]


def test_preparation_requires_fields_and_frame_capacity():
    with pytest.raises(ValueError, match="longitude"):
        prepare_trajectory(pd.DataFrame({"Seconds": [0]}))
    with pytest.raises(ValueError, match="at least 2"):
        prepare_trajectory(pd.DataFrame(columns=list(ALWAYS_LOAD_COLUMNS)), 1)
    assert missing_trajectory_columns(pd.DataFrame({"Seconds": []})) == [
        "longitude",
        "latitude",
        "Altitude",
    ]


def test_identity_and_playback_boundaries():
    frame = pd.DataFrame(
        {"Seconds": [0, 1], "longitude": [34, 35], "latitude": [32, 33], "Altitude": [0, 1]}
    )
    assert trajectory_identity(frame, "version-a") == "version-a"
    assert trajectory_identity(frame) != trajectory_identity(frame.assign(Altitude=[0, 2]))
    assert advance_frame(0, 2) == (1, True)
    assert advance_frame(1, 2) == (1, True)
    assert advance_frame(-4, 2) == (1, True)
    assert advance_frame(4, 0) == (0, True)


def test_sample_projection_keeps_trajectory_fields():
    frame = load_projection(ROOT / "synthetic_sales_data.csv", ALWAYS_LOAD_COLUMNS)
    assert list(frame.columns) == ALWAYS_LOAD_COLUMNS
