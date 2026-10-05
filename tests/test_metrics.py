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
