> For the server, session isolation, large CSV workflow, and tests, see [README_GPT.md](README_GPT.md).

## Session administration (offline networks supported)

Administration is optional. Normal dashboard users still connect to port 8501 without signing in.
Enable the separate **server-only** console explicitly:

```sh
# macOS, from the project directory
.venv/bin/python run_server.py --debug --sample --admin
```

```powershell
# Windows, from the project directory
.\.venv\Scripts\python.exe run_server.py --admin
```

Open **http://127.0.0.1:8502** on the server machine. `--admin-port 8502` selects the admin port;
it must differ from `--port`. The admin listener always binds to IPv4 loopback, regardless of
the dashboard address. No external identity provider or internet connection is required.

| Function | Server UI | Local CLI | SSH from another computer |
|---|---|---|---|
| List connected and retained disconnected sessions | Table, refreshed every 5 seconds | `sessions list` | Same CLI command on server |
| Inspect client, page, dataset, rows and columns | Table | `sessions inspect ID` | Same CLI command on server |
| Compare estimated frame/upload/export RAM and private disk bytes | Table, MiB | `sessions list --json` or `inspect` | Same CLI command on server |
| View process RAM/CPU and available host RAM | Summary | `sessions list --json` | Same CLI command on server |
| Terminate one session | Confirm **Terminate** | `sessions terminate ID` | Same CLI command on server |

### Open the server UI

1. Run `python admin.py credential-path` using the server's virtual environment. It prints the
   path of the credential file, not the token. Read that protected file locally and paste its
   `token` into the console, then click **Connect**. The token stays only in page memory.
2. Review the session ID and dataset before selecting **Terminate** and confirming. The selected
   session loses its data and settings. Other sessions remain available.
3. **Terminating** means native work is still finishing or file cleanup needs a retry. Completed
   sessions disappear from the table. Refreshing a terminated browser starts a fresh session;
   normal CLI startup-file staging still applies to that new session.
4. Click **Disconnect** to clear the console's credential and table.

Credentials rotate each server launch. Default locations are
`~/.engineering-dashboard-admin/8502/credential.json` on macOS and
`%LOCALAPPDATA%\.engineering-dashboard-admin\8502\credential.json` on Windows.
The port directory has owner-only permissions on macOS; Windows ACLs grant the launching
account and SYSTEM access. `admin.log` in the same directory rotates at 1 MiB with three backups.
Do not copy tokens into Git, SSH command lines, or screenshots.

### Local CLI examples

Run from the project directory with its Python environment (replace `python` with
`.venv/bin/python` on macOS or `.\.venv\Scripts\python.exe` on Windows):

```sh
python admin.py sessions list
python admin.py sessions list --json
python admin.py sessions inspect SESSION_ID
python admin.py sessions terminate SESSION_ID
# For scripts: skip the interactive confirmation.
python admin.py sessions terminate SESSION_ID --yes
# Nondefault port and a service-account credential location:
python admin.py --port 8503 --credential-file "/protected/path/credential.json" sessions list
```

`inspect` and `--json` report bytes, Unix timestamps, and nullable metadata. Creation time is
first observed by the monitor (within approximately five seconds); last activity records server
page execution, not mouse movement or browser-only animation. Client addresses are observed TCP
peers: reverse proxies can obscure the original computer, and multiple tabs have separate IDs.
Loopback peers are labeled local; unresolvable addresses are unknown. No reverse-DNS lookup is performed.

Exit codes: **0** success, **1** confirmation declined, **2** unavailable server/configuration or
request failure, **3** rejected credential/origin, **4** unknown session, **5** termination pending.
After code 5, poll the list: disappearance confirms cleanup completed. Repeating termination while
pending is safe; targeting an already removed ID returns code 4.

### Remote CLI through SSH

Enable Windows **OpenSSH Server** or macOS **System Settings → General → Sharing → Remote Login**
on the server. Use an authorized OS account and SSH keys. Permit SSH only from the intended LAN/VPN;
the dashboard does not install SSH, change firewall rules, or grant account access automatically.
SSH itself and these commands work without external network access after installation.

From a terminal connecting to a Mac server (replace host, account, project path and session ID):

```sh
ssh admin@mac-server '"/Users/admin/Dashboard/.venv/bin/python" "/Users/admin/Dashboard/admin.py" sessions list'
ssh admin@mac-server '"/Users/admin/Dashboard/.venv/bin/python" "/Users/admin/Dashboard/admin.py" sessions inspect SESSION_ID'
ssh admin@mac-server '"/Users/admin/Dashboard/.venv/bin/python" "/Users/admin/Dashboard/admin.py" sessions terminate SESSION_ID --yes'
```

For a Windows server, an interactive SSH shell avoids nested PowerShell/SSH quoting problems:

```text
ssh admin@windows-server
powershell -NoProfile
```

Then run these commands **inside the server's PowerShell shell**, including the call operator `&`:

```powershell
& 'C:\Engineering Dashboard\.venv\Scripts\python.exe' 'C:\Engineering Dashboard\admin.py' sessions list
& 'C:\Engineering Dashboard\.venv\Scripts\python.exe' 'C:\Engineering Dashboard\admin.py' sessions inspect SESSION_ID
& 'C:\Engineering Dashboard\.venv\Scripts\python.exe' 'C:\Engineering Dashboard\admin.py' sessions terminate SESSION_ID --yes
```

SSH commands execute on the server and contact its loopback listener. They do not expose port 8502
to the LAN. Use the launching/service account, or have the OS administrator explicitly grant the
designated admin account read access to the credential and directory, then pass `--credential-file`.
An account's normal login alone does not grant another service account's credential access.


## Additional self notes (for controlling the server cmds from remote machine):
Assuming Windows OpenSSH Server is enabled on the server and the remote Windows machine has the built-in SSH client:
From PowerShell on the remote Windows machine, create an SSH tunnel:

```
</> powershell
ssh -N -L 8502:127.0.0.1:8502 SERVER_USER@SERVER_IP

e.g.
ssh -N -L 8502:127.0.0.1:8502 dashboardadmin@192.168.1.50
```

Keep that PowerShell window open. Then open this address on the remote machine:

http://127.0.0.1:8502

To retrieve the token remotely, open another PowerShell window:

```
</> powershell
ssh SERVER_USER@SERVER_IP
```

After connecting to the Windows server:
```

</> poweshell
.\.venv\Scripts\python.exe admin.py credential-path
Get-Content "$env:LOCALAPPDATA\.engineering-dashboard-admin\8502\credential.json"
```
If Streamlit runs as a Windows service, the credential may belong to its service account instead of your SSH account. Use the exact path printed by a command executed under that service account, or configure:

```
</> poweshell
.\.venv\Scripts\python.exe admin.py `
  --credential-file "C:\Protected\Admin\credential.json" `
  sessions list
```

For CLI administration without the browser tunnel:
```
</> poweshell
ssh SERVER_USER@SERVER_IP
cd "C:\Engineering Dashboard" # example for install/cloned path @ server side

.\.venv\Scripts\python.exe admin.py sessions list
.\.venv\Scripts\python.exe admin.py sessions inspect SESSION_ID
.\.venv\Scripts\python.exe admin.py sessions terminate SESSION_ID
```

For non-interactive termination:
```
</> poweshell
.\.venv\Scripts\python.exe admin.py sessions terminate SESSION_ID --yes
```

Port 22 must be allowed from the remote machine to the server. Port 8502 should remain closed to the LAN because SSH carries the admin connection securely.





### Windows service and troubleshooting

To enable administration in WinSW, add `--admin` (and optionally `--admin-port`) to the launcher
arguments in `deploy/service.xml.template`, then stop/reinstall/start the service as described in
[README_GPT.md](README_GPT.md#windows-service). Credentials live in the service account's profile,
not necessarily the interactive user's profile. The service account needs a writable local profile.

- **Connection refused:** check `--admin`, port, running service, and that the CLI executes on the server.
- **Credential rejected:** reconnect with the newly generated token after a restart; verify the port/account.
- **Permission denied:** use the service account or request narrowly scoped OS read access; do not make credentials world-readable.
- **Runtime unavailable:** read `admin.log`. The adapter uses Streamlit internals; validate compatibility before upgrading Streamlit.
- **RAM does not fall immediately:** retained object sizes are estimates, not process ownership accounting.
  DataFrame aliases are counted once, but shared underlying arrays, native buffers, serialization,
  temporary calculations and allocator overhead prevent exact accounting. Upload and export categories
  represent known retained buffers; browser RAM is excluded. Python may reuse freed memory without
  returning it to the OS. Native calculations cannot safely be force-killed inside the shared process.

Administration does not impose automatic idle timeouts, block users, or kill the shared server.
Windows service/SSH setup must be validated on the target Windows machine.

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
 - [python] uv pip install streamlit-aggrid (the way I was able to install st_aggrid python package in my Mac)

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


### Project Related
- Activate your virtual env: % source .venv/bin/activate
- Launch streamlit session: % streamlit run 'Load CSV.py'
> Once streamlit is running you can now launch the selenium app to capture the screens printout:
-                           % python3 my_selenium.py






