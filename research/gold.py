"""Gold price history: COMEX futures (Yahoo GC=F) before PAXG existed, PAXG afterwards."""
import json
from pathlib import Path

import pandas as pd

SWITCH = "2020-09-01"


def load_gc(path) -> pd.Series:
    j = json.loads(Path(path).read_text())["chart"]["result"][0]
    s = pd.Series(j["indicators"]["quote"][0]["close"],
                  index=pd.to_datetime(j["timestamp"], unit="s").normalize(), dtype=float).dropna()
    return s[~s.index.duplicated(keep="last")].rename("gc")


def splice(gc: pd.Series, paxg: pd.Series, index: pd.DatetimeIndex, switch: str = SWITCH) -> pd.Series:
    """Daily gold on `index`: GC returns before `switch`, PAXG returns from it, forward-filled only."""
    gc = gc.reindex(gc.index.union(index)).ffill().reindex(index)
    paxg = paxg.reindex(paxg.index.union(index)).ffill().reindex(index)
    r = gc.pct_change()
    after = index >= pd.Timestamp(switch)
    r[after] = paxg.pct_change()[after]
    return (1 + r.fillna(0)).cumprod() * gc.iloc[0]


def build_prices(data_dir="data") -> pd.DataFrame:
    def close(sym):
        c = pd.read_parquet(Path(data_dir) / "spot_1d" / f"{sym}USDT.parquet").set_index("date")["close"]
        c.index = pd.to_datetime(c.index)
        return c
    btc = close("BTC").loc[:"2026-09-30"]
    gold = splice(load_gc(Path(data_dir) / "gold_gc_yahoo.json"), close("PAXG"), btc.index)
    return pd.DataFrame({"BTC": btc, "GOLD": gold})
