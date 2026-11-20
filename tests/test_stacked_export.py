import json
import re
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from framework import stacked_export
from framework.html_export import HtmlReport
from framework.stacked_presets import Preset

PAGE = next((Path(__file__).resolve().parents[1] / "pages").glob("*Enhanced Seconds.py"))


def test_stacked_snapshot_retry_and_session_isolation(monkeypatch):
    documents = []
    render = HtmlReport.document

    def capture(report):
        documents.append(render(report))
        return documents[-1]

    field = 'Δ "</script>'
    preset = Preset("p", 1, "Signals", (field, "unloaded"), (), None)
    monkeypatch.setattr(HtmlReport, "document", capture)
    monkeypatch.setattr(stacked_export.PresetStore, "list", lambda self: [preset])
    for label in ("alpha", "beta"):
        app = AppTest.from_file(str(PAGE))
        app.session_state["df_full"] = pd.DataFrame({
            "Seconds": [1.5, 0.5, 0.5], field: [label, label, None], "hidden": [3, 2, 1]})
        app.run()
        next(w for w in app.multiselect if w.label == "Select columns to display").set_value([field]).run()
        app.session_state[f"legacy:{PAGE.stem}:selected_source_row"] = "1"
        def export():
            next(w for w in app.button if w.label == "Export page as HTML").click().run()
            assert not app.exception
        monkeypatch.setattr(stacked_export, "MAX_INTERACTIVE_EXPORT_MB", 0)
        export()
        assert not app.download_button
        assert any("size limit" in w.value for w in app.warning)
        monkeypatch.setattr(stacked_export, "MAX_INTERACTIVE_EXPORT_MB", 32)
        export()
        assert app.download_button
        html = documents[-1]
        assert "Plotly.newPlot" not in html and field not in html
        data = json.loads(re.search(r'<script type="application/json">(.*?)</script>', html)[1])
        assert data["selected"] == [field] and data["source"] == "1"
        assert data["rows"][0] == ["0", 1.5, label, 3]
        assert data["presets"][0]["id"] == "p"
    assert "alpha" not in documents[-1]
