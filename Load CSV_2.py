"""
Load CSV.py — Home / Upload page.

TUTORIAL NOTE ───────────────────────────────────────────────────────────────
Multipage apps in Streamlit 1.12:
  • app.py         → the entry-point / home page
  • pages/*.py     → additional pages, shown in sidebar nav in filename order
  • Prefix files with a number to control order: 1_📊_KPIs.py, 2_📈_Charts.py …

Each page script is run from scratch on navigation, but st.session_state
persists across pages for the duration of the browser session.

We store df_full in st.session_state["df_full"] here so all other pages can
access the data without re-uploading.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from utils import inject_css, load_csv, tutorial_box

DEBUG = True  # If True, preload sample data when nothing else is loaded yet


st.set_page_config(
    page_title="Sales Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def get_cli_file_path() -> Path | None:
    args = sys.argv[1:]
    if not args:
        return None

    path = Path(args[0]).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    return path


def load_from_path(file_path: Path):
    if not file_path.exists():
        raise FileNotFoundError(f"File does not exist: {file_path}")
    if not file_path.is_file():
        raise FileNotFoundError(f"Not a regular file: {file_path}")
    if file_path.suffix.lower() != ".csv":
        raise ValueError(f"Unsupported file type: {file_path.suffix}. Supported: .csv")

    return load_csv(file_path.read_bytes()) # TBD: add support for larger files by passing the path directly to pandas.read_csv instead of loading the whole file into memory first


def store_loaded_df(df_full, source_name: str, source_kind: str) -> None:
    st.session_state["df_full"] = df_full
    st.session_state["source_name"] = source_name
    st.session_state["source_kind"] = source_kind


def render_loaded_message(df_full) -> None:
    source_name = st.session_state.get("source_name", "data source")
    source_kind = st.session_state.get("source_kind", "unknown")

    if source_kind == "debug":
        st.warning("⚠️ DEBUG MODE: sample data preloaded.")
    elif source_kind == "cli":
        st.caption("Opened from command-line argument.")
    elif source_kind == "upload":
        st.caption("Using uploaded CSV file.")

    st.success(
        f"✅ Loaded **{source_name}** — {len(df_full)} rows, {len(df_full.columns)} columns"
    )

    with st.expander("👀 Preview first 5 rows"):
        st.dataframe(df_full.head(), use_container_width=True)

    st.info("👈 Use the sidebar to navigate to KPIs, Charts, Pivot Tables, or Data Explorer.")


inject_css()

st.title("📊 Global Sales Intelligence Dashboard")
st.caption("A hands-on Streamlit + Pandas tutorial · Upload a CSV to begin")

tutorial_box("""
<b>📘 Tutorial: Multipage Apps (Streamlit 1.12+)</b><br>
Place additional <code>.py</code> files inside a <code>pages/</code> folder next to
<code>app.py</code>. Streamlit automatically adds them to the sidebar navigation.<br><br>
• File names control the order and label: <code>1_📊_KPIs.py</code> → "KPIs"<br>
• <code>st.session_state</code> persists across page navigations within the same session<br>
• Shared code (CSS, loaders, filters) lives in a plain <code>utils.py</code> module
</div>
""")

st.markdown("---")

cli_file_path = get_cli_file_path()

if "df_full" not in st.session_state:
    st.session_state["df_full"] = None
if "source_name" not in st.session_state:
    st.session_state["source_name"] = None
if "source_kind" not in st.session_state:
    st.session_state["source_kind"] = None

# 1) CLI file: initialize session from command line only if nothing is loaded yet.
if cli_file_path is not None and st.session_state["df_full"] is None:
    try:
        df_full = load_from_path(cli_file_path)
        store_loaded_df(df_full, cli_file_path.name, "cli")
    except Exception as e:
        st.error(f"Failed to open file from command line: {e}")

# 2) DEBUG sample: fallback only when nothing is loaded yet.
elif DEBUG and st.session_state["df_full"] is None:
    try:
        df_full = load_csv(Path("synthetic_sales_data.csv").read_bytes())
        store_loaded_df(df_full, "synthetic_sales_data.csv", "debug")
    except Exception as e:
        st.error(f"Failed to load debug CSV: {e}")

# 3) Always show uploader so user can override DEBUG or CLI data.
uploaded_file = st.file_uploader(
    "📂 Upload your CSV file",
    type=["csv"],
    help="Upload the CSV exported with: df_full.to_csv('my_csv_file.csv', index=False)",
)

if uploaded_file is not None:
    try:
        df_full = load_csv(uploaded_file.getvalue())
        store_loaded_df(df_full, uploaded_file.name, "upload")
    except Exception as e:
        st.error(f"Failed to load uploaded CSV: {e}")

# 4) Render current active dataframe, if any.
if st.session_state.get("df_full") is not None:
    render_loaded_message(st.session_state["df_full"])
else:
    st.info("👆 Upload a CSV file to unlock the dashboard pages.")



# # Page-side reminder
# # On your other pages, use:


# df_full = st.session_state.get("df_full")
# if df_full is None:
#     st.warning("Please load a CSV first on the Load CSV page.")
#     st.stop()