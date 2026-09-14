"""Use the installed Plotly bundle so custom charts need no external CDN."""
from importlib.resources import files
import plotly

PLOTLY_SOURCE = files(plotly).joinpath('package_data', 'plotly.min.js').read_text(encoding='utf-8')
