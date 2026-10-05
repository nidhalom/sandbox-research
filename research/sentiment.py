import json
from pathlib import Path

import pandas as pd

from research.data import _get

URL = "https://api.alternative.me/fng/?limit=0&format=json"


def fetch_fear_greed() -> pd.Series:
    data = json.loads(_get(URL))["data"]
    s = pd.Series({pd.to_datetime(int(d["timestamp"]), unit="s").normalize(): float(d["value"]) for d in data})
    return s.sort_index().rename("fng")


def load_fear_greed(path) -> pd.Series:
    path = Path(path)
    if path.exists():
        return pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0].rename("fng")
    s = fetch_fear_greed()
    path.parent.mkdir(parents=True, exist_ok=True)
    s.to_csv(path)
    return s
