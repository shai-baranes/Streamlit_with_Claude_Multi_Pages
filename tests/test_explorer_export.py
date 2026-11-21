import json
import re
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from framework import explorer_export
from framework.export_payload import InteractiveExportTooLarge
from framework.html_export import HtmlReport


PAGE = Path(__file__).resolve().parents[1] / "pages" / "0_🔧_Engineering_Explorer.py"


def test_explorer_limit_counts_converted_columns_and_escaped_values():
    frame = pd.DataFrame({"Date </script>": ["01/02/2024", None], "Reading": [1.25, 2.5]})
    original_only = explorer_export.explorer_payload(frame, [], {}, 4096)
    with pytest.raises(InteractiveExportTooLarge):
        explorer_export.explorer_payload(frame, ["Reading"], {}, len(original_only))
    full = explorer_export.explorer_payload(frame, ["Reading"], {}, 4096)
    assert "</script>" not in full
    with pytest.raises(InteractiveExportTooLarge):
        explorer_export.explorer_payload(frame, ["Reading"], {}, len(full) - 1)
    assert explorer_export.explorer_payload(frame, ["Reading"], {}, len(full)) == full


def test_explorer_snapshot_and_limit_retry(monkeypatch):
    reports = []
    document = HtmlReport.document

    def collect(report):
        reports.append(document(report))
        return reports[-1]

    monkeypatch.setattr(HtmlReport, "document", collect)
    field = 'Δ "</script>'
    app = AppTest.from_file(str(PAGE))
    app.session_state["df_full"] = pd.DataFrame({
        "Date label": ["02/01/2024", "11/02/2024", "bad"],
        "Seconds": [0.125, 0.5, 1.75],
        "Year": [2020, 2021, 2022],
        field: [2, 4, 8],
        "Group": ["X", "X", None],
    })
    app.run()
    app.multiselect[0].set_value(["Group", "Year"])
    app.selectbox[0].set_value(field)
    app.selectbox[1].set_value("median")
    app.selectbox[2].set_value("Seconds")
    app.radio[0].set_value("Numeric")
    app.multiselect[1].set_value([field, "Year"])
    app.run()
    app.slider[0].set_value((0.125, 0.5)).run()
    assert not app.exception and not reports

    monkeypatch.setattr(explorer_export, "MAX_INTERACTIVE_EXPORT_MB", 0)
    app.button[0].click().run()
    assert not app.exception and not app.download_button
    assert "Seconds interval" in app.warning[0].value

    monkeypatch.setattr(explorer_export, "MAX_INTERACTIVE_EXPORT_MB", 32)
    app.button[0].click().run()
    assert not app.exception and len(app.download_button) == 1
    report, = reports
    assert field not in report
    assert 'data-renderer="renderPlot"' not in report
    data = json.loads(re.search(r'<script type="application/json">(.*?)</script>', report)[1])
    assert data["schema"][3]["name"] == field and data["original"][3] == [2, 4, 8]
    assert data["settings"]["group"] == ["Group", "Year"] and data["settings"]["metric"] == field
    assert data["settings"]["bounds"] == [0.125, 0.5]
    assert data["settings"]["y"] == [field, "Year"]
    assert data["converted"][0]["Datetime"] == [
        "2024-01-02T00:00:00.000000000", "2024-02-11T00:00:00.000000000", None,
    ]
    assert data["converted"][2]["Datetime"][0] == "2020-01-01T00:00:00.000000000"

    second = AppTest.from_file(str(PAGE))
    second.session_state["df_full"] = pd.DataFrame({"Label": ["second session"]})
    second.run()
    second.button[0].click().run()
    assert not second.exception and len(second.download_button) == 1
    assert "second session" in reports[-1] and field not in reports[-1]
    assert "second session" not in report and "plotly.js v" not in reports[-1]
