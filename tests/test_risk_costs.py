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
