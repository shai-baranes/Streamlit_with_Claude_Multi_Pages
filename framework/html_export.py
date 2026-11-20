"""Collect rendered page content on a requested export run only."""
import json
import re
from html import escape
from html.parser import HTMLParser

import pandas as pd
from streamlit.runtime.scriptrunner import get_script_run_ctx

from framework.config import MAX_PREVIEW
from framework.state import WIDGETS


class _ReportText(HTMLParser):
    """Keep the tutorial's text formatting, excluding attributes and active content."""
    tags = {"b", "strong", "em", "i", "code", "br", "p", "div", "ul", "ol", "li"}

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.tags:
            self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in self.tags and tag != "br":
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        self.parts.append(escape(data))


_STYLE = """
* {box-sizing:border-box}
body {margin:auto; max-width:1100px; padding:clamp(12px,3vw,36px);
      font:16px/1.5 system-ui,sans-serif; color:#1e293b; background:white}
h1,h2,h3 {line-height:1.2}
.report-chart {min-width:0; margin:1rem 0}
.report-table {overflow:auto}
table {border-collapse:collapse; font-variant-numeric:tabular-nums}
th,td {text-align:start; padding:.3rem .65rem; border-bottom:1px solid #ccd5df}
thead button {font:inherit; color:inherit; border:0; background:none; cursor:pointer}
aside {background:#eff6ff; border-left:3px solid #3969ac; padding:.6rem 1rem; margin:1rem 0}
.setting {font-size:.9rem; margin:.2rem 0}
"""

_SORT_TABLES = """
for (const table of document.querySelectorAll(".report-table table")) {
  const body = table.tBodies[0];
  const headers = [...table.tHead.rows[table.tHead.rows.length - 1].cells];
  for (const [column, header] of headers.entries()) {
    const button = document.createElement("button");
    button.textContent = header.textContent;
    header.replaceChildren(button);
    button.onclick = () => {
      const ascending = header.getAttribute("aria-sort") !== "ascending";
      for (const th of headers) th.removeAttribute("aria-sort");
      header.setAttribute("aria-sort", ascending ? "ascending" : "descending");
      const sorted = [...body.rows].sort((a,b) => {
        const x = a.cells[column]?.textContent.trim() || "";
        const y = b.cells[column]?.textContent.trim() || "";
        const numeric = x && y && Number.isFinite(Number(x)) && Number.isFinite(Number(y));
        const order = numeric ? Number(x)-Number(y) : x.localeCompare(y, undefined, {numeric:true});
        return ascending ? order : -order;
      });
      body.append(...sorted);
    };
  }
}
"""

_PLOT = """
function renderPlot({parentElement, data}) {
  const figure = JSON.parse(data.figure);
  const layout = figure.layout || {};
  delete layout.width;
  const plot = parentElement.querySelector(".plot");
  Plotly.newPlot(plot, figure.data, layout, {...data.config, responsive:true})
    .then(() => { if (figure.frames?.length) Plotly.addFrames(plot, figure.frames); });
}
"""


def _arg(args, kwargs, index, name, default=None):
    return args[index] if len(args) > index else kwargs.get(name, default)


class HtmlReport:
    def __init__(self, title, slot):
        self.title, self.slot = title, slot
        self.blocks = []
        self.adapters = {}
        self.dependencies = set()
        self.error = None
        self.exclusions = 0
        self.closed = False
        # Streamlit replaces this mapping on each run, including interrupted reruns.
        self.run_cursors = get_script_run_ctx().cursors

    def is_current(self):
        ctx = get_script_run_ctx()
        return (not self.closed and not self.exclusions and ctx is not None
                and ctx.cursors is self.run_cursors)

    def rich_text(self, html):
        parser = _ReportText()
        parser.feed(html)
        parser.close()
        self.blocks.append("<aside>" + "".join(parser.parts) + "</aside>")

    def setting(self, label, value):
        if isinstance(value, (list, tuple)):
            value = ", ".join(map(str, value))
        self.blocks.append(f'<p class="setting"><b>{escape(str(label))}</b> · {escape(str(value))}</p>')

    def component(self, name, data, *, html, css, js, dependencies=()):
        """Register trusted assets once. A lazy data callable returns encoded JSON."""
        self.dependencies.update(dependencies)
        self.adapters[name] = (css, js)
        payload = (data() if callable(data) else json.dumps(data, ensure_ascii=True)).replace("<", r"\u003c")
        self.blocks.append(
            f'<section class="report-chart" data-renderer="{escape(name, quote=True)}">'
            f'{html}<script type="application/json">{payload}</script></section>'
        )

    def table(self, value, options):
        if not isinstance(value, pd.DataFrame):
            from pandas.io.formats.style import Styler
            value = value.data if isinstance(value, Styler) else pd.DataFrame(value)
        columns = options.get("column_order", value.columns)
        config = options.get("column_config") or {}
        visible = [c for c in columns if c in value and config.get(c, True) is not None]
        preview = value.iloc[:MAX_PREVIEW].loc[:, visible]
        hide_index = options.get("hide_index")
        index = not isinstance(value.index, pd.RangeIndex) if hide_index is None else not hide_index
        if config.get("_index", True) is None:
            index = False
        table = preview.to_html(index=index, escape=True, border=0, na_rep="")
        self.blocks.append(f'<div class="report-table">{table}</div>')

    def document(self):
        css = _STYLE + "\n".join(css for css, _ in self.adapters.values())
        scripts = ""
        if "plotly" in self.dependencies:
            from framework.plotly_assets import PLOTLY_SOURCE
            scripts = f"<script>{PLOTLY_SOURCE}</script>"
        for name, (_, js) in self.adapters.items():
            # Each adapter gets its own scope; no module imports or CDN on file://.
            scripts += f"""<script>(() => {{
{js}
for (const parentElement of document.querySelectorAll('[data-renderer="{name}"]')) {{
  const data = JSON.parse(parentElement.querySelector('script[type="application/json"]').textContent);
  {name}({{parentElement, data}});
}}
}})()</script>"""
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<meta http-equiv="Content-Security-Policy" content="connect-src \'none\'; '
                'img-src data: blob:; font-src data:; object-src \'none\'; base-uri \'none\'">'
                f'<title>{escape(self.title)}</title><style>{css}</style></head><body>'
                + "".join(self.blocks) + scripts + f"<script>{_SORT_TABLES}</script></body></html>")


_TEXT = {"title": "h1", "header": "h2", "subheader": "h3", "text": "pre", "caption": "p",
         "markdown": "p", "info": "p", "warning": "p", "error": "p", "success": "p"}
_CONTAINERS = {"container", "expander", "empty", "form"}


class ExportUI:
    """Forward normal calls and record supported output in emission order."""
    def __init__(self, target, report):
        self.target, self.report = target, report

    def begin_export_exclusion(self):
        self.report.exclusions += 1

    def end_export_exclusion(self):
        self.report.exclusions -= 1

    def finish_html_export(self):
        self.report.closed = True
        filename = re.sub(r'[^\w.-]+', '-', self.report.title).strip('-') or "report"
        try:
            if self.report.error:
                self.report.slot.warning(self.report.error)
                return
            self.report.slot.download_button("Download HTML", self.report.document().encode("utf-8"),
                                            file_name=f"{filename}.html", mime="text/html",
                                            on_click="ignore")
        finally:
            # Once the download is prepared, release its intermediate snapshots.
            self.report.blocks.clear()
            self.report.adapters.clear()

    def stop(self):
        # Early exits (for example, empty filters) still export the visible message.
        self.finish_html_export()
        self.target.stop()

    def __enter__(self):
        self.target.__enter__()
        return self

    def __exit__(self, *exc):
        return self.target.__exit__(*exc)

    def __getattr__(self, name):
        method = getattr(self.target, name)
        report = self.report
        # A fragment can rerun with its original page wrapper after download creation.
        if report.closed or report.exclusions:
            return method
        if name == "columns":
            def columns(*args, **kwargs):
                return [ExportUI(col, report) for col in method(*args, **kwargs)]
            return columns
        if name in _CONTAINERS:
            def container(*args, **kwargs):
                if name == "expander":
                    label = _arg(args, kwargs, 0, "label")
                    report.blocks.append(f"<h3>{escape(str(label))}</h3>")
                return ExportUI(method(*args, **kwargs), report)
            return container
        if name not in _TEXT and name not in WIDGETS and name not in {"plotly_chart", "dataframe", "table", "metric"}:
            return method

        def display(*args, **kwargs):
            result = method(*args, **kwargs)
            if name in WIDGETS:
                if kwargs.get("type") != "password":
                    report.setting(_arg(args, kwargs, 0, "label"), result)
            elif name == "metric":
                value = _arg(args, kwargs, 1, "value")
                delta = _arg(args, kwargs, 2, "delta")
                report.setting(_arg(args, kwargs, 0, "label"), value if delta is None else f"{value} ({delta})")
            elif name in {"dataframe", "table"}:
                report.table(_arg(args, kwargs, 0, "data"), kwargs)
            elif name == "plotly_chart":
                from plotly.io import to_json
                figure = _arg(args, kwargs, 0, "figure_or_data")
                report.component("renderPlot", {"figure": to_json(figure), "config": kwargs.get("config")},
                                 html='<div class="plot"></div>', css="", js=_PLOT, dependencies=("plotly",))
            else:
                body = str(_arg(args, kwargs, 0, "body"))
                if name == "markdown" and kwargs.get("unsafe_allow_html"):
                    report.rich_text(body)
                elif name == "markdown" and body.strip() == "---":
                    report.blocks.append("<hr>")
                else:
                    tag = _TEXT[name]
                    content = escape(body)
                    if name == "markdown":
                        content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
                    report.blocks.append(f"<{tag}>{content}</{tag}>")
            return result
        return display
