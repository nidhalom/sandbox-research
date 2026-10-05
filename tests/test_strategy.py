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
