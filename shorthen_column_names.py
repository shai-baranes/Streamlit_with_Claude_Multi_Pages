# this script mandates that the order in PLR sub file shall be such that we shall later be able to associated each column with origin (e.g. TBD bit to its specific BIT)
import pandas as pd
import re
from collections import Counter

df = pd.read_csv("my_csv.csv")

original_cols = list(df.columns)
base_names = [str(c).split("\\")[-1].strip() for c in original_cols]
base_counts = Counter(base_names)

new_cols = []
for col, base in zip(original_cols, base_names):
    col = str(col)

    if base_counts[base] == 1:
        new_name = base
    else:
        bracket = re.search(r"\[(\d+)\]", col)
        if bracket:
            diff = bracket.group(1)
        else:
            parts = [p for p in col.split("\\") if p]
            diff = None
            for p in reversed(parts[:-1]):
                m = re.search(r"(\d+)", p)
                if m:
                    diff = m.group(1)
                    break
            if diff is None:
                raise ValueError(f"Could not find differentiator for duplicated column: {col}")

        new_name = f"{base}_{diff}"

    new_cols.append(new_name)

if len(new_cols) != len(set(new_cols)):
    raise ValueError("Generated names are still not unique")

df.columns = new_cols
df.to_csv("shortened_columns_final.csv", index=False)