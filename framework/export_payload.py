"""Bounded JSON writing for interactive reports with embedded data."""
from datetime import date
from io import StringIO
import json
import math

import numpy as np
import pandas as pd


class InteractiveExportTooLarge(ValueError):
    """The escaped data payload exceeds the configured export budget."""


class PayloadWriter:
    def __init__(self, limit):
        self.limit = limit
        self.buffer = StringIO()

    def write(self, fragment):
        # ASCII JSON makes this the exact embedded UTF-8 size after escaping.
        fragment = fragment.replace("<", r"\u003c")
        if self.buffer.tell() + len(fragment) > self.limit:
            raise InteractiveExportTooLarge
        self.buffer.write(fragment)

    def value(self, value):
        self.write(json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False))

    def array(self, values):
        self.write("[")
        for index, value in enumerate(values):
            if index:
                self.write(",")
            self.value(value)
        self.write("]")

    def finish(self):
        return self.buffer.getvalue()


def json_cell(value):
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int) and abs(value) > 2**53 - 1:
        return str(value)  # Preserve identifiers beyond JavaScript's integer precision.
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value
