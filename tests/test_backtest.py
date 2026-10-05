from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from botcore.params import Params
from research.backtest import benchmark_equal_weight, benchmark_hold, build_market, run_backtest
from tests.conftest import make_panel

P = Params(min_history_days=120, min_vol=0.05)
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


def test_delisted_holding_is_liquidated_after_gap_with_haircut():
    panel = make_panel(drift=(0.004, -0.004, -0.004), vol=0.005)
    for k in panel:
        panel[k].loc["2020-12-01":, "AAAUSDT"] = np.nan
    res = run_backtest(build_market(panel, P), P, START)
    held_before = res.weights.loc["2020-11-30", "AAAUSDT"]
    assert held_before > 0
    # frozen during the gap, sold on day max_gap_days + 1 (known only then: no look-ahead)
    eq_frozen, eq_after = res.equity.loc["2020-12-03"], res.equity.loc["2020-12-04"]
    assert res.equity.loc["2020-11-30"] == pytest.approx(eq_frozen)
    assert eq_after == pytest.approx(eq_frozen * (1 - held_before * P.delist_haircut), rel=1e-6)
    assert res.weights.loc["2020-12-04":, "AAAUSDT"].eq(0).all()


def test_redenomination_while_held_is_not_profit():
    panel = make_panel(drift=(0.004, -0.004, -0.004), vol=0.005)
    for k in ("open", "high", "low", "close"):
        panel[k].loc["2020-12-01":, "AAAUSDT"] *= 1000
    res = run_backtest(build_market(panel, P), P, START)
    assert res.weights.loc["2020-11-30", "AAAUSDT"] > 0
    assert res.equity.max() < 2 * 10_000


def test_stop_fill_slips_toward_low_on_crash():
    panel = make_panel(drift=(0.004, -0.004, -0.004), vol=0.005)
    crash = pd.Timestamp("2020-11-01")
    panel["low"].loc[crash, "AAAUSDT"] = panel["close"].loc[crash, "AAAUSDT"] * 0.3
    m = build_market(panel, P)
    at_stop = run_backtest(m, replace(P, stop_fill=0.0), START).equity.loc[crash]
    slipped = run_backtest(m, replace(P, stop_fill=0.5), START).equity.loc[crash]
    assert slipped < at_stop


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
