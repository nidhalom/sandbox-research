import numpy as np
import pandas as pd

from botcore.params import Params
from research.panel import load_panel
from research.universe import eligible_mask, is_excluded, series_breaks
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


def test_new_stablecoins_excluded():
    for s in ("RLUSDUSDT", "USDEUSDT", "BFUSDUSDT", "FRAXUSDT", "USDSBUSDT"):
        assert is_excluded(s), s


def test_low_volatility_coin_not_eligible():
    panel = make_panel(n_days=250, symbols=("AUSDT", "PEGUSDT"), drift=(0, 0))
    panel["close"]["PEGUSDT"] = 1.0 + 0.0001 * np.sin(np.arange(250))
    mask = eligible_mask(panel, Params(min_history_days=10))
    assert mask.iloc[-1].to_dict() == {"AUSDT": True, "PEGUSDT": False}


def test_price_jump_and_long_gap_are_breaks():
    idx = pd.date_range("2020-01-01", periods=30)
    close = pd.DataFrame({"REDENOM": np.r_[np.ones(10), np.full(20, 1000.0)],
                          "GAP": np.r_[np.ones(10), np.full(5, np.nan), np.ones(15)],
                          "SHORTGAP": np.r_[np.ones(10), np.full(2, np.nan), np.ones(18)]}, index=idx)
    b = series_breaks(close, Params(max_gap_days=3, break_ratio=20))
    assert b["REDENOM"].iloc[10] and b["REDENOM"].sum() == 1
    assert b["GAP"].iloc[15] and b["GAP"].sum() == 1
    assert not b["SHORTGAP"].any()


def test_break_resets_history_requirement():
    panel = make_panel(n_days=400, symbols=("AUSDT",), drift=(0,))
    panel["close"].iloc[300:310, 0] = np.nan
    mask = eligible_mask(panel, Params(min_history_days=180, max_gap_days=3))
    assert mask.iloc[299, 0] and not mask.iloc[350, 0]
