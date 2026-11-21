import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from framework.config import ALWAYS_LOAD_COLUMNS
from framework.data import load_dataset, load_projection
from framework.html_export import HtmlReport

ROOT = Path(__file__).resolve().parents[1]

# A second page exercises the public opt-in without registering individual charts.
SMALL_PAGE = """
import pandas as pd
import plotly.graph_objects as go
from framework.state import ui
from utils import tutorial_box
st = ui("small.py")
st = st.exportable_page(title="Small report")
name = st.selectbox("Group", ["First", 'Δ "</script>'])
left, right = st.columns(2)
left.metric("Direct metric", name)
with right:
    st.subheader("Context heading")
tutorial_box("<b>Shared tutorial</b>")
st.plotly_chart(go.Figure(go.Bar(x=[name], y=[2])))
st.dataframe(pd.DataFrame({"Label": [name], "Hidden": ["hidden sentinel"]}),
             column_config={"Hidden": None})
st.begin_export_exclusion()
tutorial_box("excluded sentinel")
st.end_export_exclusion()
st.finish_html_export()
"""


def collect_documents(monkeypatch):
    reports = []
    original = HtmlReport.document

    def collect(report):
        content = original(report)
        reports.append(content)
        return content

    monkeypatch.setattr(HtmlReport, "document", collect)
    return reports


def test_unused_export_never_starts_collection(monkeypatch):
    def unexpected_report(*args, **kwargs):
        raise AssertionError("Idle page created an export collector")

    monkeypatch.setattr(HtmlReport, "__init__", unexpected_report)
    app = AppTest.from_string(SMALL_PAGE).run()
    app.selectbox[0].select('Δ "</script>').run()
    assert not app.exception
    assert not app.download_button


def test_two_line_opt_in_and_isolated_sessions(monkeypatch, tmp_path):
    from utils import CSV_HEADER_PATTERNS

    reports = collect_documents(monkeypatch)
    stamped = tmp_path / "stamped.csv"
    stamped.write_text(
        "% version: 1.5\n% start time: 18:00:30.35\n% end time: 19:20:54.22\n"
        "% note: <script>alert(1)</script>\nSeconds\n0\n",
        encoding="utf-8",
    )
    clean = tmp_path / "clean.csv"
    clean.write_text("Seconds\n0\n", encoding="utf-8")
    with monkeypatch.context() as parsing:
        parsing.setattr("utils.CSV_HEADER_PATTERNS", [*CSV_HEADER_PATTERNS, re.compile(r"^% (note: .+)")])
        dataset = load_dataset(stamped, stamped.name, ["Seconds"])
    first = AppTest.from_string(SMALL_PAGE)
    first.session_state["dataset"] = dataset
    first.run()
    second = AppTest.from_string(SMALL_PAGE)
    second.session_state["dataset"] = load_dataset(clean, clean.name, ["Seconds"])
    second.run()
    second.selectbox[0].select('Δ "</script>').run()
    assert not reports
    for app in (first, second):
        app.button[0].click().run()
        assert not app.exception
        assert len(app.download_button) == 1
    first_report, second_report = reports
    panel = re.search(r'<aside class="csv-metadata">(.*?)</aside>', first_report).group(1)
    assert re.findall(r'<li>(.*?)</li>', panel) == [
        "version: 1.5", "start time: 18:00:30.35", "end time: 19:20:54.22",
        "Elapsed time: 01:20:23.87", "note: &lt;script&gt;alert(1)&lt;/script&gt;",
    ]
    assert first_report.index(panel) < first_report.index("Direct metric")
    assert '<aside class="csv-metadata">' not in second_report
    assert "version: 1.5" not in second_report
    payload = r'<script type="application/json">(.*?)</script>'
    labels = []
    for report in reports:
        assert 'excluded sentinel' not in report and 'hidden sentinel' not in report
        assert report.index('Direct metric') < report.index('Context heading') < report.index('Shared tutorial')
        figure = json.loads(json.loads(re.search(payload, report).group(1))["figure"])
        labels.append(figure["data"][0]["x"])
    assert labels == [["First"], ['Δ "</script>']]
    assert "Δ &quot;&lt;/script&gt;" in second_report and "Δ &quot;&lt;/script&gt;" not in first_report
    second.selectbox[0].select("First").run()
    assert not second.download_button


def test_charts_report_covers_filtered_view(monkeypatch):
    reports = collect_documents(monkeypatch)
    frame = load_projection(ROOT / "synthetic_sales_data.csv", ALWAYS_LOAD_COLUMNS)
    # Each independent AppTest runtime owns its component registry.
    monkeypatch.delitem(sys.modules, "framework.measured_chart", raising=False)
    app = AppTest.from_file(str(next((ROOT / "pages").glob("*Charts (14).py"))))
    app.session_state["df_full"] = frame
    app.run(timeout=30)
    region = frame.Region.iloc[0]
    next(w for w in app.multiselect if "Regions" in w.label).set_value([region]).run(timeout=30)
    next(w for w in app.button if w.label == "Export page as HTML").click().run(timeout=30)
    assert not app.exception
    report, = reports
    assert report.count('class="report-chart"') == 9
    assert report.count('<section class="report-chart" data-renderer="renderMeasuredChart"') == 2
    assert "Animated Geo-Trace" not in report
    assert "Channel statistics" in report and "Span:" in report
    assert f"Showing {frame.Region.eq(region).sum():,} of {len(frame):,} records" in report


def test_flight_report_uses_only_the_current_datasets_snapshot(monkeypatch):
    from framework import terrain, trajectory_chart

    # Each AppTest runtime has its own component registry.
    monkeypatch.delitem(sys.modules, trajectory_chart.__name__)
    monkeypatch.setattr(terrain, "ENABLE_DEMO_TERRAIN", False)
    reports = collect_documents(monkeypatch)
    frame = load_projection(ROOT / "synthetic_sales_data.csv", ALWAYS_LOAD_COLUMNS)
    frame = frame.drop(columns=["latitude_2", "altitude_2"]).copy()
    frame.loc[frame.index[0], "latitude"] = 100  # An out-of-range sample.
    page = ROOT / "pages" / "2_✈️_3D_Flight_Simulation.py"
    key = trajectory_chart.TRAJECTORY_COMPONENT_KEY
    app = AppTest.from_file(str(page))
    app.session_state["df_full"] = frame
    app.session_state["dataset"] = SimpleNamespace(version="flight-a")
    app.run()
    assert not app.exception and not reports

    view = {"index": 17, "fps": 8, "status": "playing", "showRoute1": True}
    snapshot = {"dataset": "flight-a", "view": view}
    app.session_state[key] = {"export_snapshot": snapshot}
    app.session_state["dataset"] = SimpleNamespace(version="flight-b")
    app.run()
    assert not app.exception and not app.download_button and not reports

    app.session_state[key] = {"export_snapshot": {**snapshot, "dataset": "flight-b"}}
    app.run()
    assert not app.exception and len(app.download_button) == 1
    report, = reports
    assert 'data-renderer="renderFlightPlayer"' in report
    assert "Ignored 1 rows" in report
    assert "Showing the primary route only." in report
    assert "Playback uses 300 evenly distributed frames" in report
    data = json.loads(re.search(r'<script type="application/json">(.*?)</script>', report)[1])
    assert len(data["rows"]) == 300 and not data["hasSecondary"] and data["terrain"] is None
    assert data["initialState"] == {**view, "status": "paused"}


def test_trajectory_report_exports_each_sessions_settings(monkeypatch):
    from framework import trajectory_export

    reports = collect_documents(monkeypatch)
    page = ROOT / "pages" / "2_📈_Animated_Trajectory_2.py"

    def unexpected_export(*args, **kwargs):
        raise AssertionError("Live trajectory invoked the offline builder")

    with monkeypatch.context() as inactive:
        inactive.setattr(trajectory_export, "export_trajectory", unexpected_export)
        first = AppTest.from_file(str(page)).run()
        second = AppTest.from_file(str(page)).run()
        first.slider[0].set_value(8)
        first.slider[1].set_value(23)
        first.slider[2].set_value(150)
        first.toggle[0].set_value(True)
        first.run()
        assert not first.exception and not second.exception
        assert not reports

    for app in (first, second):
        app.button[0].click().run()
        assert not app.exception
        assert len(app.download_button) == 1
        assert len(app.get("plotly_chart")) == 1

    payloads = []
    for report in reports:
        assert "Route · 40 steps" in report
        assert report.count('<section class="report-chart" data-renderer="renderTrajectory"') == 1
        assert '<p class="setting">' not in report
        assert "open-street-map" not in report
        assert "Plotly.newPlot" not in report
        payload = json.loads(re.search(r'<script type="application/json">(.*?)</script>', report)[1])
        assert [sample[0] for sample in payload["route"]] == list(range(40))
        assert payload["coast"]["rings"] and "Natural Earth" in payload["coast"]["source"]
        payloads.append(payload)

    keys = ("zoom", "markerSize", "frameDuration", "showPoints")
    assert [tuple(payload[key] for key in keys) for payload in payloads] == [
        (8, 23, 150, True), (9, 16, 350, False),
    ]
    assert payloads[0]["route"] == payloads[1]["route"]
