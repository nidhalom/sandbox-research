# Phase 1 — Research Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline research engine that backtests the spec's long-only trend strategy on survivorship-free Binance spot data, validates it honestly, and writes a go/no-go report.

**Architecture:** `botcore/` holds pure strategy, risk and cost logic that phase 2's live bot will reuse unchanged. `research/` downloads data, builds a point-in-time universe, runs a daily event-driven backtest (decide at close, fill at next open, exchange-side stops intraday), tunes with walk-forward Optuna, validates (bootstrap CI, deflated Sharpe, PBO), and writes `reports/phase1-report.md`.

**Tech Stack:** Python 3.12, pandas 3, numpy, scipy, pyarrow, optuna, matplotlib, pytest.

**Spec:** `D:\sandbox\docs\specs\2026-10-05-trend-bot-design.md`

## Global Constraints

- **Git: local commits only** in `D:\sandbox` (hard rule 1). Commit at the end of each task; never push.
- All files under `D:\sandbox`; run commands from `D:\sandbox` with the venv active (`.venv\Scripts\activate`).
- Long-only spot, gross exposure ≤ 100%, single coin ≤ 30%, no leverage, no shorting.
- Portfolio volatility target 20% annualised; annualisation factor 365.
- Universe: top 10 USDT spot pairs by trailing 30-day quote volume; ≥ 180 days history; exclude stablecoins and leveraged tokens; include delisted coins.
- Signal windows default (20, 50, 100); vol window 30; covariance window 60.
- Stops 3 × ATR(14), trailed daily; cooldown 5 days after a stop.
- Rebalance band 2% of equity per coin.
- Brakes: −20% → half size; −30% → no new buys; −35% → flat and stop; resume from pause above −25%.
- Costs: fee 0.10% per side + half-spread 0.05% + impact 0.1 × √(notional / 30-day ADV).
- Decisions use data up to the previous close only; fills at today's open.
- Use `close / close.shift(1) - 1` for returns (pandas 3 `pct_change` fill semantics differ).

## Review Focus

1. **Coin delisted while held** → position liquidated at last close minus 10% haircut, not held forever at a stale price (test in Task 6).
2. **2025+ archive files use microsecond timestamps** → dates parse correctly, not year 57000 (test in Task 2).
3. **Coin with missing/zero volatility (new listing, flat price)** → weight 0, never inf/NaN (test in Task 4).
4. **Fewer than 10 eligible coins early in history** → strategy runs with the coins available (test in Task 3).
5. **All trend scores zero (bear market)** → 100% cash, no division by zero, equity unchanged (test in Task 6).

## File Structure

```
D:\sandbox\
├── requirements.txt
├── pytest.ini
├── botcore\__init__.py
├── botcore\params.py      Params dataclass: every tunable/default in one place
├── botcore\metrics.py     cagr, max_drawdown, sharpe, yearly_returns, summary
├── botcore\strategy.py    trend_scores, raw_weights, scale_to_target, compute_raw, weights_for_day
├── botcore\risk.py        BrakeState, update_brakes, atr
├── botcore\costs.py       trade_cost
├── research\__init__.py
├── research\data.py       archive listing + daily kline download → data\spot_1d\*.parquet
├── research\panel.py      load_panel → dict of wide DataFrames
├── research\universe.py   is_excluded, eligible_mask
├── research\backtest.py   Market, build_market, Result, run_backtest, benchmarks
├── research\validation.py bootstrap_ci, deflated_sharpe, pbo, daily_sr
├── research\sentiment.py  Fear & Greed history fetch/cache
├── research\tune.py       suggest, tune, walk_forward
├── research\report.py     go_no_go, write_report
├── research\run_phase1.py CLI entry point
└── tests\                 one test file per module + conftest.py
```

---

### Task 1: Project setup, Params, metrics

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `botcore/__init__.py`, `research/__init__.py`, `botcore/params.py`, `botcore/metrics.py`
- Test: `tests/test_metrics.py`, `tests/conftest.py`

**Interfaces:**
- Produces: `Params` (frozen dataclass, fields below); `cagr(r)`, `max_drawdown(r)`, `sharpe(r)`, `yearly_returns(r)`, `summary(r) -> dict` — all take a daily-returns `pd.Series`; `make_panel(...)` test fixture helper in `tests/conftest.py`.

- [ ] **Step 1: Create venv and config files**

`requirements.txt`:
```
pandas>=3.0
numpy>=2.0
scipy>=1.13
pyarrow>=17
optuna>=4.0
matplotlib>=3.9
pytest>=8.0
```
`pytest.ini`:
```
[pytest]
testpaths = tests
pythonpath = .
```
Run: `py -3.12 -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt`
Create empty `botcore/__init__.py` and `research/__init__.py`.

- [ ] **Step 2: Write `botcore/params.py`**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Params:
    # signal
    windows: tuple[int, int, int] = (20, 50, 100)
    vol_window: int = 30
    cov_window: int = 60
    # sizing
    vol_target: float = 0.20
    max_gross: float = 1.0
    max_single: float = 0.30
    band: float = 0.02
    # stops
    atr_window: int = 14
    atr_mult: float = 3.0
    stop_cooldown_days: int = 5
    # drawdown brakes
    brake_half: float = -0.20
    brake_pause: float = -0.30
    brake_stop: float = -0.35
    resume_level: float = -0.25
    stop_resume_days: int = 30  # backtest stand-in for the owner's manual /resume
    # universe
    universe_size: int = 10
    min_history_days: int = 180
    volume_window: int = 30
    # costs
    fee_rate: float = 0.001
    half_spread: float = 0.0005
    impact_coef: float = 0.1
    delist_haircut: float = 0.10
    # optional Fear & Greed filter (None = off)
    greed_threshold: float | None = None
    greed_scale: float = 0.5
```

- [ ] **Step 3: Write the failing metrics tests** — `tests/test_metrics.py`

```python
import numpy as np
import pandas as pd
import pytest

from botcore.metrics import cagr, max_drawdown, sharpe, summary, yearly_returns


def series(values, start="2021-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"))


def test_cagr_doubles_in_one_year():
    r = series([2 ** (1 / 365) - 1] * 365)
    assert cagr(r) == pytest.approx(1.0, rel=1e-6)


def test_max_drawdown_peak_to_trough():
    r = series([0.10, -0.50, 0.20])  # 1.1 -> 0.55 -> 0.66
    assert max_drawdown(r) == pytest.approx(-0.5)


def test_sharpe_zero_for_constant_returns():
    assert sharpe(series([0.0] * 10)) == 0.0


def test_sharpe_annualised_with_365():
    rng = np.random.default_rng(1)
    r = series(rng.normal(0.001, 0.01, 2000))
    expected = r.mean() / r.std() * np.sqrt(365)
    assert sharpe(r) == pytest.approx(expected)


def test_yearly_returns_compound_by_calendar_year():
    r = series([0.1, 0.1], start="2021-12-31")
    yr = yearly_returns(r)
    assert yr[2021] == pytest.approx(0.1) and yr[2022] == pytest.approx(0.1)


def test_summary_keys():
    assert set(summary(series([0.01, -0.01]))) == {"cagr", "max_dd", "sharpe"}
```

- [ ] **Step 4: Run to verify failure**

Run: `.venv\Scripts\python -m pytest tests/test_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'botcore.metrics'`

- [ ] **Step 5: Write `botcore/metrics.py`**

```python
import numpy as np
import pandas as pd

DAYS = 365


def equity_curve(r: pd.Series) -> pd.Series:
    return (1 + r.fillna(0)).cumprod()


def cagr(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) == 0:
        return 0.0
    return float((1 + r).prod() ** (DAYS / len(r)) - 1)


def max_drawdown(r: pd.Series) -> float:
    eq = equity_curve(r)
    return float((eq / eq.cummax() - 1).min())


def sharpe(r: pd.Series) -> float:
    r = r.dropna()
    s = r.std()
    if len(r) < 2 or s == 0 or np.isnan(s):
        return 0.0
    return float(r.mean() / s * np.sqrt(DAYS))


def yearly_returns(r: pd.Series) -> pd.Series:
    r = r.dropna()
    return (1 + r).groupby(r.index.year).prod() - 1


def summary(r: pd.Series) -> dict:
    return {"cagr": cagr(r), "max_dd": max_drawdown(r), "sharpe": sharpe(r)}
```

- [ ] **Step 6: Write the shared synthetic-data fixture** — `tests/conftest.py`

```python
import numpy as np
import pandas as pd


def make_panel(n_days=400, symbols=("AAAUSDT", "BBBUSDT", "CCCUSDT"),
               drift=(0.004, 0.0, -0.004), vol=0.02, seed=0, start="2020-01-01"):
    """Synthetic daily OHLCV panel in the same shape load_panel returns."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n_days, freq="D")
    close = pd.DataFrame(
        {s: 100 * np.exp(np.cumsum(d + vol * rng.standard_normal(n_days))) for s, d in zip(symbols, drift)},
        index=idx,
    )
    open_ = close.shift(1).fillna(close.iloc[0])
    high = np.maximum(open_, close) * 1.01
    low = np.minimum(open_, close) * 0.99
    qv = pd.DataFrame(1e7, index=idx, columns=close.columns)
    return {"open": open_, "high": high, "low": low, "close": close, "quote_volume": qv}
```

- [ ] **Step 7: Run to verify pass**

Run: `.venv\Scripts\python -m pytest tests/test_metrics.py -v`
Expected: 6 passed

---

### Task 2: Data download

**Files:**
- Create: `research/data.py`
- Test: `tests/test_data.py`

**Interfaces:**
- Produces: `list_usdt_symbols() -> list[str]`; `parse_kline_csv(raw: bytes) -> DataFrame[date, open, high, low, close, quote_volume]`; `download_symbol(symbol, out_dir: Path) -> Path | None`; `download_all(out_dir, workers=16, symbols=None) -> list[Path]`. Output files: `<out_dir>/<SYMBOL>.parquet`.

- [ ] **Step 1: Write the failing tests** — `tests/test_data.py`

```python
import io
import zipfile

import pandas as pd

from research import data

LISTING = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
<IsTruncated>false</IsTruncated>
<CommonPrefixes><Prefix>data/spot/monthly/klines/BTCUSDT/</Prefix></CommonPrefixes>
<CommonPrefixes><Prefix>data/spot/monthly/klines/ETHBTC/</Prefix></CommonPrefixes>
<CommonPrefixes><Prefix>data/spot/monthly/klines/LUNAUSDT/</Prefix></CommonPrefixes>
</ListBucketResult>"""

FILES = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
<IsTruncated>false</IsTruncated>
<Contents><Key>data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2024-12.zip</Key></Contents>
<Contents><Key>data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2024-12.zip.CHECKSUM</Key></Contents>
<Contents><Key>data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2025-01.zip</Key></Contents>
</ListBucketResult>"""

ROW_MS = b"1733011200000,100,110,90,105,1,1733097599999,5000,10,0,0,0\n"        # 2024-12-01, ms
ROW_US = b"1735689600000000,105,120,100,115,1,1735775999999999,6000,10,0,0,0\n"  # 2025-01-01, us


def zipped(csv: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("f.csv", csv)
    return buf.getvalue()


def test_list_usdt_symbols_keeps_only_usdt_pairs(monkeypatch):
    monkeypatch.setattr(data, "_get", lambda url, timeout=60: LISTING)
    assert data.list_usdt_symbols() == ["BTCUSDT", "LUNAUSDT"]


def test_parse_handles_milliseconds_and_microseconds():
    df = data.parse_kline_csv(ROW_MS + ROW_US)
    assert list(df["date"]) == [pd.Timestamp("2024-12-01"), pd.Timestamp("2025-01-01")]
    assert list(df["close"]) == [105.0, 115.0]
    assert list(df["quote_volume"]) == [5000.0, 6000.0]


def test_parse_skips_header_row():
    header = b"open_time,open,high,low,close,volume,close_time,quote_volume,count,tb,tq,ignore\n"
    assert len(data.parse_kline_csv(header + ROW_MS)) == 1


def test_download_symbol_writes_parquet(monkeypatch, tmp_path):
    def fake_get(url, timeout=60):
        if "prefix=" in url:
            return FILES
        return zipped(ROW_MS if "2024-12" in url else ROW_US)

    monkeypatch.setattr(data, "_get", fake_get)
    path = data.download_symbol("BTCUSDT", tmp_path)
    df = pd.read_parquet(path)
    assert len(df) == 2 and df["date"].is_monotonic_increasing


def test_download_symbol_skips_existing(monkeypatch, tmp_path):
    (tmp_path / "BTCUSDT.parquet").write_bytes(b"x")
    monkeypatch.setattr(data, "_get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    assert data.download_symbol("BTCUSDT", tmp_path) == tmp_path / "BTCUSDT.parquet"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python -m pytest tests/test_data.py -v`
Expected: FAIL with `ImportError: cannot import name 'data'`

- [ ] **Step 3: Write `research/data.py`**

```python
"""Download daily spot candles for every USDT pair, listed and delisted, from data.binance.vision."""
import io
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
FILES = "https://data.binance.vision"
NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
KLINE_PREFIX = "data/spot/monthly/klines/"


def _get(url: str, timeout: int = 60) -> bytes:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return resp.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def _list(prefix: str) -> tuple[list[str], list[str]]:
    """Return (sub-folder prefixes, file keys) under an S3 prefix, following pagination."""
    prefixes, keys, marker = [], [], ""
    while True:
        url = f"{BUCKET}?delimiter=/&prefix={prefix}" + (f"&marker={marker}" if marker else "")
        root = ET.fromstring(_get(url))
        prefixes += [p.text for p in root.findall("s3:CommonPrefixes/s3:Prefix", NS)]
        keys += [k.text for k in root.findall("s3:Contents/s3:Key", NS)]
        if root.findtext("s3:IsTruncated", namespaces=NS) != "true":
            return prefixes, keys
        marker = root.findtext("s3:NextMarker", namespaces=NS) or (keys or prefixes)[-1]


def list_usdt_symbols() -> list[str]:
    prefixes, _ = _list(KLINE_PREFIX)
    return sorted(s for s in (p.rstrip("/").split("/")[-1] for p in prefixes) if s.endswith("USDT"))


def parse_kline_csv(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), header=None, dtype=str)
    if not df.iloc[0, 0].isdigit():
        df = df.iloc[1:]
    t = pd.to_numeric(df[0]).astype("int64")
    t = t.where(t < 10**14, t // 1000)  # files from 2025 on use microseconds
    out = pd.DataFrame({"date": pd.to_datetime(t.values, unit="ms").normalize()})
    for col, name in [(1, "open"), (2, "high"), (3, "low"), (4, "close"), (7, "quote_volume")]:
        out[name] = pd.to_numeric(df[col]).astype(float).values
    return out


def _csv_from_zip(raw: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return z.read(z.namelist()[0])


def download_symbol(symbol: str, out_dir: Path) -> Path | None:
    path = Path(out_dir) / f"{symbol}.parquet"
    if path.exists():
        return path
    _, keys = _list(f"{KLINE_PREFIX}{symbol}/1d/")
    zips = sorted(k for k in keys if k.endswith(".zip"))
    if not zips:
        return None
    frames = [parse_kline_csv(_csv_from_zip(_get(f"{FILES}/{k}"))) for k in zips]
    df = pd.concat(frames).drop_duplicates("date").sort_values("date")
    df.to_parquet(path, index=False)
    return path


def download_all(out_dir, workers: int = 16, symbols: list[str] | None = None) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    symbols = symbols or list_usdt_symbols()

    def safe(sym):
        try:
            return download_symbol(sym, out_dir)
        except Exception as exc:  # one bad symbol must not stop the download
            print(f"skip {sym}: {exc}")
            return None

    with ThreadPoolExecutor(workers) as ex:
        return [p for p in ex.map(safe, symbols) if p]
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest tests/test_data.py -v`
Expected: 5 passed

---

### Task 3: Panel loader and point-in-time universe

**Files:**
- Create: `research/panel.py`, `research/universe.py`
- Test: `tests/test_panel_universe.py`

**Interfaces:**
- Consumes: parquet files from Task 2; `Params` (Task 1).
- Produces: `load_panel(data_dir) -> dict[str, DataFrame]` with keys `open, high, low, close, quote_volume` (index = daily dates, columns = symbols, NaN where not trading); `is_excluded(symbol) -> bool`; `eligible_mask(panel, p) -> DataFrame[bool]` (True = in universe at that day's close).

- [ ] **Step 1: Write the failing tests** — `tests/test_panel_universe.py`

```python
import numpy as np
import pandas as pd

from botcore.params import Params
from research.panel import load_panel
from research.universe import eligible_mask, is_excluded
from tests.conftest import make_panel


def test_load_panel_aligns_symbols_with_different_ranges(tmp_path):
    for sym, start, n in [("AUSDT", "2020-01-01", 3), ("BUSDT", "2020-01-02", 3)]:
        pd.DataFrame({"date": pd.date_range(start, periods=n), "open": 1.0, "high": 1.0,
                      "low": 1.0, "close": 1.0, "quote_volume": 1.0}).to_parquet(tmp_path / f"{sym}.parquet")
    panel = load_panel(tmp_path)
    assert list(panel["close"].index) == list(pd.date_range("2020-01-01", periods=4))
    assert np.isnan(panel["close"].loc["2020-01-01", "BUSDT"])


def test_exclusions():
    assert is_excluded("USDCUSDT") and is_excluded("FDUSDUSDT") and is_excluded("BTCUPUSDT")
    assert is_excluded("ETHDOWNUSDT")
    assert not is_excluded("JUPUSDT") and not is_excluded("BTCUSDT") and not is_excluded("SUPERUSDT")


def test_min_history_required():
    panel = make_panel(n_days=200)
    mask = eligible_mask(panel, Params(min_history_days=180))
    assert not mask.iloc[178].any() and mask.iloc[181].all()


def test_top_n_by_volume():
    panel = make_panel(n_days=200, symbols=("AUSDT", "BUSDT", "CUSDT"), drift=(0, 0, 0))
    panel["quote_volume"]["AUSDT"] = 3e7
    panel["quote_volume"]["CUSDT"] = 1e6
    mask = eligible_mask(panel, Params(min_history_days=10, universe_size=2))
    assert mask.iloc[-1].to_dict() == {"AUSDT": True, "BUSDT": True, "CUSDT": False}


def test_fewer_eligible_than_universe_size_still_works():
    panel = make_panel(n_days=200)
    mask = eligible_mask(panel, Params(min_history_days=10, universe_size=10))
    assert mask.iloc[-1].sum() == 3


def test_not_eligible_on_days_without_price():
    panel = make_panel(n_days=200)
    panel["close"].iloc[150:, 0] = np.nan
    mask = eligible_mask(panel, Params(min_history_days=10))
    assert not mask.iloc[160, 0]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python -m pytest tests/test_panel_universe.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.panel'`

- [ ] **Step 3: Write `research/panel.py`**

```python
from pathlib import Path

import pandas as pd

FIELDS = ["open", "high", "low", "close", "quote_volume"]


def load_panel(data_dir) -> dict[str, pd.DataFrame]:
    frames = {p.stem: pd.read_parquet(p).set_index("date") for p in sorted(Path(data_dir).glob("*.parquet"))}
    if not frames:
        raise FileNotFoundError(f"no parquet files in {data_dir}")
    idx = pd.date_range(min(f.index.min() for f in frames.values()),
                        max(f.index.max() for f in frames.values()), freq="D")
    return {f: pd.DataFrame({s: df[f] for s, df in frames.items()}).reindex(idx) for f in FIELDS}
```

- [ ] **Step 4: Write `research/universe.py`**

```python
import pandas as pd

from botcore.params import Params

STABLES = {
    "USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD", "PAX", "USDS", "UST", "USTC", "USDD", "PYUSD",
    "EURI", "AEUR", "XUSD", "USD1", "SUSD", "EUR", "GBP", "AUD", "TRY", "BRL", "RUB", "UAH", "NGN",
    "ZAR", "PLN", "RON", "ARS", "JPY", "MXN", "COP", "CZK", "BIDR", "IDRT", "BKRW",
}
LEVERAGED_UNDERLYINGS = {
    "BTC", "ETH", "BNB", "XRP", "LINK", "ADA", "DOT", "TRX", "XTZ", "EOS", "LTC", "BCH",
    "FIL", "SXP", "YFI", "UNI", "AAVE", "SUSHI", "1INCH", "XLM",
}


def is_excluded(symbol: str) -> bool:
    base = symbol.removesuffix("USDT")
    if base in STABLES:
        return True
    for suffix in ("UP", "DOWN", "BULL", "BEAR"):
        if base.endswith(suffix) and base[: -len(suffix)] in LEVERAGED_UNDERLYINGS:
            return True
    return False


def eligible_mask(panel: dict[str, pd.DataFrame], p: Params) -> pd.DataFrame:
    """True where a symbol is in the universe at that day's close (uses data up to that close only)."""
    close, qv = panel["close"], panel["quote_volume"]
    history = close.notna().cumsum()
    allowed = pd.Series({s: not is_excluded(s) for s in close.columns})
    ok = (history >= p.min_history_days) & close.notna() & allowed
    adv = qv.rolling(p.volume_window, min_periods=p.volume_window // 2).mean().where(ok)
    return adv.rank(axis=1, ascending=False, method="first") <= p.universe_size
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv\Scripts\python -m pytest tests/test_panel_universe.py -v`
Expected: 6 passed

---

### Task 4: Strategy (signal and sizing)

**Files:**
- Create: `botcore/strategy.py`
- Test: `tests/test_strategy.py`

**Interfaces:**
- Consumes: `Params`.
- Produces: `trend_scores(close, windows) -> DataFrame` in [0, 1]; `raw_weights(close, scores, vol_window) -> DataFrame`; `scale_to_target(raw: Series, cov: DataFrame, p) -> Series`; `compute_raw(close, p) -> DataFrame`; `weights_for_day(raw_row: Series, eligible_row: Series, returns_window: DataFrame, p) -> Series` (index = symbols with weight > 0). Phase 2 calls `compute_raw` + `weights_for_day` exactly as the backtest does.

- [ ] **Step 1: Write the failing tests** — `tests/test_strategy.py`

```python
import numpy as np
import pandas as pd
import pytest

from botcore.params import Params
from botcore.strategy import compute_raw, raw_weights, scale_to_target, trend_scores, weights_for_day
from tests.conftest import make_panel

IDX = pd.date_range("2020-01-01", periods=150)


def test_rising_series_scores_one_falling_scores_zero():
    close = pd.DataFrame({"UP": np.linspace(1, 2, 150), "DOWN": np.linspace(2, 1, 150)}, index=IDX)
    s = trend_scores(close, (20, 50, 100))
    assert s["UP"].iloc[-1] == 1.0 and s["DOWN"].iloc[-1] == 0.0


def test_scores_zero_before_enough_history():
    close = pd.DataFrame({"UP": np.linspace(1, 2, 150)}, index=IDX)
    assert trend_scores(close, (20, 50, 100))["UP"].iloc[10] == 0.0


def test_zero_volatility_gives_zero_weight_not_inf():
    close = pd.DataFrame({"FLAT": np.ones(150), "NEW": np.r_[np.full(140, np.nan), np.linspace(1, 2, 10)]}, index=IDX)
    w = raw_weights(close, pd.DataFrame(1.0, index=IDX, columns=close.columns), 30)
    assert np.isfinite(w.values).all() and (w.iloc[-1] == 0).all()


def test_scale_respects_target_and_caps():
    raw = pd.Series({"A": 1.0, "B": 1.0})
    cov = pd.DataFrame([[0.0001, 0], [0, 0.0001]], index=["A", "B"], columns=["A", "B"])  # 19% vol each
    w = scale_to_target(raw, cov, Params(vol_target=0.20))
    assert (w <= 0.30 + 1e-12).all() and w.sum() <= 1.0 + 1e-12


def test_scale_hits_vol_target_when_caps_do_not_bind():
    raw = pd.Series({"A": 1.0, "B": 1.0})
    daily_var = 0.04 ** 2
    cov = pd.DataFrame([[daily_var, 0], [0, daily_var]], index=["A", "B"], columns=["A", "B"])
    w = scale_to_target(raw, cov, Params(vol_target=0.20, max_single=1.0))
    port_vol = np.sqrt(w.values @ (cov.values * 365) @ w.values)
    assert port_vol == pytest.approx(0.20)


def test_scale_empty_when_all_zero():
    assert scale_to_target(pd.Series({"A": 0.0}), pd.DataFrame(), Params()).empty


def test_weights_for_day_excludes_ineligible():
    panel = make_panel(n_days=300, drift=(0.004, 0.004, 0.004))
    p = Params()
    raw = compute_raw(panel["close"], p)
    rets = panel["close"] / panel["close"].shift(1) - 1
    elig = pd.Series({"AAAUSDT": True, "BBBUSDT": False, "CCCUSDT": True})
    w = weights_for_day(raw.iloc[-1], elig, rets.iloc[-60:], p)
    assert "BBBUSDT" not in w.index and len(w) >= 1
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python -m pytest tests/test_strategy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'botcore.strategy'`

- [ ] **Step 3: Write `botcore/strategy.py`**

```python
"""Pure strategy logic shared by the backtester (phase 1) and the live bot (phase 2)."""
import numpy as np
import pandas as pd

from botcore.params import Params


def trend_scores(close: pd.DataFrame, windows) -> pd.DataFrame:
    """Average of sign(close - SMA(n)) over the windows, long-only (clipped at 0)."""
    s = sum(np.sign(close - close.rolling(n, min_periods=n).mean()) for n in windows) / len(windows)
    return s.clip(lower=0).fillna(0)


def raw_weights(close: pd.DataFrame, scores: pd.DataFrame, vol_window: int) -> pd.DataFrame:
    rets = close / close.shift(1) - 1
    vol = rets.rolling(vol_window, min_periods=vol_window).std() * np.sqrt(365)
    w = scores / vol
    return w.replace([np.inf, -np.inf], np.nan).fillna(0)


def scale_to_target(raw: pd.Series, cov: pd.DataFrame, p: Params) -> pd.Series:
    raw = raw[raw > 0]
    if raw.empty:
        return raw
    c = cov.reindex(index=raw.index, columns=raw.index).fillna(0).values * 365
    port_vol = float(np.sqrt(max(raw.values @ c @ raw.values, 0.0)))
    if port_vol == 0:
        return raw * 0.0
    w = (raw * (p.vol_target / port_vol)).clip(upper=p.max_single)
    gross = w.sum()
    return w * (p.max_gross / gross) if gross > p.max_gross else w


def compute_raw(close: pd.DataFrame, p: Params) -> pd.DataFrame:
    return raw_weights(close, trend_scores(close, p.windows), p.vol_window)


def weights_for_day(raw_row: pd.Series, eligible_row: pd.Series, returns_window: pd.DataFrame,
                    p: Params) -> pd.Series:
    """Target weights for the next open, from data up to the last close."""
    raw = raw_row.where(eligible_row.reindex(raw_row.index, fill_value=False).astype(bool), 0.0)
    cols = raw[raw > 0].index
    cov = returns_window[cols].cov(min_periods=p.cov_window // 2)
    return scale_to_target(raw[cols], cov, p)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest tests/test_strategy.py -v`
Expected: 7 passed

---

### Task 5: Risk brakes, ATR, and costs

**Files:**
- Create: `botcore/risk.py`, `botcore/costs.py`
- Test: `tests/test_risk_costs.py`

**Interfaces:**
- Consumes: `Params`.
- Produces: `BrakeState(peak: float, mode: str = "normal")` with modes `normal|half|paused|stopped`; `update_brakes(state, equity, p) -> BrakeState`; `atr(high, low, close, window) -> DataFrame`; `trade_cost(notional: float, adv_quote: float, p) -> float` (quote currency).

- [ ] **Step 1: Write the failing tests** — `tests/test_risk_costs.py`

```python
import numpy as np
import pandas as pd
import pytest

from botcore.costs import trade_cost
from botcore.params import Params
from botcore.risk import BrakeState, atr, update_brakes

P = Params()


@pytest.mark.parametrize("equity,mode", [(95, "normal"), (79, "half"), (69, "paused"), (64, "stopped")])
def test_brake_levels(equity, mode):
    assert update_brakes(BrakeState(peak=100), equity, P).mode == mode


def test_pause_holds_until_recovery_above_resume_level():
    s = update_brakes(BrakeState(peak=100), 69, P)
    s = update_brakes(s, 74, P)          # -26%: still paused
    assert s.mode == "paused"
    s = update_brakes(s, 76, P)          # -24%: resumes into half
    assert s.mode == "half"


def test_stopped_is_sticky():
    s = update_brakes(BrakeState(peak=100), 60, P)
    assert update_brakes(s, 99, P).mode == "stopped"


def test_peak_tracks_new_highs():
    assert update_brakes(BrakeState(peak=100), 120, P).peak == 120


def test_atr_constant_range():
    idx = pd.date_range("2020-01-01", periods=20)
    close = pd.DataFrame({"A": 100.0}, index=idx)
    out = atr(close + 1, close - 1, close, 14)
    assert np.isnan(out["A"].iloc[12]) and out["A"].iloc[-1] == pytest.approx(2.0)


def test_trade_cost_formula():
    p = Params(fee_rate=0.001, half_spread=0.0005, impact_coef=0.1)
    expected = 1000 * (0.001 + 0.0005 + 0.1 * np.sqrt(1000 / 1e7))
    assert trade_cost(1000, 1e7, p) == pytest.approx(expected)


def test_trade_cost_zero_and_missing_volume():
    assert trade_cost(0, 1e7, P) == 0.0
    assert trade_cost(1000, np.nan, P) == pytest.approx(1000 * (0.001 + 0.0005 + 0.01))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python -m pytest tests/test_risk_costs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'botcore.costs'`

- [ ] **Step 3: Write `botcore/risk.py`**

```python
from dataclasses import dataclass

import numpy as np
import pandas as pd

from botcore.params import Params


@dataclass(frozen=True)
class BrakeState:
    peak: float
    mode: str = "normal"  # normal | half | paused | stopped


def update_brakes(state: BrakeState, equity: float, p: Params) -> BrakeState:
    peak = max(state.peak, equity)
    if state.mode == "stopped":
        return BrakeState(peak, "stopped")
    dd = equity / peak - 1
    if dd <= p.brake_stop:
        mode = "stopped"
    elif dd <= p.brake_pause or (state.mode == "paused" and dd <= p.resume_level):
        mode = "paused"
    elif dd <= p.brake_half:
        mode = "half"
    else:
        mode = "normal"
    return BrakeState(peak, mode)


def atr(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, window: int) -> pd.DataFrame:
    prev = close.shift(1)
    tr = np.fmax(np.fmax((high - low).values, (high - prev).abs().values), (low - prev).abs().values)
    return pd.DataFrame(tr, index=close.index, columns=close.columns).rolling(window, min_periods=window).mean()
```

- [ ] **Step 4: Write `botcore/costs.py`**

```python
import numpy as np

from botcore.params import Params

MISSING_VOLUME_IMPACT = 0.01  # assume 1% impact when volume is unknown


def trade_cost(notional: float, adv_quote: float, p: Params) -> float:
    """Fee + half-spread + square-root market impact, in quote currency."""
    if notional == 0:
        return 0.0
    if adv_quote and not np.isnan(adv_quote) and adv_quote > 0:
        impact = p.impact_coef * np.sqrt(notional / adv_quote)
    else:
        impact = MISSING_VOLUME_IMPACT
    return float(notional * (p.fee_rate + p.half_spread + impact))
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv\Scripts\python -m pytest tests/test_risk_costs.py -v`
Expected: 10 passed

---

### Task 6: Backtester and benchmarks

**Files:**
- Create: `research/backtest.py`
- Test: `tests/test_backtest.py`

**Interfaces:**
- Consumes: `Params`, `compute_raw`, `weights_for_day`, `BrakeState`, `update_brakes`, `atr`, `trade_cost`, `eligible_mask`.
- Produces: `Market` dataclass; `build_market(panel, p, fng: Series | None = None) -> Market`; `Result(returns, equity, weights, trades, costs, stops)`; `run_backtest(m, p, start, end=None, initial=10_000.0) -> Result`; `benchmark_hold(close, symbol, start, end=None) -> Series`; `benchmark_equal_weight(m, start, end=None) -> Series`.

- [ ] **Step 1: Write the failing tests** — `tests/test_backtest.py`

```python
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from botcore.params import Params
from research.backtest import benchmark_equal_weight, benchmark_hold, build_market, run_backtest
from tests.conftest import make_panel

P = Params(min_history_days=120)
START = "2020-06-01"


def test_uptrend_is_bought_and_profits():
    panel = make_panel(drift=(0.004, 0.004, 0.004), vol=0.01)
    res = run_backtest(build_market(panel, P), P, START)
    assert res.trades > 0 and res.equity.iloc[-1] > 10_000


def test_all_downtrend_stays_in_cash():
    panel = make_panel(drift=(-0.004, -0.004, -0.004), vol=0.005)
    res = run_backtest(build_market(panel, P), P, START)
    assert res.trades == 0 and res.equity.iloc[-1] == pytest.approx(10_000)


def test_no_look_ahead():
    panel = make_panel(drift=(0.003, 0.0, 0.002))
    cut = pd.Timestamp("2020-10-01")
    altered = {k: v.copy() for k, v in panel.items()}
    for k in ("open", "high", "low", "close"):
        altered[k].loc[cut:] *= 1.7
    a = run_backtest(build_market(panel, P), P, START).equity
    b = run_backtest(build_market(altered, P), P, START).equity
    pd.testing.assert_series_equal(a.loc[: cut - pd.Timedelta(days=1)], b.loc[: cut - pd.Timedelta(days=1)])


def test_costs_reduce_equity():
    panel = make_panel(drift=(0.004, 0.002, 0.003))
    free = replace(P, fee_rate=0.0, half_spread=0.0, impact_coef=0.0)
    pricey = replace(P, fee_rate=0.01)
    m = build_market(panel, P)
    assert run_backtest(m, pricey, START).equity.iloc[-1] < run_backtest(m, free, START).equity.iloc[-1]


def test_weights_respect_caps():
    panel = make_panel(drift=(0.004, 0.004, 0.004))
    res = run_backtest(build_market(panel, P), P, START)
    assert (res.weights.sum(axis=1) <= 1.05).all() and (res.weights.max(axis=1) <= 0.36).all()


def test_delisted_holding_is_liquidated_with_haircut():
    panel = make_panel(drift=(0.004, -0.004, -0.004), vol=0.005)
    for k in panel:
        panel[k].loc["2020-12-01":, "AAAUSDT"] = np.nan
    res = run_backtest(build_market(panel, P), P, START)
    assert res.weights.loc["2020-12-05":, "AAAUSDT"].eq(0).all()
    held_before = res.weights.loc["2020-11-30", "AAAUSDT"]
    eq_before, eq_after = res.equity.loc["2020-11-30"], res.equity.loc["2020-12-01"]
    assert held_before > 0
    assert eq_after == pytest.approx(eq_before * (1 - held_before * P.delist_haircut), rel=1e-6)


def test_stop_triggers_on_crash():
    panel = make_panel(drift=(0.004, -0.004, -0.004), vol=0.005)
    crash = pd.Timestamp("2020-11-01")
    panel["low"].loc[crash, "AAAUSDT"] = panel["close"].loc[crash, "AAAUSDT"] * 0.5
    res = run_backtest(build_market(panel, P), P, START)
    assert res.stops >= 1


def test_benchmarks():
    panel = make_panel()
    m = build_market(panel, P)
    hold = benchmark_hold(m.close, "AAAUSDT", START)
    assert hold.index[0] == pd.Timestamp(START)
    ew = benchmark_equal_weight(m, START)
    assert len(ew) == len(hold) and np.isfinite(ew).all()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python -m pytest tests/test_backtest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.backtest'`

- [ ] **Step 3: Write `research/backtest.py`**

```python
"""Daily event-driven backtest. Decisions use data up to the previous close; orders fill at today's
open; exchange-side stops trigger intraday; equity is marked at the close."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from botcore.costs import trade_cost
from botcore.params import Params
from botcore.risk import BrakeState, atr, update_brakes
from botcore.strategy import compute_raw, weights_for_day
from research.universe import eligible_mask


@dataclass
class Market:
    close: pd.DataFrame
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    returns: pd.DataFrame
    adv: pd.DataFrame
    eligible: pd.DataFrame
    atr: pd.DataFrame
    last_valid: pd.Series
    fng: pd.Series | None = None


def build_market(panel: dict, p: Params, fng: pd.Series | None = None) -> Market:
    close = panel["close"]
    return Market(
        close=close, open=panel["open"], high=panel["high"], low=panel["low"],
        returns=close / close.shift(1) - 1,
        adv=panel["quote_volume"].rolling(p.volume_window, min_periods=1).mean(),
        eligible=eligible_mask(panel, p),
        atr=atr(panel["high"], panel["low"], close, p.atr_window),
        last_valid=close.apply(lambda s: s.last_valid_index()),
        fng=None if fng is None else fng.reindex(close.index).ffill(),
    )


@dataclass
class Result:
    returns: pd.Series
    equity: pd.Series
    weights: pd.DataFrame
    trades: int
    costs: float
    stops: int


def run_backtest(m: Market, p: Params, start, end=None, initial: float = 10_000.0) -> Result:
    idx = m.close.index
    dates = m.close.loc[start:end].index
    first = idx.get_loc(dates[0])
    if first < p.cov_window:
        raise ValueError("start must leave at least cov_window days of history")
    syms = list(m.close.columns)
    pos = {s: j for j, s in enumerate(syms)}
    n = len(syms)
    O, L = m.open.values, m.low.values
    lastC = m.close.ffill().values
    A, ADV = m.atr.values, m.adv.values
    raw = compute_raw(m.close, p)
    last_valid = m.last_valid.reindex(syms).values

    units = np.zeros(n)
    stop = np.full(n, np.nan)
    cooldown = np.zeros(n, dtype=int)
    cash = initial
    brakes = BrakeState(peak=initial)
    stopped_days = 0
    eq_hist = np.empty(len(dates))
    w_hist = np.zeros((len(dates), n))
    trades, costs, n_stops = 0, 0.0, 0

    for k in range(len(dates)):
        i = first + k
        today = idx[i]

        # 1) holdings in symbols that stopped trading for good: sell at last close minus haircut
        for j in np.flatnonzero(units > 0):
            if pd.isna(last_valid[j]) or today > last_valid[j]:
                cash += units[j] * lastC[i, j] * (1 - p.delist_haircut)
                units[j], stop[j] = 0.0, np.nan

        # 2) rebalance at today's open with information up to yesterday's close
        px_open = np.where(np.isnan(O[i]), lastC[i - 1], O[i])
        equity_open = cash + float(np.nansum(units * px_open))
        current_w = np.where(units > 0, units * px_open / equity_open, 0.0) if equity_open > 0 else np.zeros(n)
        target = np.zeros(n)
        if brakes.mode != "stopped":
            tw = weights_for_day(raw.iloc[i - 1], m.eligible.iloc[i - 1], m.returns.iloc[i - p.cov_window: i], p)
            for s, w in tw.items():
                target[pos[s]] = w
            if p.greed_threshold is not None and m.fng is not None:
                g = m.fng.iloc[i - 1]
                if not np.isnan(g) and g >= p.greed_threshold:
                    target *= p.greed_scale
            if brakes.mode == "half":
                target *= 0.5
            target[cooldown > 0] = 0.0
            if brakes.mode == "paused":
                target = np.minimum(target, current_w)

        tradable = ~np.isnan(O[i])
        diff = (target - current_w) * equity_open
        act = tradable & ((np.abs(target - current_w) > p.band) | ((target == 0) & (units > 0)))

        for j in np.flatnonzero(act & (diff < 0)):  # sells first, to fund buys
            notional = units[j] * O[i, j] if target[j] == 0 else min(-diff[j], units[j] * O[i, j])
            c = trade_cost(notional, ADV[i - 1, j], p)
            units[j] -= notional / O[i, j]
            cash += notional - c
            costs += c
            trades += 1
            if units[j] <= 1e-12:
                units[j], stop[j] = 0.0, np.nan

        buys = np.flatnonzero(act & (diff > 0))
        need = sum(diff[j] + trade_cost(diff[j], ADV[i - 1, j], p) for j in buys)
        scale = min(1.0, 0.999 * cash / need) if need > 0 else 1.0
        for j in buys:
            notional = diff[j] * scale
            c = trade_cost(notional, ADV[i - 1, j], p)
            units[j] += notional / O[i, j]
            cash -= notional + c
            costs += c
            trades += 1
            if np.isnan(stop[j]) and not np.isnan(A[i - 1, j]):
                stop[j] = O[i, j] - p.atr_mult * A[i - 1, j]

        # 3) exchange-side stops trigger intraday (gap below the stop fills at the open)
        for j in np.flatnonzero((units > 0) & ~np.isnan(stop)):
            if not np.isnan(L[i, j]) and L[i, j] <= stop[j]:
                px = min(O[i, j], stop[j]) if not np.isnan(O[i, j]) else stop[j]
                notional = units[j] * px
                c = trade_cost(notional, ADV[i - 1, j], p)
                cash += notional - c
                costs += c
                trades += 1
                n_stops += 1
                units[j], stop[j] = 0.0, np.nan
                cooldown[j] = p.stop_cooldown_days + 1

        # 4) mark to market at the close, trail stops, update brakes
        marks = np.nan_to_num(lastC[i])
        equity = cash + float(np.sum(units * marks))
        held = units > 0
        new_stop = lastC[i] - p.atr_mult * A[i]
        stop = np.where(held & ~np.isnan(new_stop), np.fmax(stop, new_stop), stop)
        cooldown = np.maximum(cooldown - 1, 0)
        brakes = update_brakes(brakes, equity, p)
        if brakes.mode == "stopped":
            stopped_days += 1
            if stopped_days > p.stop_resume_days:
                brakes, stopped_days = BrakeState(peak=equity), 0
        eq_hist[k] = equity
        if equity > 0:
            w_hist[k] = np.where(held, units * marks / equity, 0.0)

    equity_s = pd.Series(eq_hist, index=dates)
    rets = equity_s / equity_s.shift(1) - 1
    rets.iloc[0] = equity_s.iloc[0] / initial - 1
    return Result(rets, equity_s, pd.DataFrame(w_hist, index=dates, columns=syms), trades, costs, n_stops)


def benchmark_hold(close: pd.DataFrame, symbol: str, start, end=None) -> pd.Series:
    r = close[symbol] / close[symbol].shift(1) - 1
    return r.loc[start:end].fillna(0)


def benchmark_equal_weight(m: Market, start, end=None) -> pd.Series:
    """Equal weight across the universe chosen at the previous close; no costs (flatters the benchmark)."""
    members = m.eligible.shift(1, fill_value=False).astype(bool)
    return m.returns.where(members).mean(axis=1).loc[start:end].fillna(0)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest tests/test_backtest.py -v`
Expected: 8 passed

---

### Task 7: Validation statistics

**Files:**
- Create: `research/validation.py`
- Test: `tests/test_validation.py`

**Interfaces:**
- Consumes: daily-returns Series / DataFrame.
- Produces: `bootstrap_ci(r, n=2000, block=20, seed=0) -> dict[str, tuple[float, float]]` with keys `cagr, sharpe, max_dd` (5th, 95th percentile = 90% CI); `daily_sr(r) -> float` (non-annualised); `deflated_sharpe(r, trial_daily_srs: list[float]) -> float` (probability in [0, 1]); `pbo(trial_returns: DataFrame, S=16) -> float`.

- [ ] **Step 1: Write the failing tests** — `tests/test_validation.py`

```python
import numpy as np
import pandas as pd

from botcore.metrics import sharpe
from research.validation import bootstrap_ci, daily_sr, deflated_sharpe, pbo

IDX = pd.date_range("2019-01-01", periods=1500)


def test_bootstrap_ci_brackets_point_estimate():
    r = pd.Series(np.random.default_rng(0).normal(0.001, 0.02, 1500), index=IDX)
    ci = bootstrap_ci(r, n=500)
    assert ci["sharpe"][0] < sharpe(r) < ci["sharpe"][1]
    assert ci["max_dd"][0] <= ci["max_dd"][1] <= 0


def test_deflated_sharpe_high_for_single_strong_strategy():
    r = pd.Series(np.random.default_rng(1).normal(0.003, 0.02, 1500), index=IDX)
    assert deflated_sharpe(r, [daily_sr(r)]) > 0.95


def test_deflated_sharpe_penalises_many_trials():
    rng = np.random.default_rng(2)
    r = pd.Series(rng.normal(0.0008, 0.02, 1500), index=IDX)
    few = deflated_sharpe(r, list(rng.normal(0.0, 0.01, 2)))
    many = deflated_sharpe(r, list(rng.normal(0.0, 0.03, 500)))
    assert many < few


def test_pbo_about_half_for_pure_noise():
    M = pd.DataFrame(np.random.default_rng(3).normal(0, 0.01, (1600, 30)))
    assert 0.3 < pbo(M, S=8) < 0.7


def test_pbo_zero_when_one_trial_truly_dominates():
    M = pd.DataFrame(np.random.default_rng(4).normal(0, 0.01, (1600, 30)))
    M[0] += 0.01
    assert pbo(M, S=8) == 0.0
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python -m pytest tests/test_validation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.validation'`

- [ ] **Step 3: Write `research/validation.py`**

```python
from itertools import combinations

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

EULER = 0.5772156649


def _paths(x: np.ndarray, n: int, block: int, seed: int) -> np.ndarray:
    """Stationary bootstrap (Politis-Romano): resampled paths, shape (n, T)."""
    rng = np.random.default_rng(seed)
    T = len(x)
    restart = rng.random((n, T)) < 1 / block
    restart[:, 0] = True
    pos = np.arange(T)
    last = np.maximum.accumulate(np.where(restart, pos, 0), axis=1)
    starts = rng.integers(T, size=(n, T))
    idx = (np.take_along_axis(starts, last, axis=1) + (pos - last)) % T
    return x[idx]


def bootstrap_ci(r: pd.Series, n: int = 2000, block: int = 20, seed: int = 0) -> dict:
    x = r.dropna().values
    paths = _paths(x, n, block, seed)
    T = paths.shape[1]
    eq = np.cumprod(1 + paths, axis=1)
    stats = {
        "cagr": eq[:, -1] ** (365 / T) - 1,
        "sharpe": paths.mean(axis=1) / paths.std(axis=1, ddof=1) * np.sqrt(365),
        "max_dd": (eq / np.maximum.accumulate(eq, axis=1) - 1).min(axis=1),
    }
    return {k: (float(np.percentile(v, 5)), float(np.percentile(v, 95))) for k, v in stats.items()}


def daily_sr(r: pd.Series) -> float:
    x = r.dropna()
    s = x.std()
    return 0.0 if len(x) < 2 or s == 0 else float(x.mean() / s)


def deflated_sharpe(r: pd.Series, trial_daily_srs: list[float]) -> float:
    """Bailey & Lopez de Prado (2014): probability the true Sharpe exceeds the best expected by luck."""
    x = r.dropna().values
    T = len(x)
    sr = daily_sr(r)
    n_trials = len(trial_daily_srs)
    if n_trials > 1:
        sd = np.std(trial_daily_srs, ddof=1)
        sr0 = sd * ((1 - EULER) * norm.ppf(1 - 1 / n_trials) + EULER * norm.ppf(1 - 1 / (n_trials * np.e)))
    else:
        sr0 = 0.0
    g3, g4 = skew(x), kurtosis(x, fisher=False)
    denom = np.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr**2, 1e-12))
    return float(norm.cdf((sr - sr0) * np.sqrt(T - 1) / denom))


def _col_sr(X: np.ndarray) -> np.ndarray:
    s = X.std(axis=0, ddof=1)
    return np.divide(X.mean(axis=0), s, out=np.zeros(X.shape[1]), where=s > 0)


def pbo(trial_returns: pd.DataFrame, S: int = 16) -> float:
    """Probability of Backtest Overfitting via combinatorially symmetric cross-validation."""
    X = trial_returns.dropna().values
    N = X.shape[1]
    blocks = np.array_split(np.arange(len(X)), S)
    logits = []
    for chosen in combinations(range(S), S // 2):
        ins = np.concatenate([blocks[b] for b in chosen])
        oos = np.concatenate([blocks[b] for b in range(S) if b not in chosen])
        sr_oos = _col_sr(X[oos])
        best = int(np.argmax(_col_sr(X[ins])))
        omega = ((sr_oos < sr_oos[best]).sum() + 1) / (N + 1)
        logits.append(np.log(omega / (1 - omega)))
    return float(np.mean(np.array(logits) <= 0))
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest tests/test_validation.py -v`
Expected: 5 passed

---

### Task 8: Fear & Greed data and walk-forward tuning

**Files:**
- Create: `research/sentiment.py`, `research/tune.py`
- Test: `tests/test_sentiment_tune.py`

**Interfaces:**
- Consumes: `Market`, `run_backtest`, `Params`, `sharpe`.
- Produces: `fetch_fear_greed() -> Series` (daily index, values 0–100); `load_fear_greed(path) -> Series` (cached CSV, fetched if missing); `suggest(trial, base: Params) -> Params`; `tune(m, base, train_start, train_end, n_trials, seed=0, log=None) -> Params`; `WalkForward(returns: Series, chosen: dict[int, Params], trials: list[list[tuple[Params, Series]]])`; `walk_forward(m, base, first_test_year, last_test_year, train_start, n_trials) -> WalkForward`.

- [ ] **Step 1: Write the failing tests** — `tests/test_sentiment_tune.py`

```python
import json

import pandas as pd

from botcore.params import Params
from research import sentiment
from research.backtest import build_market
from research.tune import tune, walk_forward
from tests.conftest import make_panel


def test_fetch_fear_greed_parses_api(monkeypatch):
    payload = {"data": [{"value": "80", "timestamp": "1609545600"}, {"value": "20", "timestamp": "1609459200"}]}
    monkeypatch.setattr(sentiment, "_get", lambda url, timeout=60: json.dumps(payload).encode())
    s = sentiment.fetch_fear_greed()
    assert list(s.index) == [pd.Timestamp("2021-01-01"), pd.Timestamp("2021-01-02")]
    assert list(s.values) == [20.0, 80.0]


def test_load_fear_greed_uses_cache(monkeypatch, tmp_path):
    path = tmp_path / "fng.csv"
    pd.Series([50.0], index=pd.to_datetime(["2021-01-01"]), name="fng").to_csv(path)
    monkeypatch.setattr(sentiment, "_get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    assert sentiment.load_fear_greed(path).iloc[0] == 50.0


def test_tune_returns_params_within_search_space():
    m = build_market(make_panel(n_days=600), Params(min_history_days=120))
    best = tune(m, Params(min_history_days=120), "2020-06-01", "2021-03-31", n_trials=3)
    f, mid, slow = best.windows
    assert 10 <= f <= 30 and 40 <= mid <= 80 and 90 <= slow <= 200 and 2.0 <= best.atr_mult <= 5.0


def test_walk_forward_concatenates_out_of_sample_years():
    m = build_market(make_panel(n_days=1100, start="2019-01-01"), Params(min_history_days=120))
    wf = walk_forward(m, Params(min_history_days=120), 2021, 2021, train_start="2019-07-01", n_trials=2)
    assert wf.returns.index.min() == pd.Timestamp("2021-01-01")
    assert wf.returns.index.max() == pd.Timestamp("2021-12-31")
    assert set(wf.chosen) == {2021} and len(wf.trials[0]) == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python -m pytest tests/test_sentiment_tune.py -v`
Expected: FAIL with `ImportError: cannot import name 'sentiment'`

- [ ] **Step 3: Write `research/sentiment.py`**

```python
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
```

- [ ] **Step 4: Write `research/tune.py`**

```python
from dataclasses import dataclass, replace

import optuna
import pandas as pd

from botcore.metrics import sharpe
from botcore.params import Params
from research.backtest import Market, run_backtest

optuna.logging.set_verbosity(optuna.logging.WARNING)


def suggest(trial, base: Params) -> Params:
    return replace(
        base,
        windows=(trial.suggest_int("w_fast", 10, 30), trial.suggest_int("w_mid", 40, 80),
                 trial.suggest_int("w_slow", 90, 200)),
        atr_mult=trial.suggest_float("atr_mult", 2.0, 5.0),
        band=trial.suggest_float("band", 0.01, 0.05),
    )


def tune(m: Market, base: Params, train_start, train_end, n_trials: int, seed: int = 0,
         log: list | None = None) -> Params:
    def objective(trial):
        p = suggest(trial, base)
        r = run_backtest(m, p, train_start, train_end).returns
        if log is not None:
            log.append((p, r))
        return sharpe(r)

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n_trials)
    return suggest(optuna.trial.FixedTrial(study.best_params), base)


@dataclass
class WalkForward:
    returns: pd.Series
    chosen: dict
    trials: list


def walk_forward(m: Market, base: Params, first_test_year: int, last_test_year: int, train_start,
                 n_trials: int) -> WalkForward:
    """Tune on everything before each test year, trade that year with the winner, roll forward."""
    pieces, chosen, trials = [], {}, []
    for year in range(first_test_year, last_test_year + 1):
        log: list = []
        best = tune(m, base, train_start, f"{year - 1}-12-31", n_trials, seed=year, log=log)
        chosen[year] = best
        trials.append(log)
        pieces.append(run_backtest(m, best, f"{year}-01-01", f"{year}-12-31").returns)
    return WalkForward(pd.concat(pieces), chosen, trials)
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv\Scripts\python -m pytest tests/test_sentiment_tune.py -v`
Expected: 4 passed

---

### Task 9: Report, CLI, and the real run

**Files:**
- Create: `research/report.py`, `research/run_phase1.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `go_no_go(oos, benchmarks: dict[str, Series], ci: dict, pbo_value: float) -> tuple[dict[str, bool], bool]`; `write_report(path, sections: dict) -> Path`; CLI `python -m research.run_phase1 [--data data/spot_1d] [--trials 60] [--first-test-year 2021] [--skip-download]` writing `reports/phase1-report.md` and PNG charts.

- [ ] **Step 1: Write the failing tests** — `tests/test_report.py`

```python
import numpy as np
import pandas as pd

from research.report import go_no_go, write_report

IDX = pd.date_range("2021-01-01", periods=730)


def test_go_when_all_criteria_pass():
    oos = pd.Series(np.random.default_rng(0).normal(0.002, 0.01, 730), index=IDX)
    bench = {"Hold BTC": pd.Series(np.random.default_rng(1).normal(0.0, 0.03, 730), index=IDX)}
    checks, go = go_no_go(oos, bench, {"sharpe": (1.2, 4.0)}, 0.1)
    assert go and all(checks.values())


def test_no_go_when_pbo_high():
    oos = pd.Series(np.random.default_rng(0).normal(0.002, 0.01, 730), index=IDX)
    checks, go = go_no_go(oos, {}, {"sharpe": (1.2, 4.0)}, 0.6)
    assert not go and not checks["PBO < 0.3"]


def test_write_report_creates_markdown(tmp_path):
    path = write_report(tmp_path / "r.md", {"Verdict": "GO", "Details": "| a |\n|---|\n| 1 |"})
    text = path.read_text(encoding="utf-8")
    assert "## Verdict" in text and "GO" in text
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python -m pytest tests/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.report'`

- [ ] **Step 3: Write `research/report.py`**

```python
from pathlib import Path

import pandas as pd

from botcore.metrics import max_drawdown, sharpe


def go_no_go(oos: pd.Series, benchmarks: dict, ci: dict, pbo_value: float) -> tuple[dict, bool]:
    s = sharpe(oos)
    checks = {
        "Sharpe ≥ 1.0": s >= 1.0,
        "Sharpe 90% CI lower bound ≥ 0.5": ci["sharpe"][0] >= 0.5,
        "Max drawdown no worse than −35%": max_drawdown(oos) >= -0.35,
        "PBO < 0.3": pbo_value < 0.3,
    }
    for name, b in benchmarks.items():
        checks[f"Sharpe above {name}"] = s > sharpe(b.reindex(oos.index).fillna(0))
    return checks, all(checks.values())


def write_report(path, sections: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ["# Phase 1 Research Report", ""]
    for title, text in sections.items():
        body += [f"## {title}", "", text, ""]
    path.write_text("\n".join(body), encoding="utf-8")
    return path
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest tests/test_report.py -v`
Expected: 3 passed

- [ ] **Step 5: Write `research/run_phase1.py`**

```python
"""Phase 1 entry point: download data, backtest, tune walk-forward, validate, write the report."""
import argparse
from dataclasses import asdict, replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from botcore.metrics import equity_curve, summary, yearly_returns
from botcore.params import Params
from research.backtest import benchmark_equal_weight, benchmark_hold, build_market, run_backtest
from research.data import download_all
from research.panel import load_panel
from research.report import go_no_go, write_report
from research.sentiment import load_fear_greed
from research.tune import walk_forward
from research.validation import bootstrap_ci, daily_sr, deflated_sharpe, pbo

REPORTS = Path("reports")


def table(rows: dict[str, dict], fmt: dict[str, str]) -> str:
    cols = list(fmt)
    lines = ["| | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for name, vals in rows.items():
        lines.append(f"| {name} | " + " | ".join(format(vals[c], fmt[c]) for c in cols) + " |")
    return "\n".join(lines)


def yearly_table(series: dict[str, pd.Series]) -> str:
    df = pd.DataFrame({k: yearly_returns(v) for k, v in series.items()})
    lines = ["| Year | " + " | ".join(df.columns) + " |", "|---" * (len(df.columns) + 1) + "|"]
    for year, row in df.iterrows():
        lines.append(f"| {year} | " + " | ".join(f"{v:+.1%}" for v in row) + " |")
    return "\n".join(lines)


def chart(series: dict[str, pd.Series], path: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    for name, r in series.items():
        eq = equity_curve(r)
        ax1.plot(eq.index, eq.values, label=name)
        ax2.plot(eq.index, (eq / eq.cummax() - 1).values, label=name)
    ax1.set_yscale("log")
    ax1.set_title("Growth of 1 (log scale)")
    ax2.set_title("Drawdown")
    ax1.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/spot_1d")
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--first-test-year", type=int, default=2021)
    ap.add_argument("--train-start", default="2019-01-01")
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args(argv)

    if not args.skip_download:
        print("downloading data (cached files are skipped)...")
        download_all(args.data)
    panel = load_panel(args.data)
    base = Params()
    market = build_market(panel, base, load_fear_greed("data/fear_greed.csv"))
    start = f"{args.first_test_year}-01-01"
    last_year = market.close.index[-1].year
    print(f"data {market.close.index[0].date()} -> {market.close.index[-1].date()}, {market.close.shape[1]} symbols")

    untuned = run_backtest(market, base, start)
    greed = run_backtest(market, replace(base, greed_threshold=80), start)
    print(f"walk-forward {args.first_test_year}-{last_year}, {args.trials} trials per fold...")
    wf = walk_forward(market, base, args.first_test_year, last_year, args.train_start, args.trials)

    benchmarks = {"Hold BTC": benchmark_hold(market.close, "BTCUSDT", start),
                  "Equal-weight universe": benchmark_equal_weight(market, start)}
    last_fold = wf.trials[-1]
    pbo_value = pbo(pd.DataFrame({k: r for k, (_, r) in enumerate(last_fold)}))
    dsr = deflated_sharpe(wf.returns, [daily_sr(r) for _, r in last_fold])
    ci = bootstrap_ci(wf.returns)
    checks, go = go_no_go(wf.returns, benchmarks, ci, pbo_value)

    strategies = {"Walk-forward tuned (primary)": wf.returns, "Untuned defaults": untuned.returns,
                  "Untuned + Fear&Greed filter": greed.returns, **benchmarks}
    REPORTS.mkdir(exist_ok=True)
    chart(strategies, REPORTS / "phase1-equity.png")

    fmt = {"cagr": "+.1%", "max_dd": ".1%", "sharpe": ".2f"}
    chosen = "\n".join(f"- {y}: windows={p.windows}, atr_mult={p.atr_mult:.2f}, band={p.band:.3f}"
                       for y, p in wf.chosen.items())
    verdict = "**GO**: proceed to phase 2." if go else "**NO-GO**: do not build the live bot on this strategy yet."
    sections = {
        "Verdict": verdict + "\n\n" + "\n".join(f"- {'✅' if ok else '❌'} {name}" for name, ok in checks.items()),
        "Out-of-sample results": table({k: summary(v) for k, v in strategies.items()}, fmt)
                                 + "\n\n![equity](phase1-equity.png)",
        "Yearly returns": yearly_table(strategies),
        "Confidence (90%, stationary bootstrap) for the primary strategy":
            f"- CAGR: {ci['cagr'][0]:+.1%} to {ci['cagr'][1]:+.1%}\n"
            f"- Sharpe: {ci['sharpe'][0]:.2f} to {ci['sharpe'][1]:.2f}\n"
            f"- Max drawdown: {ci['max_dd'][0]:.1%} to {ci['max_dd'][1]:.1%}",
        "Overfitting checks": f"- PBO (last fold, {len(last_fold)} trials): {pbo_value:.2f}\n"
                              f"- Deflated Sharpe probability: {dsr:.2f}",
        "Parameters chosen each year": chosen,
        "Trading activity (untuned run)": f"- Trades: {untuned.trades}\n- Stops hit: {untuned.stops}\n"
                                          f"- Total costs: {untuned.costs:,.0f} USDT on 10,000 start",
        "Caveats": "- Each walk-forward year restarts with fresh capital and brake state.\n"
                   "- Untuned defaults were picked after a probe on 2020–2026 data, so they are not "
                   "truly out-of-sample; the walk-forward line is the honest one.\n"
                   "- Equal-weight benchmark pays no costs.\n"
                   "- Data ends at the last complete month in the Binance archive.",
        "Base parameters": "```\n" + "\n".join(f"{k} = {v}" for k, v in asdict(base).items()) + "\n```",
    }
    path = write_report(REPORTS / "phase1-report.md", sections)
    print(f"report written: {path.resolve()}  verdict: {'GO' if go else 'NO-GO'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the whole test suite**

Run: `.venv\Scripts\python -m pytest -q`
Expected: all tests pass (54 tests)

- [ ] **Step 7: Run phase 1 for real**

Run: `.venv\Scripts\python -m research.run_phase1 --trials 60`
Expected: download of ~600+ USDT symbols into `data\spot_1d\`, then `report written: D:\sandbox\reports\phase1-report.md  verdict: GO|NO-GO`. Read the report and sanity-check: universe contains real coins (BTC, ETH…), no year shows impossible returns (> +2000%), costs are non-zero.

---

### Task 10: Independent audit (Fable 5.1)

**Files:**
- Modify: whatever the audit finds wrong (with a failing test first for each fix)
- Create: `reports/phase1-audit.md`

- [ ] **Step 1: Dispatch the audit** — Agent tool, `model: "fable"`, prompt:

> Audit the trading research engine in `D:\sandbox` (spec: `docs/specs/2026-10-05-trend-bot-design.md`, plan: `docs/plans/2026-10-05-phase1-research-engine.md`, report: `reports/phase1-report.md`). Hunt for: look-ahead bias, data leakage between train and test, survivorship bias, wrong cost or fee accounting, wrong timestamps, wrong annualisation, statistical errors in PBO / deflated Sharpe / bootstrap, and any way the reported profit could be fake. Do not use git. Do not modify files. Write findings to `reports/phase1-audit.md`, ranked by severity, each with file:line, why it matters, and the concrete fix.

- [ ] **Step 2: Fix every confirmed finding** — for each: write a failing test reproducing it, fix, run `.venv\Scripts\python -m pytest -q`.

- [ ] **Step 3: Re-run phase 1** — `.venv\Scripts\python -m research.run_phase1 --skip-download --trials 60` and report the final verdict and numbers to the owner.
