from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from framework.config import ALWAYS_LOAD_COLUMNS
from framework.data import load_projection
from framework.trajectory import (
    SECONDARY_TRAJECTORY_COLUMNS,
    advance_frame,
    missing_trajectory_columns,
    prepare_trajectory,
    trajectory_separation_meters,
    trajectory_identity,
)
import framework.terrain as terrain_module


ROOT = Path(__file__).resolve().parents[1]


def test_sample_trajectory_profile():
    frame = pd.read_csv(ROOT / "synthetic_sales_data.csv")
    assert len(frame) == 1_500
    assert len(frame.columns) == 29
    assert frame.columns.is_unique
    trajectory_columns = (
        "longitude", "latitude", "Altitude", *SECONDARY_TRAJECTORY_COLUMNS
    )
    assert set(trajectory_columns).issubset(ALWAYS_LOAD_COLUMNS)
    assert frame[["Seconds", *trajectory_columns]].notna().all().all()
    assert frame["Seconds"].tolist() == pytest.approx(
        [index * 0.5 for index in range(len(frame))]
    )
    assert frame["longitude"].between(34.6, 35.9).all()
    assert frame["latitude"].between(31.9, 33.5).all()
    assert frame["Altitude"].between(250, 12_500).all()
    # The synthetic profile climbs, cruises high, and finishes after a descent.
    assert frame.loc[400:1100, "Altitude"].median() > 10_000
    assert frame["Altitude"].iloc[-1] < frame.loc[750, "Altitude"]
    assert frame["longitude_2"].between(34.6, 35.9).all()
    assert frame["latitude_2"].between(31.9, 33.5).all()
    assert frame["altitude_2"].between(250, 12_800).all()
    # The second aircraft stays adjacent while its smooth lateral spacing changes.
    north_km = (frame["latitude_2"] - frame["latitude"]) * 111.32
    east_km = (
        (frame["longitude_2"] - frame["longitude"])
        * 111.32
        * np.cos(np.radians(frame["latitude"]))
    )
    separation_km = np.hypot(north_km, east_km)
    assert separation_km.between(1.0, 2.5).all()
    assert separation_km.max() - separation_km.min() > 0.8


def test_sample_power_states_follow_seconds_thresholds():
    frame = pd.read_csv(ROOT / "synthetic_sales_data.csv")
    thresholds = {"Power_1": 60, "Power_2": 70, "Power_3": 80, "Power_4": 90}
    assert set(thresholds).issubset(ALWAYS_LOAD_COLUMNS)
    for column, threshold in thresholds.items():
        # Each device transitions exactly once and remains powered thereafter.
        expected = np.where(frame["Seconds"] >= threshold, "ON", "OFF")
        assert frame[column].isin({"ON", "OFF"}).all()
        assert frame[column].tolist() == expected.tolist()


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


def test_preparation_keeps_complete_secondary_route_on_shared_frames():
    frame = pd.DataFrame(
        {
            "Seconds": [1, 0], "longitude": [35, 34], "latitude": [33, 32],
            "Altitude": [1000, 500], "longitude_2": [35.01, 34.01],
            "latitude_2": [32.99, 31.99], "altitude_2": [1100, 600],
        }
    )
    result = prepare_trajectory(frame)
    assert list(result.frame.columns) == [
        "Seconds", "longitude", "latitude", "Altitude", *SECONDARY_TRAJECTORY_COLUMNS
    ]
    assert result.frame["Seconds"].tolist() == [0, 1]
    assert result.frame["altitude_2"].tolist() == [600, 1100]
    separation = trajectory_separation_meters(result.frame)
    assert len(separation) == 2 and (separation > 0).all()


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


def test_warning_sleeve_uses_mesh_geometry():
    chart = (ROOT / "framework" / "trajectory_chart.py").read_text()
    assert 'type: "mesh3d"' in chart
    assert "Two triangles per segment" in chart
    assert '<select id="trajectory-fps">' in chart
    assert "current.Seconds.toFixed(1)} Seconds" in chart
    assert 'id="trajectory-route-1"' in chart and 'id="trajectory-route-2"' in chart
    assert 'id="trajectory-terrain"' in chart
    assert 'id="trajectory-play"' in chart and 'id="trajectory-pause"' in chart
    assert 'value="10">10 fps</option>' in chart
    assert "data.terrain && terrainToggle.checked" in chart
    assert "player.state.showTerrain" in chart
    assert 'data-attr="dragmode"' in chart
    assert ".modebar-btn.active" in chart
    assert '"scene.dragmode": false' in chart
    assert "scheduleStateSave" in chart
    assert 'name: "Demonstration terrain"' in chart


def test_demonstration_terrain_is_bounded_and_has_elevation_changes(monkeypatch):
    frame = load_projection(ROOT / "synthetic_sales_data.csv", ALWAYS_LOAD_COLUMNS)
    # Exercise terrain geometry independently from the operator-controlled feature flag.
    monkeypatch.setattr(terrain_module, "ENABLE_DEMO_TERRAIN", True)
    terrain = terrain_module.demonstration_terrain(frame, grid_size=12)
    assert terrain is not None
    longitude = np.asarray(terrain["longitude"])
    latitude = np.asarray(terrain["latitude"])
    altitude = np.asarray(terrain["altitude_km"])
    assert longitude.shape == latitude.shape == altitude.shape == (12, 12)
    assert longitude.min() < frame["longitude"].min()
    assert longitude.max() > frame["longitude_2"].max()
    assert altitude.min() >= 0
    assert altitude.max() - altitude.min() > 0.25
