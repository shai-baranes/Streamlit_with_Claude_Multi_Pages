# AGENTS.md

## Project purpose

This repository is a pandas and Streamlit dashboard for loading, filtering,
grouping, exporting, and visualizing ordinary single-header CSV files. It must
continue to support the existing sales pages while also accepting generic
engineering datasets. The primary deployment target is a Windows server on a
trusted LAN or VPN, with macOS used for local development and validation.

Read `README_GPT.md` before making architectural, deployment, ingestion, or
performance changes. It is the detailed operator guide and should be updated
when user-visible behavior, launch commands, limits, or service setup changes.

## Entry points and important modules

- `Load CSV.py`: Streamlit entry point and session-specific dataset loader.
- `run_server.py`: portable launcher for Windows production and macOS debug use.
- `pages/0_🔧_Engineering_Explorer.py`: schema-independent filtering, grouping,
  tables, and trend views.
- `pages/2_✈️_3D_Flight_Simulation.py`: dataset-backed 3D trajectory page.
- `framework/data.py`: validated CSV retention, projection, resource limits,
  cleanup, and optional Parquet caching.
- `framework/session.py`: atomic staging, replacement, and owned-source cleanup.
- `framework/exports.py`: explicit preparation and session-private download retention.
- `framework/measurement_chart.py`: v2 Plotly chart and point measurements.
- `framework/state.py`: widget namespacing and cross-page persistence wrappers.
- `framework/config.py`: fixed columns and environment-configurable limits.
- `framework/trajectory.py`: pure trajectory validation and frame reduction.
- `framework/trajectory_chart.py`: Streamlit Components v2 Plotly flight player.
- `utils.py`: compatibility helpers used by legacy pages.
- `deploy/`: PowerShell and WinSW service packaging.
- `benchmarks/large_csv.py`: opt-in multi-user CSV/Parquet benchmark.

## Required behavior

- Keep one active dataset per browser session. Never share DataFrames, source
  files, filters, caches, or exports across sessions.
- A new tab, browser refresh, or server restart may start a new session. Private
  temporary disk files support the active session and are not a permanent archive.
- Production starts without a dataset. Sample loading is explicit and controlled
  by `--sample`; never silently load sample data.
- A CLI CSV path is a server-local startup source copied privately into each new
  session. A later upload replaces it only for that session.
- Dataset replacement is atomic: retain the current dataset until the replacement
  has passed header, structure, size, projection, and parsing checks.
- Preserve source column names, row order for generic engineering data, nulls,
  and selected-column ordering.
- Missing fixed or sales fields must produce guidance rather than exceptions.
- Keep legacy sales calculations and page layouts intact unless the requested
  change requires modifying them.

## CSV and performance constraints

`ALWAYS_LOAD_COLUMNS` in `framework/config.py` contains the fixed sample schema,
including `Seconds`, `longitude`, `latitude`, and `Altitude`. Available fixed
fields load automatically; users may add other fields through the projection UI.

CSV input is UTF-8 with an optional BOM, comma-delimited, and has one nonempty,
unique header row. Validate malformed quoting, inconsistent row widths, and
duplicate headers explicitly. Do not reject engineering files merely because
sales fields are absent.

Avoid full-frame copies, repeated CSV parsing on reruns, and eager export
serialization. Respect the configured upload, DataFrame, process-memory,
preview, chart-point, and temporary-file limits. Parquet remains session-private
and optional; automatic conversion stays disabled unless representative
benchmarks satisfy the time and peak-memory policy documented in `README_GPT.md`.

## Session state and Streamlit conventions

- Use the `ui(__file__)` wrapper from `framework/state.py` on pages that need
  persistent widgets. Keep common filters shared and page-specific widgets scoped.
- Keep saved values separate from ephemeral Streamlit widget keys.
- Stage and commit datasets through `framework/session.py`; never delete an original
  CLI source. Refresh leases before expiry cleanup and hold the storage lock through
  staging and ingestion.
- Prepared exports live under `export:<page>` and are invalidated on changed export
  inputs or dataset replacement. Never serialize CSV on unrelated reruns.
- Use `require_data()` for pages that need the active `df_full` compatibility view.
- Do not add process-wide caches containing private session DataFrames.
- Use Streamlit Components v2 APIs for custom components. Do not introduce
  `st.components.v1`, global `Streamlit.*` JavaScript calls, or iframe messaging.
  Existing third-party AgGrid internals are a compatibility exception; do not fork them.
  The measurement renderer uses light DOM for Plotly CSS and pointer compatibility;
  all chart selectors and event listeners must remain scoped to its own root.
- The 3D flight player advances frames and handles camera and slider interaction
  in the browser to avoid a Streamlit rerun for every frame.
- Changes to `framework/trajectory_chart.py` may require restarting the Streamlit
  server because imported component definitions can remain cached.

## 3D trajectory behavior

The flight page requires numeric `Seconds`, `longitude`, `latitude`, and
`Altitude`. All four values must be finite. It drops invalid coordinate rows with a visible notice, sorts stably
by seconds, and reduces playback deterministically to at most 300 frames while
retaining endpoints.

The browser player must preserve the user-selected Plotly camera until Reset.
Play continues from the current frame; Pause holds it; Reset restores frame zero,
the default playback rate, stopped status, and default camera. Progress and rate
sliders remain usable during playback. Keep Play, Pause, and Reset visible while
scrolling within the player. Keep all seven Plotly manipulation icons in one
vertical strip at the bottom-left of the 3D graph.
Keep the playback buttons compact. Play and Pause must clearly show their active
state, and Reset must briefly turn gray when pressed. Keep metric values compact
enough for narrow screens, and retain framed Plotly toolbar buttons.

## Editing rules

- Default to an isolated Git worktree on a `codex/` branch for new feature work.
  An explicit chat instruction to use the current worktree overrides this default.
- Treat every pre-existing dirty-tree change as user-owned. Never discard,
  overwrite, reset, or reformat unrelated changes.
- Make minimal changes to legacy pages. Prefer shared helpers and wrappers for
  cross-cutting behavior.
- When changing or refactoring an existing source file, add concise inline
  comments where the reason or compatibility requirement is not obvious.
- Preserve exact filenames and Unicode page names; quote paths containing spaces
  or emoji in shell commands.
- Use `rg` and `rg --files` for repository searches.
- Do not commit generated caches, `.DS_Store`, virtual environments, service
  executables, temporary datasets, benchmark working files, or Python bytecode.
- Before staging or committing, inspect `git status --short`. Include user-owned
  changes only when the user explicitly asks to include them.

## Validation

Use the project environment and keep the uv cache outside the repository when
appropriate:

```sh
UV_CACHE_DIR=/tmp/codex-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/codex-uv-cache uv run python -m compileall -q .
git diff --check
```

For focused trajectory work, run:

```sh
UV_CACHE_DIR=/tmp/codex-uv-cache uv run pytest tests/test_trajectory.py tests/test_app.py -q
```

Use Streamlit `AppTest` for page and state behavior. Use a real browser for file
drag-and-drop, AgGrid selection restoration, Plotly camera manipulation, live
3D playback, slider dragging, and independent-session verification.

Do not claim Windows service validation from macOS. Report macOS checks and
Windows service checks separately. Large benchmarks are opt-in because the full
500,000-row by 2,000-column scenario can create multi-gigabyte temporary files.

## Common launch commands

macOS development:

```sh
.venv/bin/python run_server.py --debug --sample
.venv/bin/python run_server.py "/absolute/path/to/data.csv" --debug
```

Windows production or foreground validation:

```powershell
.\.venv\Scripts\python.exe run_server.py
.\.venv\Scripts\python.exe run_server.py "C:\Engineering Data\data.csv"
```

The server binds to `0.0.0.0:8501` by default. Remote access assumes a trusted
LAN/VPN and correctly scoped Windows firewall rules; the app has no built-in login.
