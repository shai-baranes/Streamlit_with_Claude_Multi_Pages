# 📊 Streamlit + Pandas Tutorial — Global Sales Dashboard

A professional, fully-commented Streamlit app covering the most important
patterns for building data dashboards with pandas DataFrames.
based on the 'Streamlit_With_Claude' project while adding utilization of page differentialtion and using color themes as supported by the older Streamlit v1.2.0 version. 


## Self Notes
This is a tutorial I created to teach myself how to build data dashboards with Streamlit and pandas. It covers the most important patterns for building interactive data apps, including sidebar filters, KPI cards, charts, pivot tables, and more. The dataset is synthetic global sales data across multiple dimensions.

Once adding pages (TABs), the name of the main TAB is the .py file name and the other tabs according to the file names under the 'page' folder.
(order is given by the enumerate prefix in the file name, e.g. 1_ for the first tab, 2_ for the second tab, etc.)


Quick libraries installation given having a predefined `requirements.txt` file:

```bash
## 🚀 Quick Start


# 1. Create & activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows

# 2. Install dependencies (either option from the following)
# > pip install -r requirements.txt
# OR
# > uv venv  (or > UV add 'project_name')
# > uv pip install -r requirements.txt 
# OR
# > uv add -r requirements.txt # my prefered way

# 3. Run the app
# > streamlit run app.py
# another option (without having to activate the environment)
# > uv run streamlit run app.py
```

Your browser will open automatically at **http://localhost:8501**

---

## 📚 What This Tutorial Covers

| # | Topic | Streamlit API | Pandas Concept |
|---|-------|--------------|----------------|
| ① | Synthetic dataset with `@st.cache_data` | `@st.cache_data` | DataFrame construction |
| ② | Sidebar with multi-select, slider, toggle | `st.sidebar`, `st.multiselect`, `st.slider`, `st.toggle` | — |
| ③ | Boolean filtering chained with `&` | — | `df[mask1 & mask2]`, `.isin()`, `.between()` |
| ④ | KPI metric cards in columns | `st.metric`, `st.columns` | `.sum()`, `.mean()` |
| ⑤ | Bar chart with dynamic group-by | `st.selectbox`, `st.radio` | `.groupby().sum()` |
| ⑥ | Time-series line chart | `st.selectbox` | `.groupby()`, datetime handling |
| ⑦ | Scatter plot with bubble sizing | `st.selectbox` | `.sample()` |
| ⑧ | Treemap (hierarchical drill-down) | `st.selectbox` | — |
| ⑨ | Box plot for distribution analysis | `st.selectbox` | — |
| ⑩ | Interactive pivot table | `st.selectbox` × 4 | `pd.pivot_table()`, `margins=True` |
| ⑪ | Heatmap from pivot | — | `.iloc`, `.values`, `.index` |
| ⑫ | Column-configured data table | `st.dataframe`, `st.column_config` | `.head()` |
| ⑬ | CSV download button | `st.download_button` | `.to_csv().encode()` |
| ⑭ | Collapsible stats expander | `st.expander` | `.describe()` |

---

## 🗂️ Dataset Schema

1,500 synthetic global sales records across 2022–2023:

| Column | Type | Description |
|--------|------|-------------|
| Date | datetime | Transaction date |
| Year / Quarter / Month | int/str | Time dimensions |
| Region | str | 5 global regions |
| Country | str | 20 countries |
| Category | str | Software / Hardware / Services / Cloud / Consulting |
| Product | str | 20 products |
| Segment | str | Enterprise / Mid-Market / SMB |
| Channel | str | Direct / Partner / Online / Reseller |
| Sales_Rep | str | 20 reps (Rep_01 … Rep_20) |
| Revenue | float | Deal value in USD |
| Units | int | Units sold |
| Cost | float | Cost of goods |
| Profit | float | Revenue − Cost |
| Margin_% | float | Profit / Revenue × 100 |
| Deal_Won | bool | Whether the deal closed |

---

## 🔑 Key Patterns to Remember

### Sidebar Filtering
```python
selected = st.sidebar.multiselect("Label", options=df["col"].unique())
df_filtered = df[df["col"].isin(selected)]
```

### Chained Boolean Filters
```python
mask = (
    (df["Year"].isin(years))
    & (df["Revenue"].between(lo, hi))
    & (df["Deal_Won"] == True)
)
df_filtered = df[mask]
```

### Pivot Table
```python
pivot = pd.pivot_table(
    df,
    values="Revenue",
    index="Region",
    columns="Category",
    aggfunc="sum",
    margins=True,
    fill_value=0,
)
```

### Cache Expensive Computation
```python
@st.cache_data
def load_data():
    return pd.read_csv("data.csv")   # only runs once
```

### Download Button
```python
st.download_button(
    "Download CSV",
    data=df.to_csv(index=False).encode(),
    file_name="export.csv",
    mime="text/csv",
)
```