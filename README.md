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
# > uv pip install -r requirements.txt (or uv pip sync requirements.txt)
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

### TODOs
- [x] Check if 'Select-All' is applicable on my restricted environment
- [x] If above, remove the 'All' filters *(above not met in older versions)*
- [x] Check if 'inject_css()' is applicable and needed?
- [x] Apply the simulated map for longitude / latitude
- [x] Utilize the Normalized chart where applicable (e.g. for the bar chart)
- [x] Apply the new color (to be taken from 'config.toml') simulated map for longitude / latitude
- [ ] Apply the time delta between 2 rows for the 'Stacked Values Table' page.
- [ ] 'pip install streamlit-aggrid' - for AgGrid version (so the selected row stays visibly highlighted inside the grid itself when switching OFF stacked-mode)
- [ ] from some reason, after aggrid we're asked to re-install pandas... (need to kill all python|streamlit instances and retry!)
- [ ] note that it is recommeded to backup the current .env (along with Stacjed_Values_Table #1) before trying version *_2* to which we need to install above!!!
- [ ] loading the CSV with several gaps (nulls) I get an error from the load_csv file...


### Aditional Notes on Python & Streamlit Versions Management (taken from MISC README)
 - [python] py --list (to see all installed python versions on the system)
 - [python] py -3.9 (to run python 3.9, if installed)
 - [python] python --version (to see the current python version in use; also >python -V)
 - [python] where python (to see the path of the current python executable in use)
 - [python] streamlit --version (to see the current Streamlit version in use)
 - [python] where streamlit (to see the path of the current Streamlit executable in use)
 - [python] <https://www.python.org/downloads/>(to down any prior released version of python)
 - [python] py -3.9 -m venv .venv (to create a virtual env using older python 3.9v) *or C:\Path\To\Python39\python.exe -m venv .venv*
 - [python] python -m pip install streamlit==1.2.0 (if wanting to install a specific [older] version of Streamlit)
 - [python] python -m pip install protobuf==3.20.0 (if wanting to install a specific [older] version of protobuf, which is a dependency for Streamlit)
 - [python] pip install "altair<5" (if already from active env; to be followed by installing a specific [older] version of Altair, which is a dependency for Streamlit)
 - [python] 

### wanting to replace .venv (to align with newer python installation)
-  [DOS]              >> .venv\Scripts\activate ; pip freeze > requirements.txt; deactivate
-  [DOS]              >> rmdir /s .venv
-  [pyenv|powershell] if 'pyenv' not installed, install pyenv via powershell: >> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine
-  [pyenv|powershell] followed by runnig the pyenv-win installer: >> Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/pyenv-win/pyenv-win/master/pyenv-win/install-pyenv-win.ps1" -OutFile "./install-pyenv-win.ps1"; &"./install-pyenv-win.ps1"
-  [pyenv|powershell] verify by (after close/opening powershell): >> pyenv --version
-  [pyenv|powershell] installing out python version: >> pyenv install 3.12.10
-  [UV]               UV alternative to install python 3.12 (outside the environment): >> uv run --python 3.12 python --version

-  [UV|powershell]    uv venv --python 3.12 (creating python 3.12 environment)
-  [UV]               python pin 3.12 (sometimes it may skip the '.python-version' file info; followd by uv ad ...)
-  [UV]               uv pip install -r requirements.txt (or 'uv pip sync requirements.txt'; note that we may prefer removing the versions)
-  [Mac]	      source .venv/bin/activate

### Prompt for perplexity:
 I'd like to add a dataframe table, based on 'synthetic_sales_data.csv' file, with st.multiselect() streamlit object.
these are the requirements for this object behavior:

imagine that we have a csv file with headers: 'time', 'applied_commands', 'state', 'mode', 'speed', 'temperatue', ...

1. the default view is empty. meaning that no column is selected and no data is shown in the table. the user can shall select the columns to be shown (from the csv headers) using st.multiselect() object.
2. the first element|(csv column) to be selected shall be deployed in table such that we get its rows only where the values of the first selected column have been changed (stacked mode). no need to display rows where the value of the first selected column is same as before (if values of fiorst selected column, corresponding rows\lines shall be skipped).
3. Per first element|header selection, the 'Time' column shall be added to its left side. (with corresponding values to the stacked displayed rows as dictated by request #2).
4. if additional columns are selected (once the first column is selected), their corresponding values shall be also displayed (without adding additional lines|rows); note also that all appended columns shall be deployed to the right of the first selected column (contrary to the 'Time' column).
5. columns to the right side of the first selected column can be easily removed without affecting the values of the remaining columns.
6. if the first selected column is removed (the one next to the 'Time' column),  the next row to be the new row right to the 'Time' column shall now be considered as 'the first element|(csv column) to be selected' and above rules are applies to it - meaning that the data is updated such that the visible rows are only the rows where the value of this column has changed.

let me know if need more clarifications.

-------------------------------

I would like to add functionality as folowing:
1. adding a checkbutton to our table, check by default
2. if we uncheck the button, the mask filter is off and all the rows depicted by the dataframe are displayed (for the selected columns)
3. if a grid was selected prior to uncheck cmd, the grid remains selected and visible - meaning that the table expands but the user doesn't have to screoll in order to find the priorly  selected grid.

this additional functionality is to allow to user to assess prior and post values on other columns adjacent to the value change of the anchor column

