"""Standalone export adapter for a time-ordered route in the bundled region."""
import json
from pathlib import Path


def export_trajectory(report, samples, *, zoom, marker_size, frame_duration, show_points):
    """Export a frame with Time, Latitude and Longitude columns."""
    assets = Path(__file__).parent

    def payload():
        return json.dumps({
            "route": list(samples[["Time", "Latitude", "Longitude"]].itertuples(index=False, name=None)),
            "coast": json.loads((assets / "trajectory_coastline.json").read_text(encoding="utf-8")),
            "zoom": zoom,
            "markerSize": marker_size,
            "frameDuration": frame_duration,
            "showPoints": show_points,
        }, separators=(",", ":"), allow_nan=False)

    report.component(
        "renderTrajectory", payload,
        html="""
        <div class="trajectory-settings">
          <label>Zoom <span class="trajectory-value" aria-hidden="true"></span>
            <input data-control="zoom" type="range" min="6" max="15" step="1">
          </label>
          <label>Current marker size <span class="trajectory-value" aria-hidden="true"></span>
            <input data-control="marker" type="range" min="8" max="24" step="1">
          </label>
          <label>Frame duration (ms) <span class="trajectory-value" aria-hidden="true"></span>
            <input data-control="duration" type="range" min="100" max="1200" step="50">
          </label>
        </div>
        <label class="trajectory-points">
          <input data-control="points" type="checkbox"> Show all route points
        </label>
        <div class="trajectory-playback">
          <button type="button" data-control="play">Play</button>
          <button type="button" data-control="pause">Pause</button>
          <label>Step <span class="trajectory-value" aria-hidden="true"></span>
            <input data-control="step" type="range" min="0" step="1" value="0">
          </label>
        </div>
        <svg class="trajectory-map" tabindex="0" role="img"
             aria-label="Trajectory map. Use the arrow keys to pan and plus or minus to zoom.">
          <g class="trajectory-world">
            <rect class="trajectory-water"></rect>
            <path class="trajectory-land"></path>
            <polyline class="trajectory-route"></polyline>
            <polyline class="trajectory-traveled"></polyline>
          </g>
          <g class="trajectory-samples"></g>
          <circle class="trajectory-current"><title></title></circle>
          <text class="trajectory-time" aria-hidden="true"></text>
        </svg>
        <div class="trajectory-caption">
          <output class="trajectory-position" aria-live="off"></output>
          <small>Offline coastline · <span class="trajectory-credit"></span></small>
        </div>
        """,
        css="""
        .trajectory-settings {display:grid;gap:.75rem 1rem;
          grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
        .trajectory-settings label,.trajectory-playback label {min-width:0}
        .trajectory-value {font-variant-numeric:tabular-nums}
        .trajectory-settings input,.trajectory-playback input {display:block;width:100%;margin:0}
        .trajectory-points {display:inline-block;margin:.75rem 0}
        .trajectory-playback {display:flex;align-items:end;gap:.5rem;margin-bottom:.75rem}
        .trajectory-playback label {flex:1;margin-left:.5rem}
        .trajectory-playback button {font:inherit;padding:.3rem .7rem}
        .trajectory-map {display:block;width:100%;height:clamp(320px,60vh,600px);
          border:1px solid #a7bac4;border-radius:8px;background:#eef2f4;cursor:grab;touch-action:none}
        .trajectory-map:active {cursor:grabbing}
        .trajectory-water {fill:#dceef5}
        .trajectory-land {fill:#e7e9d9;fill-rule:evenodd}
        .trajectory-route,.trajectory-traveled {fill:none;stroke-linejoin:round;stroke-linecap:round;
          vector-effect:non-scaling-stroke}
        .trajectory-route {stroke:#727981;stroke-width:3}
        .trajectory-traveled {stroke:#1976d2;stroke-width:4}
        .trajectory-samples circle {fill:#37698f;stroke:white;stroke-width:1}
        .trajectory-current {fill:#0d47a1;stroke:white;stroke-width:2}
        .trajectory-time {font-weight:600;fill:#0d47a1;paint-order:stroke;stroke:white;stroke-width:3;
          pointer-events:none}
        .trajectory-caption {display:flex;flex-wrap:wrap;justify-content:space-between;
          align-items:baseline;gap:.25rem 1rem;margin-top:.35rem}
        .trajectory-position {font-variant-numeric:tabular-nums}
        """,
        js=(assets / "trajectory_export.js").read_text(encoding="utf-8"),
    )
