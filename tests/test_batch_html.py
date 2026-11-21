from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from threading import Event, Thread
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from framework import batch_html, data
from framework.cli import startup_csv_options
import run_server


ROOT = Path(__file__).resolve().parents[1]


def test_batch_flag_requires_source_and_is_forwarded(tmp_path, monkeypatch):
    source = tmp_path / "my data.csv"
    source.write_text("Seconds\n1\n")
    monkeypatch.setattr(sys, "argv", ["Load CSV.py", "--export-pages-html"])
    with pytest.raises(ValueError, match="requires a startup CSV"):
        startup_csv_options()
    monkeypatch.setattr(sys, "argv", ["run_server.py", "--export-pages-html"])
    with pytest.raises(SystemExit):
        run_server.main()
    calls = []
    monkeypatch.setattr(run_server.subprocess, "call", lambda cmd, **kwargs: calls.append(cmd) or 0)
    monkeypatch.setattr(sys, "argv", ["run_server.py", "--csv_file", str(source), "--export-pages-html"])
    assert run_server.main() == 0
    assert calls[0][-4:] == ["--", "--csv_file", str(source), "--export-pages-html"]


@pytest.mark.parametrize("args", [
    ("dashboard_server.py", "--csv_file", "PATH", "--all-columns"),
    ("Load CSV.py", "PATH", "--load-all"),
    ("Load CSV.py", "PATH"),
])
def test_applied_startup_projection_triggers_batch(tmp_path, monkeypatch, args):
    monkeypatch.setattr(data, "ROOT", tmp_path / "private")
    source = tmp_path / "startup.csv"
    source.write_text("Seconds,Other\n0,a\n1,b\n2,c\n")
    monkeypatch.setattr(sys, "argv", [*(str(source) if arg == "PATH" else arg for arg in args),
                                     "--export-pages-html"])
    calls = []
    monkeypatch.setattr(batch_html, "start_batch", lambda path, dataset: calls.append((path, dataset)))
    app = AppTest.from_file(str(ROOT / "Load CSV.py")).run()
    if args == ("Load CSV.py", "PATH"):
        assert not calls
        app.slider[0].set_range(1.0, 2.0)
        app.multiselect[0].set_value(["Other"])
        app.button[-1].click().run()
        assert calls[0][1].frame.Seconds.tolist() == [1, 2]
    assert not app.exception and len(calls) == 1
    assert calls[0][0] == source
    assert list(calls[0][1].frame) == ["Seconds", "Other"]
    app.run()
    app.file_uploader[0].set_value((source.name, b"Seconds,Other\n4,new\n", "text/csv")).run()
    app.button[-1].click().run()
    assert not app.exception and len(calls) == 1
    assert app.session_state["dataset"].frame.Seconds.tolist() == [4]


def test_replacement_before_first_apply_cannot_start_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "ROOT", tmp_path / "private")
    source = tmp_path / "startup.csv"
    source.write_text("Seconds\n0\n1\n")
    monkeypatch.setattr(sys, "argv", ["Load CSV.py", str(source), "--export-pages-html"])

    def unexpected(*args):
        pytest.fail("The replacement upload claimed the startup batch")

    monkeypatch.setattr(batch_html, "start_batch", unexpected)
    app = AppTest.from_file(str(ROOT / "Load CSV.py")).run()
    app.file_uploader[0].set_value((source.name, b"Seconds\n7\n", "text/csv")).run()
    app.button[-1].click().run()
    assert not app.exception
    assert app.session_state["dataset"].frame.Seconds.tolist() == [7]


def test_concurrent_claims_and_atomic_output_folders(tmp_path, monkeypatch):
    source = tmp_path / "in.csv"
    source.touch()
    dataset = SimpleNamespace(source=source, name=source.name, selected=[], seconds_range=None, frame=[])
    monkeypatch.setattr(batch_html, "_claimed", False)
    ran = Event()

    def fake_worker(job, stream, settings):
        stream.close()
        ran.set()

    monkeypatch.setattr(batch_html, "_supervise", fake_worker)
    with ThreadPoolExecutor(4) as pool:
        folders = list(pool.map(batch_html.reserve_output, [tmp_path] * 4))
        jobs = list(pool.map(lambda _: batch_html.start_batch(source, dataset), range(4)))
    assert {path.name for path in folders} == {
        "streamlit_pages", "streamlit_pages_2", "streamlit_pages_3", "streamlit_pages_4",
    }
    assert [job.folder.name for job in jobs if job] == ["streamlit_pages_5"]
    assert ran.wait(5)


def test_unwritable_output_leaves_a_failed_job(tmp_path, monkeypatch):
    source = tmp_path / "data.csv"
    source.touch()
    monkeypatch.setattr(batch_html, "_claimed", False)

    def denied(_):
        raise PermissionError("Cannot create output directory")

    monkeypatch.setattr(batch_html, "reserve_output", denied)
    job = batch_html.start_batch(source, SimpleNamespace(source=source))
    assert job.done and job.folder is None and "Cannot create" in job.error


def test_readiness_requires_completed_page_after_staging(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("Seconds\n1\n")
    dataset = data.load_dataset(source, source.name, ["Seconds"])
    page = tmp_path / "page.py"
    release = tmp_path / "release"
    page.write_text(f"""
from pathlib import Path
from time import sleep
from framework.state import ui
st = ui(__file__).exportable_page(title="Readiness")
st.text("Complete page content")
st.finish_html_export()
while not Path({str(release)!r}).exists():
    sleep(0.01)
raise RuntimeError("after export hook")
""")
    destination = batch_html.ReportDestination(tmp_path)
    result = []
    runner = Thread(target=lambda: result.append(batch_html.run_page(page, dataset, destination)), daemon=True)
    runner.start()
    try:
        import time

        deadline = time.monotonic() + 10
        while destination.filename is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert destination.temporary.exists() and not list(tmp_path.glob("*.html"))
    finally:
        release.touch()
        runner.join(10)
    assert result == ["Failed · after export hook"]
    assert not list(tmp_path.glob("*.html"))

    page.write_text(page.read_text().split("while not Path")[0])
    assert batch_html.run_page(page, dataset, batch_html.ReportDestination(tmp_path)) == "Saved · Readiness.html"
    assert (tmp_path / "Readiness.html").read_text().endswith("</body></html>")
