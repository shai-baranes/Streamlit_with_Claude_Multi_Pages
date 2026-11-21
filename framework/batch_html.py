"""Export a committed startup CSV projection in an isolated Streamlit runner."""
import ast
from dataclasses import dataclass
import itertools
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from threading import Lock, Thread, Timer


APP_ROOT = Path(__file__).resolve().parents[1]
PAGE_TIMEOUT = 300
TIMEOUT_EXIT = 124
_lock = Lock()
_claimed = False
_log = logging.getLogger(__name__)


def discover_pages(directory):
    for path in sorted(directory.glob("*.py")):
        tree = ast.parse(path.read_bytes(), filename=str(path))
        if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and node.func.attr == "exportable_page" for node in ast.walk(tree)):
            yield path


def reserve_output(parent):
    for number in itertools.count(1):
        folder = parent / ("streamlit_pages" if number == 1 else f"streamlit_pages_{number}")
        try:
            folder.mkdir(mode=0o700)
            return folder
        except FileExistsError:
            continue


def atomic_text(path, text):
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass
class ReportDestination:
    folder: Path
    started: bool = False
    skipped: str | None = None
    error: str | None = None
    filename: str | None = None

    @property
    def temporary(self):
        return self.folder / ".page-report.tmp"

    def stage(self, filename, html):
        self.temporary.write_text(html, encoding="utf-8")
        self.filename = filename

    def publish(self):
        name = Path(self.filename)
        for number in itertools.count(1):
            path = self.folder / (name.name if number == 1 else f"{name.stem}-{number}{name.suffix}")
            if not path.exists():
                self.temporary.replace(path)
                return path.name


@dataclass
class BatchJob:
    folder: Path | None = None
    done: bool = False
    error: str | None = None


def start_batch(source, dataset):
    """Pin the imported source before returning control to the dashboard."""
    global _claimed
    with _lock:
        if _claimed:
            return None
        _claimed = True
    job = BatchJob()
    stream = None
    try:
        stream = dataset.source.open("rb")
        folder = job.folder = reserve_output(source.parent)
        settings = {
            "name": dataset.name, "columns": dataset.selected, "range": dataset.seconds_range,
            "rows": len(dataset.frame), "output": str(folder),
        }
        Thread(target=_supervise, args=(job, stream, settings), daemon=True).start()
    except (OSError, RuntimeError) as error:
        if stream is not None:
            stream.close()
        job.error = str(error)
        job.done = True
        _log.error("HTML batch could not start: %s", error)
    return job


def show_progress(job):
    import streamlit as st

    if job.folder is not None:
        st.caption("HTML export folder")
        st.text(str(job.folder))
    if not job.done:
        _live_progress(job)
    else:
        _progress(job)


def _progress(job):
    import streamlit as st

    if job.error:
        st.error(f"Batch HTML export failed: {job.error}")
        return
    try:
        with (job.folder / "summary.txt").open(encoding="utf-8") as stream:
            progress = stream.readline().strip()
    except OSError:
        progress = "Preparing the imported CSV for HTML export"
    if job.done:
        st.success(f"{progress}. See summary.txt for page outcomes.")
    else:
        st.info(progress)


def _live_progress(job):
    import streamlit as st

    @st.fragment(run_every=1)
    def render():
        _progress(job)
        # End the periodic fragment once the batch completes.
        if job.done:
            st.rerun()

    render()


def _checkpoint(work, settings, state, *, complete=False):
    atomic_text(work / "state.json", json.dumps(state))
    status = "HTML batch complete" if complete else "Exporting HTML"
    counts = f'{len(state["outcomes"])} of {len(settings["pages"])} pages processed'
    lines = [
        f"{status} · {counts}",
        f'CSV: {settings["name"]}',
        f'Rows: {settings["rows"]:,}',
        "Columns: " + ", ".join(settings["columns"]),
        f'Seconds interval: {settings["range"] if settings["range"] is not None else "all rows"}',
        "",
    ]
    if state["current"]:
        lines.append(f'In progress: {state["current"]}')
    lines.extend(f"{page}: {outcome}" for page, outcome in state["outcomes"].items())
    atomic_text(Path(settings["output"]) / "summary.txt", "\n".join(lines) + "\n")


def _supervise(job, source, settings):
    try:
        with source, tempfile.TemporaryDirectory(prefix="dashboard-html-") as directory:
            work = Path(directory)
            settings["pages"] = [page.name for page in discover_pages(APP_ROOT / "pages")]
            state = {"current": None, "outcomes": {}}
            _checkpoint(work, settings, state)
            with (work / "source.csv").open("wb") as snapshot:
                shutil.copyfileobj(source, snapshot, length=1024**2)
            source.close()
            atomic_text(work / "settings.json", json.dumps(settings))
            env = dict(os.environ, DASHBOARD_ADMIN="0", DASHBOARD_SAMPLE="0")
            while True:
                result = subprocess.run(
                    [sys.executable, "-m", "framework.batch_html", str(work)],
                    cwd=APP_ROOT, env=env, stdin=subprocess.DEVNULL,
                )
                state = json.loads((work / "state.json").read_text(encoding="utf-8"))
                if result.returncode == 0:
                    break
                if state["current"] is None:
                    raise RuntimeError(f"Export worker exited with code {result.returncode}.")
                # A stuck ScriptRunner may not honor a stop request. Restart the
                # process for the remaining pages, retaining completed files.
                ReportDestination(job.folder).temporary.unlink(missing_ok=True)
                reason = ("Page timed out" if result.returncode == TIMEOUT_EXIT
                          else f"Export worker exited with code {result.returncode}")
                state["outcomes"][state["current"]] = f"Failed · {reason}"
                state["current"] = None
                _checkpoint(work, settings, state)
            saved = sum(outcome.startswith("Saved") for outcome in state["outcomes"].values())
            print(f"HTML batch finished in {job.folder} ({saved}/{len(settings['pages'])} reports saved). "
                  "See summary.txt for page outcomes.", flush=True)
    except Exception as error:
        job.error = str(error)
        _log.exception("HTML batch failed")
    finally:
        job.done = True


def run_page(page, dataset, destination):
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(page))
    app.session_state["dataset"] = dataset
    app.session_state["df_full"] = dataset.frame
    app.session_state["_html_batch_destination"] = destination
    app.run(timeout=PAGE_TIMEOUT)
    if app.exception:
        return f"Failed · {app.exception[0].message}"
    if destination.error:
        return f"Failed · {destination.error}"
    if destination.skipped:
        return f"Skipped · {destination.skipped}"
    if destination.filename is not None:
        return f"Saved · {destination.publish()}"
    if not destination.started and (app.warning or app.info):
        message = (app.warning or app.info)[0].value
        return f"Skipped · {message}"
    return "Failed · Page did not complete its HTML export"


def run_worker(work):
    from framework.data import load_dataset

    settings = json.loads((work / "settings.json").read_text(encoding="utf-8"))
    state = json.loads((work / "state.json").read_text(encoding="utf-8"))
    interval = tuple(settings["range"]) if settings["range"] is not None else None
    dataset = load_dataset(work / "source.csv", settings["name"], settings["columns"], seconds_range=interval)
    if len(dataset.frame) != settings["rows"]:
        raise ValueError("The export snapshot row count differs from the committed import.")
    for page in settings["pages"]:
        if page in state["outcomes"]:
            continue
        state["current"] = page
        _checkpoint(work, settings, state)
        destination = ReportDestination(Path(settings["output"]))
        watchdog = Timer(PAGE_TIMEOUT + 5, os._exit, args=(TIMEOUT_EXIT,))
        watchdog.daemon = True
        watchdog.start()
        try:
            outcome = run_page(APP_ROOT / "pages" / page, dataset, destination)
        except Exception as error:
            outcome = f"Failed · {error}"
        finally:
            watchdog.cancel()
            destination.temporary.unlink(missing_ok=True)
        state["outcomes"][page] = outcome
        state["current"] = None
        _checkpoint(work, settings, state)
    _checkpoint(work, settings, state, complete=True)


if __name__ == "__main__":
    run_worker(Path(sys.argv[1]))
