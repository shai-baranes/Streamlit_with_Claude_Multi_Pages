"""
app.py — Home / Upload page.

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

import streamlit as st
from utils import inject_css, load_csv, tutorial_box

DEBUG = True  # Set to False to enable CSV upload (note: also in DEBUG mode, after each refresh you need to click on the 'Load CSV' page in the sidebar to load the sample data)

st.set_page_config(
    page_title="Sales Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

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

# st.markdown("""
# <div class='tutorial-box'>
# <b>📘 Tutorial: Multipage Apps (Streamlit 1.12+)</b><br>
# Place additional <code>.py</code> files inside a <code>pages/</code> folder next to
# <code>app.py</code>. Streamlit automatically adds them to the sidebar navigation.<br><br>
# • File names control the order and label: <code>1_📊_KPIs.py</code> → "KPIs"<br>
# • <code>st.session_state</code> persists across page navigations within the same session<br>
# • Shared code (CSS, loaders, filters) lives in a plain <code>utils.py</code> module
# </div>
# """, unsafe_allow_html=True)

st.markdown("---")

if not DEBUG:
    uploaded_file = st.file_uploader(
        "📂 Upload your CSV file",
        type=["csv"],
        help="Upload the CSV exported with: df_full.to_csv('my_csv_file.csv', index=False)",
    )

    if uploaded_file is not None:
        df_full = load_csv(uploaded_file.read())
        st.session_state["df_full"] = df_full
        st.success(f"✅ Loaded **{uploaded_file.name}** — {len(df_full)} rows, {len(df_full.columns)} columns")
        with st.expander("👀 Preview first 5 rows"):
            st.dataframe(df_full.head())
        st.info("👈 Use the sidebar to navigate to KPIs, Charts, Pivot Tables, or Data Explorer.")
    else:
        st.info("👆 Upload a CSV file to unlock the dashboard pages.")
        if "df_full" in st.session_state:
            st.success(f"✅ Previously loaded data still active ({len(st.session_state['df_full']):,} rows). Navigate using the sidebar.")
else:
    st.warning("⚠️ DEBUG MODE: CSV upload disabled, using sample data.")
    df_full = load_csv(open("synthetic_sales_data.csv", "rb").read())
    st.session_state["df_full"] = df_full
    st.success(f"✅ Loaded synthetic_sales_data.csv — {len(df_full)} rows, {len(df_full.columns)} columns")