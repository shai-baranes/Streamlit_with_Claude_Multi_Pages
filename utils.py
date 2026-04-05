"""
utils.py — shared helpers imported by every page.

TUTORIAL NOTE ───────────────────────────────────────────────────────────────
In a multipage Streamlit app, each page is a separate Python script that
Streamlit runs independently. To share code (CSS, caching, sidebar filters)
across pages we put it in a plain Python module and import it.

st.session_state persists across page navigations within the same browser
session, so the uploaded file and all filter selections survive page switches.
─────────────────────────────────────────────────────────────────────────────
"""

import io
import streamlit as st
import pandas as pd


# ── Shared CSS ────────────────────────────────────────────────────────────────
# Light theme: white/light-grey backgrounds, dark text, indigo/teal accents.
# NOTE: In Streamlit 1.12, config.toml theming is not fully supported and
# class-based CSS is often overridden by Streamlit's own injected styles.
# We keep the CSS for elements Streamlit doesn't override (metric cards, headers)
# but tutorial boxes now use inline styles to guarantee their appearance.
CSS = """
<style>
    /* ── Page background ── */
    .main  { background-color: #f5f7fa; }
    .stApp { background-color: #f5f7fa; }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e2e8f0; }

    /* ── KPI metric cards ── */
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #ffffff 0%, #eef2ff 100%);
        border: 1px solid #c7d2fe;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 1px 4px rgba(99,102,241,0.08);
    }

    /* ── Section headers ── */
    .section-header {
        font-size: 1.4rem;
        font-weight: 700;
        color: #1e293b;
        border-left: 4px solid #6366f1;
        padding-left: 12px;
        margin: 24px 0 12px 0;
    }

    /* ── General text ── */
    h1, h2, h3 { color: #1e293b !important; }
    p, li       { color: #374151; }
</style>
"""

# ── Tutorial box HTML ─────────────────────────────────────────────────────────
# TUTORIAL NOTE:
# In Streamlit 1.12, class-based CSS targeting custom divs is unreliable —
# Streamlit's own injected stylesheet often wins the specificity battle.
# The solution is inline styles, which always have the highest CSS specificity
# and cannot be overridden by any external stylesheet.
def tutorial_box(html_content: str) -> None:
    """Render a styled tutorial callout box using fully inline styles."""
    st.markdown(f"""
<div style="
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-left: 4px solid #3b82f6;
    border-radius: 8px;
    padding: 16px 20px;
    margin: 12px 0;
    font-size: 0.88rem;
    color: #1e293b;
    line-height: 1.7;
    font-family: sans-serif;
">
{html_content}
</div>
""", unsafe_allow_html=True)

def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


# ── CSV loader (cached) ───────────────────────────────────────────────────────
@st.cache
def load_csv(file_bytes: bytes) -> pd.DataFrame:
    """
    TUTORIAL NOTE ───────────────────────────────────────────────────────────
    Accepts bytes (not UploadedFile) so the argument is hashable for @st.cache.
    Derives time columns if they are absent from the CSV.
    ─────────────────────────────────────────────────────────────────────────
    """
    df = pd.read_csv(io.BytesIO(file_bytes))
    df["Date"] = pd.to_datetime(df["Date"])
    if "Year"     not in df.columns: df["Year"]     = df["Date"].dt.year
    if "MonthNum" not in df.columns: df["MonthNum"]  = df["Date"].dt.month
    if "Month"    not in df.columns: df["Month"]     = df["Date"].dt.strftime("%b")
    if "Quarter"  not in df.columns: df["Quarter"]   = df["Date"].dt.quarter.apply(lambda q: f"Q{q}")
    return df.sort_values("Date").reset_index(drop=True)


# ── Upload gate ───────────────────────────────────────────────────────────────
def require_data() -> pd.DataFrame:
    """
    Call at the top of every page.
    Returns df_full if a file has been uploaded, otherwise shows the upload
    prompt and calls st.stop() so nothing else on the page renders.

    TUTORIAL NOTE ───────────────────────────────────────────────────────────
    st.session_state["df_full"] acts as a cross-page data store.
    The file is uploaded once on the home page; every other page reads it
    from session_state without re-uploading.
    ─────────────────────────────────────────────────────────────────────────
    """
    if "df_full" not in st.session_state:
        st.warning("⚠️ No data loaded yet. Please go to the **Home** page and upload a CSV file.")
        st.stop()
    return st.session_state["df_full"]


# ── Sidebar filters ───────────────────────────────────────────────────────────
def sidebar_filters(df_full: pd.DataFrame) -> pd.DataFrame:
    """
    Renders all sidebar filters and returns the filtered DataFrame.
    Call once per page — widget keys are stable so session_state
    preserves selections when navigating between pages.
    """
    with st.sidebar:
        st.image("https://streamlit.io/images/brand/streamlit-mark-color.png", width=40) # TBD replace it with a locally saved image to avoid external dependency   
        st.title("🎛️ Filters")
        st.markdown("---")

        # ── helper: bi-directional All checkbox ──────────────────────────────
        def _all_multiselect(label, emoji, all_opts, cb_key, ms_key, prev_key):
            _prev = st.session_state.get(prev_key, all_opts)
            _cur  = st.session_state.get(ms_key,   all_opts)
            if set(_cur) < set(_prev) and st.session_state.get(cb_key, True):
                st.session_state[cb_key] = False
            # all_cb = st.checkbox(f"All {label}", value=True, key=cb_key) # no need for user defined 'All' button since the drop-down option already includes 'All'    
            # if all_cb:
            #     st.session_state[ms_key] = all_opts
            selected = st.multiselect(
                f"{emoji} {label}", options=all_opts, default=all_opts, key=ms_key,
            )
            st.session_state[prev_key] = st.session_state.get(ms_key, all_opts)
            return selected
            # return all_opts if all_cb else selected

        selected_years = _all_multiselect(
            "Years", "📅",
            sorted(df_full["Year"].unique().tolist()),
            "all_years_cb", "ms_years", "ms_years_prev",
        )
        selected_regions = _all_multiselect(
            "Regions", "🌍",
            sorted(df_full["Region"].unique().tolist()),
            "all_regions_cb", "ms_regions", "ms_regions_prev",
        )
        selected_categories = _all_multiselect(
            "Categories", "🏷️",
            sorted(df_full["Category"].unique().tolist()),
            "all_cats_cb", "ms_categories", "ms_categories_prev",
        )
        selected_segments = _all_multiselect(
            "Segments", "🎯",
            sorted(df_full["Segment"].unique().tolist()),
            "all_segs_cb", "ms_segments", "ms_segments_prev",
        )

        st.markdown("---")
        rev_min = float(df_full["Revenue"].min())
        rev_max = float(df_full["Revenue"].max())
        revenue_range = st.slider(
            "💰 Revenue Range ($)",
            min_value=rev_min, max_value=rev_max,
            value=(rev_min, rev_max), format="$%.0f",
        )
        st.markdown("---")
        won_only = st.checkbox("🏆 Won Deals Only", value=False)
        st.caption(f"Total records: {len(df_full):,}")

    # Apply filters
    df = df_full[
        (df_full["Year"].isin(selected_years))
        & (df_full["Region"].isin(selected_regions))
        & (df_full["Category"].isin(selected_categories))
        & (df_full["Segment"].isin(selected_segments))
        & (df_full["Revenue"].between(*revenue_range))
    ]
    if won_only:
        df = df[df["Deal_Won"] == True]
    return df


# ── Sidebar filters ───────────────────────────────────────────────────────────
def sidebar_filters_2(df_full: pd.DataFrame) -> pd.DataFrame:
    """
    Renders all sidebar filters and returns the filtered DataFrame.
    Call once per page — widget keys are stable so session_state
    preserves selections when navigating between pages.
    """
    with st.sidebar:
        st.image("https://streamlit.io/images/brand/streamlit-mark-color.png", width=40)
        st.title("🎛️ Filters")
        st.markdown("---")

        # ── helper: bi-directional All checkbox ──────────────────────────────
        def _all_multiselect(label, emoji, all_opts, cb_key, ms_key, prev_key):
            _prev = st.session_state.get(prev_key, all_opts)
            _cur  = st.session_state.get(ms_key,   all_opts)
            if set(_cur) < set(_prev) and st.session_state.get(cb_key, True):
                st.session_state[cb_key] = False
            all_cb = st.checkbox(f"All {label}", value=True, key=cb_key)
            if all_cb:
                st.session_state[ms_key] = all_opts
            selected = st.multiselect(
                f"{emoji} {label}", options=all_opts, default=all_opts, key=ms_key,
            )
            st.session_state[prev_key] = st.session_state.get(ms_key, all_opts)
            return all_opts if all_cb else selected

        selected_years = _all_multiselect(
            "Years", "📅",
            sorted(df_full["Year"].unique().tolist()),
            "all_years_cb", "ms_years", "ms_years_prev",
        )
        selected_regions = _all_multiselect(
            "Regions", "🌍",
            sorted(df_full["Region"].unique().tolist()),
            "all_regions_cb", "ms_regions", "ms_regions_prev",
        )
        # selected_categories = _all_multiselect(
        #     "Categories", "🏷️",
        #     sorted(df_full["Category"].unique().tolist()),
        #     "all_cats_cb", "ms_categories", "ms_categories_prev",
        # )
        # selected_segments = _all_multiselect(
        #     "Segments", "🎯",
        #     sorted(df_full["Segment"].unique().tolist()),
        #     "all_segs_cb", "ms_segments", "ms_segments_prev",
        # )

        # st.markdown("---")
        # rev_min = float(df_full["Revenue"].min())
        # rev_max = float(df_full["Revenue"].max())
        # revenue_range = st.slider(
        #     "💰 Revenue Range ($)",
        #     min_value=rev_min, max_value=rev_max,
        #     value=(rev_min, rev_max), format="$%.0f",
        # )
        # st.markdown("---")
        won_only = st.checkbox("🏆 Won Deals Only", value=False)
        st.caption(f"Total records: {len(df_full):,}")

    # Apply filters
    df = df_full[
        (df_full["Year"].isin(selected_years))
        & (df_full["Region"].isin(selected_regions))
        # & (df_full["Category"].isin(selected_categories))
        # & (df_full["Segment"].isin(selected_segments))
        # & (df_full["Revenue"].between(*revenue_range))
    ]
    if won_only:
        df = df[df["Deal_Won"] == True]
    return df
