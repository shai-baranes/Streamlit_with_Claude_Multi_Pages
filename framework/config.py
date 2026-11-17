"""Deployment limits; environment overrides are read at process startup."""

import os
from pathlib import Path
import tempfile

ALWAYS_LOAD_COLUMNS = [
    "Date",
    "Year",
    "Quarter",
    "Month",
    "MonthNum",
    "Seconds",
    "Region",
    "Country",
    "Category",
    "Product",
    "Segment",
    "Channel",
    "Sales_Rep",
    "Revenue",
    "Units",
    "Cost",
    "Profit",
    "Margin_%",
    "Deal_Won",
    # Keep sample trajectory coordinates available without requiring an extra selection.
    "longitude",
    "latitude",
    "Altitude",
    # Load the optional second aircraft with the primary trajectory projection.
    "longitude_2",
    "latitude_2",
    "altitude_2",
    # Keep deterministic device states available for timeline demonstrations.
    "Power_1",
    "Power_2",
    "Power_3",
    "Power_4",
]
ROOT = Path(
    os.environ.get(
        "DASHBOARD_DATA_DIR", str(Path(tempfile.gettempdir()) / "engineering-dashboard")
    )
)
MAX_UPLOAD_MB = int(os.environ.get("DASHBOARD_MAX_UPLOAD_MB", "1024"))
MAX_FRAME_MB = int(os.environ.get("DASHBOARD_MAX_FRAME_MB", "1024"))
MAX_PREVIEW = int(os.environ.get("DASHBOARD_MAX_PREVIEW", "1000"))
MAX_POINTS = int(os.environ.get("DASHBOARD_MAX_POINTS", "10000"))
TTL_SECONDS = int(os.environ.get("DASHBOARD_TTL_SECONDS", "86400"))

MAX_PROCESS_MB = int(os.environ.get("DASHBOARD_MAX_PROCESS_MB", "24576"))
