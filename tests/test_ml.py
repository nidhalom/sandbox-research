import numpy as np
import pandas as pd
import pytest

from research.run_ml import make_features, make_target, ml_verdict, strategy_returns, train_end


def series(n=200, seed=0):
    idx = pd.date_range("2019-01-01", periods=n, freq="D")
    close = pd.Series(100 * np.exp(np.random.default_rng(seed).normal(0, 0.02, n).cumsum()), index=idx)
    fng = pd.Series(np.arange(n, dtype=float), index=idx)
    return close, fng


def test_features_do_not_use_future_prices():
    close, fng = series()
    f1 = make_features(close, fng)
    close2 = close.copy()
    close2.iloc[150:] *= 3
    f2 = make_features(close2, fng)
    pd.testing.assert_frame_equal(f1.iloc[:150], f2.iloc[:150])


def test_missing_fear_greed_is_forward_filled_only():
    close, fng = series()
    gap = fng.drop(fng.index[100:103])
    f = make_features(close, gap)
    assert f["fng"].iloc[100:103].tolist() == [99.0, 99.0, 99.0]


def test_target_compares_close_seven_days_ahead():
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    close = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 0, 0], index=idx, dtype=float)
    t = make_target(close)
    assert t.iloc[0] == 1.0 and t.iloc[1] == 0.0 and t.iloc[3:].isna().all()


def test_training_stops_before_targets_are_known():
    assert train_end(pd.Timestamp("2021-01-01")) == pd.Timestamp("2020-12-24")


def test_strategy_returns_shift_positions_and_charge_switches():
    idx = pd.date_range("2024-01-01", periods=4, freq="D")
    close = pd.Series([100.0, 110.0, 121.0, 108.9], index=idx)
    proba = pd.Series([0.6, 0.6, 0.4, 0.4], index=idx)
    r = strategy_returns(close, proba, threshold=0.55, cost=0.01)
    assert r.tolist() == pytest.approx([-0.01, 0.10, 0.10 - 0.01, 0.0])


def test_ml_verdict():
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    good = {"sharpe": (0.6, 2.0)}
    r = pd.Series([0.01, 0.012, 0.011], index=idx)
    btc = pd.Series([0.01, -0.01, 0.01], index=idx)
    assert ml_verdict(r, btc, good) == []
    assert "Sharpe CI lower bound below 0.5" in ml_verdict(r, btc, {"sharpe": (0.1, 2.0)})
