"""Deterministic demonstration terrain for the 3D trajectory player."""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# DEMONSTRATION TERRAIN TOGGLE
# Set this to False (or comment True and uncomment False) to remove the layer.
ENABLE_DEMO_TERRAIN = True
# ENABLE_DEMO_TERRAIN = False
# ---------------------------------------------------------------------------


def demonstration_terrain(route: pd.DataFrame, grid_size: int = 28) -> dict | None:
    """Build a bounded synthetic elevation grid around one or two flight routes."""

    if not ENABLE_DEMO_TERRAIN:
        return None
    if grid_size < 8:
        raise ValueError("grid_size must be at least 8.")

    longitude_columns = ["longitude"]
    latitude_columns = ["latitude"]
    if {"longitude_2", "latitude_2"}.issubset(route.columns):
        longitude_columns.append("longitude_2")
        latitude_columns.append("latitude_2")

    longitudes = route[longitude_columns].to_numpy(dtype=float)
    latitudes = route[latitude_columns].to_numpy(dtype=float)
    longitude_padding = max(0.035, (np.nanmax(longitudes) - np.nanmin(longitudes)) * 0.06)
    latitude_padding = max(0.035, (np.nanmax(latitudes) - np.nanmin(latitudes)) * 0.06)
    longitude_axis = np.linspace(
        np.nanmin(longitudes) - longitude_padding,
        np.nanmax(longitudes) + longitude_padding,
        grid_size,
    )
    latitude_axis = np.linspace(
        np.nanmin(latitudes) - latitude_padding,
        np.nanmax(latitudes) + latitude_padding,
        grid_size,
    )
    longitude_grid, latitude_grid = np.meshgrid(longitude_axis, latitude_axis)

    # Normalized coordinates keep the same terrain character for different route bounds.
    u = (longitude_grid - longitude_axis[0]) / (longitude_axis[-1] - longitude_axis[0])
    v = (latitude_grid - latitude_axis[0]) / (latitude_axis[-1] - latitude_axis[0])
    ridge = 360 * np.exp(-(((u - 0.68) / 0.18) ** 2 + ((v - 0.62) / 0.28) ** 2))
    foothills = 190 * np.exp(-(((u - 0.28) / 0.22) ** 2 + ((v - 0.36) / 0.20) ** 2))
    undulation = 38 * (np.sin(4 * np.pi * u) * np.cos(3 * np.pi * v) + 1)
    slope = 55 * v
    elevation_m = 35 + ridge + foothills + undulation + slope

    return {
        "longitude": longitude_grid.tolist(),
        "latitude": latitude_grid.tolist(),
        "altitude_km": (elevation_m / 1000).tolist(),
    }
