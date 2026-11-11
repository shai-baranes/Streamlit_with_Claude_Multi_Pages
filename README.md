> For the server, session isolation, large CSV workflow, and tests, see [README_GPT.md](README_GPT.md).

## Launching the dashboard

### Execution arguments

| Argument | Accepted value | Default | Behavior |
|---|---|---|---|
| `CSV_PATH` (positional) | Server-local `.csv` path | None | Privately stage the file in each new session; wait for Apply columns. |
| `--csv_file PATH` | Server-local `.csv` path | None | Automatically apply available fixed columns and the full numeric Seconds interval once per new session; keep the form visible. Cannot be combined with positional CSV_PATH. |
| `--parquet true\|false` | `true` or `false`, case-insensitive | `false` | Set the initial experimental Parquet checkbox value, including automatic loading. Users may change it afterward. Works without a startup CSV. |
| `--debug` | Flag | Off | Enable foreground development/debug logging. |
| `--sample` | Flag | Off | Offer the explicit Load sample data button. |
| `--admin` | Flag | Off | Enable the separate loopback-only administration listener. |
| `--admin-port PORT` | Integer 1–65535 | `8502` | Administration port; must differ from dashboard port when administration is enabled. |
| `--port PORT` | TCP port | `8501` | Dashboard listening port. |
| `--address ADDRESS` | Bind address | `0.0.0.0` | Dashboard listening address; does not change the administration bind address. |
| `-h`, `--help` | Flag | — | Show launcher usage and exit. |

Windows PowerShell examples:

```powershell
.\.venv\Scripts\python.exe run_server.py
.\.venv\Scripts\python.exe run_server.py "C:\Data\file.csv"
.\.venv\Scripts\python.exe run_server.py --csv_file "C:\Data\file.csv" --parquet true
.\.venv\Scripts\python.exe run_server.py --csv_file "C:\Data\file.csv" --parquet false
```

macOS examples:

```sh
.venv/bin/python run_server.py --debug
.venv/bin/python run_server.py "/absolute/path/to/file.csv" --debug
.venv/bin/python run_server.py --csv_file "/absolute/path/to/file.csv" --parquet true --debug
.venv/bin/python run_server.py --csv_file "/absolute/path/to/file.csv" --parquet false --debug
```

`--csv_file` uses the same validation, limits, and atomic commit as Apply columns.
Available fixed fields load automatically; select additional fields and press Apply columns
for later changes. The Seconds slider initially spans the numeric minimum through maximum;
rows with invalid/missing Seconds are excluded when an interval is available. Without a usable
numeric interval, no time filter is applied. If no fixed fields exist, select additional columns
and apply manually. Parquet remains experimental, session-private, and falls back to CSV on
cache failure. The checkbox preference survives navigation and later uploads/sample selection;
those later sources still require Apply. Clear dataset empties the session without reloading the
startup file. A new browser session receives its own private startup copy and initial preferences.

### Direct Streamlit application arguments

Application arguments must follow Streamlit's `--` separator:

```sh
.venv/bin/streamlit run "Load CSV.py" -- --csv_file "/absolute/path/to/file.csv" --parquet true
.venv/bin/streamlit run "Load CSV.py" -- "/absolute/path/to/file.csv" --load-all
```

| Application argument | Default | Behavior |
|---|---|---|
| `CSV_PATH` | None | Stage privately and wait for Apply columns. |
| `--csv_file PATH` | None | Auto-apply fixed columns and full Seconds interval; form stays visible. |
| `--parquet true\|false` | `false` | Initial session checkbox/cache setting; accepted case-insensitively. |
| `--load-all` | Off | Requires positional CSV_PATH; loads every row and column and hides the projection form for that source. Cannot be combined with --csv_file and is not a run_server.py option. |

## Load a client-local CSV from Windows

On the server, start the dashboard with `python run_server.py` or the existing Windows service.
Client uploads use the same dashboard URL and port on the trusted LAN or VPN. The scripts
upload a CSV from the Windows client. The server option `--csv_file` instead opens a path
on the server for new sessions. Direct `streamlit run "Load CSV.py"` serves the dashboard UI only.

Keep both client scripts together on the Windows machine. Run either command:

```powershell
.\client_load_csv.ps1 -ServerUrl "http://192.168.1.177:8501" -CsvFile "C:\Engineering Data\flight.csv" -Parquet $false
.\client_load_csv.cmd "http://192.168.1.177:8501" "C:\Engineering Data\flight.csv" true
```

| PowerShell argument | CMD position | Default | Behavior |
|---|---|---|---|
| `-ServerUrl` | 1 | Required | Dashboard URL, including its port. |
| `-CsvFile` | 2 | Required for upload | Local CSV path. Quote paths with spaces. |
| `-Parquet` | 3 | False | Initial cache setting. Use `$true` or `$false` in PowerShell and `true` or `false` in CMD. Upload only. |
| `-StopAll` | 2 (`--stop-all`) | Off | Stop this terminal’s sessions on the specified server. Omit the CSV path and Parquet setting. |

The script opens a single-use link in the default browser after validation. Browser settings
determine whether it opens in a tab or window. The link expires after 10 minutes and creates an
independent session that applies the fixed fields over the full Seconds range. The projection
form stays available for adjustments. Run the script again if the link expires or the session
is lost after it was claimed. With `--admin` enabled, the browser session appears in the
loopback administration console once it connects. Pending uploads have no dashboard session.

Uploads are streamed to disk and use the existing CSV size and format limits. Staging accepts
two uploads at a time, eight in-flight or unclaimed files in total, and twice the per-file limit
in reserved bytes. The endpoint has no separate login. Keep access restricted to trusted
clients. The client transmits the CSV and launch token over the configured connection, so use
HTTPS when the network requires transport encryption.

### Stop this terminal’s client sessions

Run the stop command in the same PowerShell or Command Prompt session used to launch
the CSVs, with the same dashboard URL:

```powershell
.\client_load_csv.ps1 -ServerUrl "http://192.168.1.177:8501" -StopAll
.\client_load_csv.cmd "http://192.168.1.177:8501" --stop-all
```

Use updated scripts and restart the server with the updated `run_server.py` before
launching CSVs you want to stop this way. The command works without `--admin`. It closes
this terminal’s browser sessions on that server and cancels its active uploads and unused
launch links. Other terminals and servers keep running. A refresh that starts a new
browser session does not inherit ownership. The script sends an ownership credential over
the configured connection; use HTTPS if the network requires transport encryption.

Run the command before closing the terminal. Closing it does not end browser sessions,
and another terminal cannot recover the launch group. To clean up afterward, use **Clear
dataset** in the dashboard or terminate the session through server administration if
enabled. The stop command reports sessions still terminating: running work can delay
private-file cleanup and memory release. The server can reuse released memory even if
its reported RAM usage does not immediately drop.

If Stop All returns HTTP 405 while uploads still work, check which dashboard process
is listening at the client URL. Restart it with `run_server.py` from the updated
checkout. Restarting ends existing sessions, so relaunch any CSVs you still need.

### PowerShell says the script is not digitally signed

Use `client_load_csv.cmd` with the arguments shown above. Under `RemoteSigned`, it
asks before removing the download marker from an unsigned `.ps1` file. Approve only
after reviewing the file and confirming your organization allows it. If PowerShell
still blocks the script, the launcher prints the execution policies for each scope.

To check manually, run these commands in the folder containing `client_load_csv.ps1`.

```powershell
Get-ExecutionPolicy
Get-ExecutionPolicy -List
Get-Item -LiteralPath .\client_load_csv.ps1 -Stream Zone.Identifier -ErrorAction SilentlyContinue
```

- With `RemoteSigned`, if the last command reports `Zone.Identifier`, review the script
  and verify its source. If your organization permits it, run
  `Unblock-File -LiteralPath .\client_load_csv.ps1` and retry the same launch command.
  This removes the download marker from that file alone.
- With `AllSigned`, ask your administrator for a copy signed by a trusted publisher.
  With `Restricted`, use the browser uploader or ask your administrator about approved
  script execution.
- The CMD wrapper invokes the same PowerShell script. For manual upload, open the
  dashboard in the browser, choose **Upload**, select your CSV, and click **Apply columns**.

See [Microsoft's PowerShell execution policy guide](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies?view=powershell-5.1).

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

1. Open `http://127.0.0.1:8502` locally on the server, or open the same address after creating
   the SSH tunnel described below. Click **Connect**; no application token or password is required.
   SSH and the server operating-system account provide authentication for remote access.
2. Review the session ID and dataset before selecting **Terminate** and confirming. The selected
   session loses its data and settings. Other sessions remain available.
3. **Terminating** means native work is still finishing or file cleanup needs a retry. Completed
   sessions disappear from the table. Refreshing a terminated browser starts a fresh session;
   normal CLI startup-file staging still applies to that new session.
4. Click **Disconnect** to clear the table and stop browser refreshes. A prominent green or red
   panel shows whether this browser console is connected or disconnected and displays its URL.

`admin.log` remains under `~/.engineering-dashboard-admin/8502/` on macOS or
`%LOCALAPPDATA%\.engineering-dashboard-admin\8502\` on Windows and rotates at 1 MiB with three
backups. Port 8502 remains loopback-only and should not be exposed through a firewall or port forward.

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
# Nondefault administration port:
python admin.py --port 8503 sessions list
```

`inspect` and `--json` report bytes, Unix timestamps, and nullable metadata. Creation time is
first observed by the monitor (within approximately five seconds); last activity records server
page execution, not mouse movement or browser-only animation. Client addresses are observed TCP
peers: reverse proxies can obscure the original computer, and multiple tabs have separate IDs.
Loopback peers are labeled local; unresolvable addresses are unknown. No reverse-DNS lookup is performed.

Exit codes: **0** success, **1** confirmation declined, **2** unavailable server/configuration or
request failure, **3** rejected loopback host/origin, **4** unknown session, **5** termination pending.
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
to the LAN. Any OS account permitted to log into the server and execute the project CLI can use it.


### Additional self notes (for controlling the server cmds from remote machine):
_To access the admin dashboard locally or remotely through an SSH tunnel:_

first , run the server with the `--admin` option (and optionally `--admin-port` if you want to change the default port 8502):

```
</> powershell
.\.venv\Scripts\python.exe run_server.py --admin --admin-port 8502
``` 

or after triggering the virtual environment:
```
</> powershell
source .venv/bin/activate
python run_server.py --admin --admin-port 8502
``` 


and you can invoke the admin UI in your browser on the server machine by:  
http://127.0.0.1:8502   (and not http://localhost:8502 for this case, maybe to prevent easy control from remote machine)
Select **Connect**. No separate administration token is required.


Assuming Windows OpenSSH Server is enabled on the server and the remote Windows machine has the built-in SSH client:
From PowerShell on the remote Windows machine, create an SSH tunnel:

```
</> powershell
ssh -N -L 8502:127.0.0.1:8502 SERVER_USER@SERVER_IP

e.g.
ssh -N -L 8502:127.0.0.1:8502 dashboardadmin@192.168.1.50
```
you might be prompted to accept the server's fingerprint and enter the password (you password to unlock the account) for the server user account. After successful authentication, the SSH tunnel will be established, forwarding local port 8502 to the server's port 8502.


Keep that PowerShell window open. Then open this address on the remote machine:

http://127.0.0.1:8502

To use the CLI remotely, open another PowerShell window:

```
</> powershell
ssh SERVER_USER@SERVER_IP

(again provide user password if prompted)

```

After connecting to the Windows server, change to the project directory and run the `admin.py`
commands below. The CLI contacts `127.0.0.1:8502` directly and does not need a credential file.

For CLI administration without the browser tunnel:
```
</> poweshell
ssh SERVER_USER@SERVER_IP
cd "C:\[project path]"

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
- **Connect fails:** verify the SSH tunnel is still open, the URL is exactly `http://127.0.0.1:8502`, and the server was launched with `--admin`.
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
    return pd.read_csv("data.csv")  # only runs once
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



