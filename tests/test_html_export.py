import json
import re
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

from framework.config import ALWAYS_LOAD_COLUMNS
from framework.data import load_projection
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


def test_two_line_opt_in_and_isolated_sessions(monkeypatch):
    reports = collect_documents(monkeypatch)
    first = AppTest.from_string(SMALL_PAGE).run()
    second = AppTest.from_string(SMALL_PAGE).run()
    second.selectbox[0].select('Δ "</script>').run()
    assert not reports
    for app in (first, second):
        app.button[0].click().run()
        assert not app.exception
        assert len(app.download_button) == 1
    first_report, second_report = reports
    payload = r'<script type="application/json">(.*?)</script>'
    labels = []
    for report in reports:
        assert 'excluded sentinel' not in report and 'hidden sentinel' not in report
        assert report.index('Direct metric') < report.index('Context heading') < report.index('Shared tutorial')
        figure = json.loads(json.loads(re.search(payload, report).group(1))["figure"])
        labels.append(figure["data"][0]["x"])
    assert labels == [["First"], ['Δ "</script>']]
    assert "&lt;/script&gt;" in second_report and "&lt;/script&gt;" not in first_report
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
