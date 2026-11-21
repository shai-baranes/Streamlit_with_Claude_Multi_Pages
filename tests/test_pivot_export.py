import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from framework.config import ALWAYS_LOAD_COLUMNS
from framework.data import load_projection
from framework.html_export import HtmlReport
from framework import pivot_export


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "3_🔄_Pivot_Tables.py"
SCRIPT = ROOT / "framework" / "pivot_export.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="JavaScript runtime unavailable")
def test_offline_matrix_matches_live_pandas():
    frame = pd.DataFrame({
        "Year": [10, 10, 10, 2, 2, 2, 3, None, 10],
        "Channel": ["Web", "Web", "Store", "Web", "Web", "Store", "Other", "Web", None],
        "Profit": [1.25, 2.5, None, 0.25, None, -2.5, None, 9, 15],
    })
    operations = ["sum", "mean", "count", "median", "max"]
    data = pivot_export.pivot_payload(
        frame, {}, {"rows": ["Year", "Channel"], "value": ["Profit"], "operation": operations}, 4096,
    )
    # Exercise the actual browser calculation without pulling in a browser dependency.
    script = SCRIPT.read_text(encoding="utf-8") + """
    const data = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
    console.log(JSON.stringify(data.options.operation.map(operation =>
      computePivot(data.dimensions.Year, data.dimensions.Channel, data.values.Profit, operation)
    )));
    """
    result = subprocess.run(["node", "-e", script], input=data, text=True, capture_output=True, check=True)
    for operation, matrix in zip(operations, json.loads(result.stdout), strict=True):
        expected = frame.pivot_table(
            values="Profit", index="Year", columns="Channel",
            aggfunc=np.median if operation == "median" else operation, fill_value=0,
            margins=True, margins_name="TOTAL",
        ).iloc[:-1, :-1]
        assert matrix["rows"] == expected.index.tolist()
        assert matrix["columns"] == expected.columns.tolist()
        np.testing.assert_allclose(matrix["cells"], expected.to_numpy(dtype=float))


def test_pivot_page_exports_session_filters_and_recovers_after_limit(monkeypatch):
    reports = []
    document = HtmlReport.document

    def collect(report):
        reports.append(document(report))
        return reports[-1]

    monkeypatch.setattr(HtmlReport, "document", collect)
    frame = load_projection(ROOT / "synthetic_sales_data.csv", ALWAYS_LOAD_COLUMNS)
    field = 'Δ "</script>'
    first_frame = frame.head(12).assign(Region=field)
    second_frame = frame.tail(12).assign(Region="Other session")

    def app_for(data):
        app = AppTest.from_file(str(PAGE))
        app.session_state["df_full"] = data
        return app.run()

    first = app_for(first_frame)
    first.button[0].click().run()
    invalid_report, = reports
    assert not first.exception and first.download_button
    assert '"rows":"Region","columns":"Region"' in invalid_report
    assert field not in invalid_report
    assert "Showing 12 of 12 records" in invalid_report

    first.selectbox[1].select("Category").run()
    monkeypatch.setattr(pivot_export, "MAX_INTERACTIVE_EXPORT_MB", 0)
    first.button[0].click().run()
    assert not first.download_button
    assert any("Narrow the sidebar filters" in item.value for item in first.warning)
    monkeypatch.setattr(pivot_export, "MAX_INTERACTIVE_EXPORT_MB", 32)
    first.button[0].click().run()
    assert not first.exception and first.download_button
    report = reports[1]
    payload = json.loads(re.search(r'<script type="application/json">(.*?)</script>', report)[1])
    assert payload["settings"]["columns"] == "Category"
    assert payload["dimensions"]["Region"]["labels"] == [field]
    assert payload["values"]["Revenue"] == first_frame.Revenue.tolist()
    assert "Deal_Won" not in payload["values"] and "Date" not in payload["dimensions"]
    assert report.count('data-renderer="renderPivot"') == 2  # section plus adapter selector
    assert 'data-renderer="renderPlot"' not in report
    assert "Tutorial: Plotly Heatmap from Pivot" in report

    second = app_for(second_frame)
    second.button[0].click().run()
    assert "Other session" in reports[2] and r"\u0394" not in reports[2]
    assert "Other session" not in report
    next(w for w in second.multiselect if "Regions" in w.label).set_value([]).run()
    second.button[0].click().run()
    assert "No data matches the current filters" in reports[3]
    assert "Showing 0 of 12 records" in reports[3]
    assert 'data-renderer="renderPivot"' not in reports[3]
