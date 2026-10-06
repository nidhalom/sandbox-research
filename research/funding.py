"""Binance USDⓈ-M perpetual funding rates (used only as a signal; no futures position is taken)."""
import io
import urllib.parse
from pathlib import Path

import pandas as pd

from research.data import FILES, _csv_from_zip, _get, _list

PREFIX = "data/futures/um/monthly/fundingRate/"


def parse_funding_csv(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw))
    return pd.DataFrame({"time": pd.to_datetime(df["calc_time"], unit="ms"),
                         "rate": df["last_funding_rate"].astype(float),
                         "hours": df["funding_interval_hours"].astype(float)})


def download_funding(symbol: str = "BTCUSDT", out_dir="data/funding") -> Path:
    path = Path(out_dir) / f"{symbol}.parquet"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    _, keys = _list(f"{PREFIX}{symbol}/")
    zips = sorted(k for k in keys if k.endswith(".zip"))
    frames = [parse_funding_csv(_csv_from_zip(_get(f"{FILES}/{urllib.parse.quote(k)}"))) for k in zips]
    pd.concat(frames).drop_duplicates("time").sort_values("time").to_parquet(path, index=False)
    return path


def annualized_daily(f: pd.DataFrame) -> pd.Series:
    """Average funding per day, annualized (rate per interval × intervals per year)."""
    per_year = f["rate"] * (24 / f["hours"]) * 365
    return per_year.groupby(f["time"].dt.normalize()).mean()


def funding_signal(f: pd.DataFrame, window: int = 7) -> pd.Series:
    """7-day average of annualized funding, known at each day's close (UTC)."""
    return annualized_daily(f).rolling(window, min_periods=window).mean()
