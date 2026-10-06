import numpy as np
import pandas as pd
import pytest

from research.run_ideas import brake_weight, dyn_verdict, future_vol, vol_features, vol_train_end, vol_weight


def test_vol_weight_caps_at_base_and_scales_down():
    w = vol_weight(pd.Series([0.30, 0.60, 1.20]))
    assert w.tolist() == pytest.approx([0.5, 0.5, 0.25])


def test_brake_is_zero_below_200_day_average():
    close = pd.Series(np.r_[np.full(200, 100.0), 50.0, 150.0], index=pd.date_range("2020-01-01", periods=202))
    w = brake_weight(close)
    assert w.iloc[199] == 0.5 and w.iloc[200] == 0.0 and w.iloc[201] == 0.5


def test_vol_features_ignore_future_and_target_is_future():
    idx = pd.date_range("2020-01-01", periods=200)
    close = pd.Series(100 * np.exp(np.random.default_rng(1).normal(0, 0.03, 200).cumsum()), index=idx)
    fng = pd.Series(50.0, index=idx)
    close2 = close.copy()
    close2.iloc[150:] *= 2
    pd.testing.assert_frame_equal(vol_features(close, fng).iloc[:150], vol_features(close2, fng).iloc[:150])
    assert future_vol(close).iloc[-30:].isna().all()
    # target at t uses returns t+1..t+30: day 119 is untouched by the change at 150, day 120 sees it
    assert np.isclose(future_vol(close).iloc[119], future_vol(close2).iloc[119])
    assert not np.isclose(future_vol(close).iloc[120], future_vol(close2).iloc[120])


def test_vol_training_stops_before_target_is_known():
    assert vol_train_end(pd.Timestamp("2021-01-01")) == pd.Timestamp("2020-12-01")


def test_dyn_verdict_requires_beating_a1():
    btc = {"cagr": 0.3, "max_dd": -0.8, "sharpe": 0.8}
    a1 = {"cagr": 0.25, "max_dd": -0.5, "sharpe": 1.0}
    assert dyn_verdict({"cagr": 0.25, "max_dd": -0.3, "sharpe": 1.1}, btc, a1) == []
    assert dyn_verdict({"cagr": 0.25, "max_dd": -0.3, "sharpe": 0.9}, btc, a1) == [
        "Sharpe not above A1 (50/50 quarterly)"]
