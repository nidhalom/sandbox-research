import numpy as np
import pandas as pd
import pytest

from botcore.ensemble import donchian_active, ensemble_fraction, hysteresis, run_book


def s(values):
    return pd.Series(values, index=pd.date_range("2022-01-01", periods=len(values)), dtype=float)


def test_donchian_enters_on_breakout_and_exits_below_trailing_midpoint():
    close = s([10, 10, 10, 12, 13, 11.4, 11.6, 11.2])
    a = donchian_active(close, 3)
    # day 3: 12 > max(10,10,10) -> enter, stop = (10+10)/2 = 10
    # day 4: stop = max(10, (12+10)/2=11)=11 ; day 5: stop=max(11,(13+10)/2=11.5)=11.5 -> 11.4 < 11.5 exits
    assert a.tolist() == [0, 0, 0, 1, 1, 0, 0, 0]


def test_donchian_uses_only_past_closes():
    close = s([10, 10, 10, 12, 13, 11.4, 11.6, 11.2])
    changed = close.copy()
    changed.iloc[6:] = 100.0
    assert donchian_active(close, 3).iloc[:6].tolist() == donchian_active(changed, 3).iloc[:6].tolist()


def test_ensemble_fraction_is_share_of_active_lookbacks():
    close = s(np.r_[np.full(10, 10.0), 20.0])
    f = ensemble_fraction(close, lookbacks=(2, 5, 20))
    assert f.iloc[-1] == pytest.approx(2 / 3)          # L=20 lacks history -> inactive


def test_hysteresis_switches_on_above_high_and_off_below_low():
    x = s([0.1, 0.35, 0.2, 0.12, 0.05, 0.2])
    assert hysteresis(x, on=0.30, off=0.10).tolist() == [0, 1, 1, 1, 0, 0]


def frame(rows, cols=("A",)):
    return pd.DataFrame(rows, columns=list(cols), index=pd.date_range("2022-01-01", periods=len(rows)), dtype=float)


def test_book_trades_at_next_open_with_costs():
    o = frame([[10], [20], [20]])
    c = frame([[10], [20], [30]])
    t = frame([[1.0], [1.0], [1.0]])
    f = frame([[1.0], [0.0], [0.0]]).astype(bool)
    eq = run_book(o, c, t, f, cost=0.01)
    assert eq.iloc[0] == pytest.approx(1.0)                         # decided at close day 0, nothing held yet
    units = 1.0 / 20 / 1.01                                         # bought at day-1 open, paying 1%
    assert eq.iloc[2] == pytest.approx(units * 30)


def test_book_band_skips_small_drift_but_force_trades():
    o = frame([[10, 10], [10, 10], [11, 10], [11, 10]], cols=("A", "B"))
    c = o.copy()
    t = frame([[0.5, 0.5]] * 4, cols=("A", "B"))
    nof = frame([[1, 1], [0, 0], [0, 0], [0, 0]], cols=("A", "B")).astype(bool)
    eq = run_book(o, c, t, nof, band=0.2, cost=0.0)
    assert eq.iloc[-1] == pytest.approx(0.5 * 1.1 + 0.5)            # 10% drift < 20% band: no trade


def test_held_coin_that_stops_trading_is_sold_at_half_its_last_close():
    o = frame([[10], [10], [np.nan], [np.nan], [np.nan], [np.nan], [np.nan]])
    c = frame([[10], [10], [np.nan], [np.nan], [np.nan], [np.nan], [np.nan]])
    t = frame([[1.0]] * 7)
    f = frame([[1.0]] + [[0.0]] * 6).astype(bool)
    eq = run_book(o, c, t, f, cost=0.0)
    assert eq.iloc[-1] == pytest.approx(0.5)


def test_funding_is_annualized_per_day_and_averaged_over_7_days():
    from research.funding import annualized_daily, funding_signal
    t = pd.date_range("2022-01-01", periods=8 * 3, freq="8h")
    f = pd.DataFrame({"time": t, "rate": 0.0001, "hours": 8.0})
    d = annualized_daily(f)
    assert d.iloc[0] == pytest.approx(0.0001 * 3 * 365)
    sig = funding_signal(f)
    assert np.isnan(sig.iloc[5]) and sig.iloc[6] == pytest.approx(0.0001 * 3 * 365)
