import numpy as np
import pandas as pd
import pytest

from research.run_core import (core_verdict, exit_half_at_target, exit_staged, independent_count,
                               load_closes, months_later, plan_deposits, plan_gain)


def test_load_closes_keeps_only_common_days(tmp_path):
    d = pd.date_range("2020-08-25", periods=6, freq="D")
    pd.DataFrame({"date": d, "close": range(6)}).to_parquet(tmp_path / "BTCUSDT.parquet")
    pd.DataFrame({"date": d[3:], "close": range(3)}).to_parquet(tmp_path / "PAXGUSDT.parquet")
    df = load_closes(tmp_path, ["BTC", "PAXG"])
    assert df.index[0] == d[3] and len(df) == 3 and not df.isna().any().any()


def test_deposit_on_missing_day_moves_to_next_day():
    idx = pd.DatetimeIndex(["2024-01-01", "2024-04-02", "2024-07-01"])
    deps = plan_deposits(idx, pd.Timestamp("2024-01-01"), [(0, 2000.0), (3, 500.0), (6, 500.0)])
    assert deps == {idx[0]: 2000.0, idx[1]: 500.0, idx[2]: 500.0}


def test_horizon_past_data_end_is_skipped():
    px = pd.DataFrame({"A": 1.0}, index=pd.date_range("2024-01-01", periods=100, freq="D"))
    assert months_later(px.index, px.index[0], 12) is None
    assert plan_gain(px, {"A": 1.0}, "none", px.index[0], [(0, 100.0)], exit_staged(12), 12) is None


def test_half_sold_at_target_before_last_deposit_and_rest_at_horizon():
    idx = pd.date_range("2024-01-01", "2026-08-01", freq="D")
    price = pd.Series(1.0, index=idx)
    price.loc["2024-02-01":] = 2.0          # +100% after one month, before the month-3 deposit
    px = pd.DataFrame({"A": price})
    plan = [(0, 2000.0), (3, 500.0), (6, 500.0)]
    g = plan_gain(px, {"A": 1.0}, "none", idx[0], plan, exit_half_at_target(30, 0.30), 30)
    # half of 4000 sold 2024-02-01 -> 2000; remaining 2000 + 1000 deposited at price 2 -> 3000 at end
    assert g == pytest.approx((2000 + 3000) / 3000 - 1, abs=0.01)  # 0.15% costs


def test_never_hitting_target_sells_everything_at_horizon():
    idx = pd.date_range("2024-01-01", "2026-08-01", freq="D")
    px = pd.DataFrame({"A": 1.0}, index=idx)
    g = plan_gain(px, {"A": 1.0}, "none", idx[0], [(0, 3000.0)], exit_half_at_target(30, 0.30), 30)
    assert g == pytest.approx(0.0, abs=0.01)


def test_staged_exit_sells_three_equal_parts():
    idx = pd.date_range("2024-01-01", "2026-08-01", freq="D")
    price = pd.Series(1.0, index=idx)
    for m, p in [(22, 2.0), (23, 3.0), (24, 4.0)]:
        price.loc[months_later(idx, idx[0], m):] = p
    px = pd.DataFrame({"A": price})
    g = plan_gain(px, {"A": 1.0}, "none", idx[0], [(0, 300.0)], exit_staged(24), 24)
    assert g == pytest.approx((100 * 2 + 100 * 3 + 100 * 4) / 300 - 1, abs=0.01)


def test_independent_count_greedy_non_overlapping():
    starts = pd.date_range("2020-01-06", "2022-12-26", freq="W-MON")
    assert independent_count(starts, 12) == 3


def test_core_verdict():
    btc = {"cagr": 0.30, "max_dd": -0.77, "sharpe": 0.8}
    b3 = {"cagr": 0.20, "max_dd": -0.40, "sharpe": 0.9}
    assert core_verdict({"cagr": 0.21, "max_dd": -0.30, "sharpe": 1.0}, btc, b3) == []
    fails = core_verdict({"cagr": 0.10, "max_dd": -0.50, "sharpe": 0.7}, btc, b3)
    assert len(fails) == 4
    assert core_verdict({"cagr": 0.21, "max_dd": -0.30, "sharpe": 0.85}, btc, b3) == [
        "Sharpe not above 50/50 never rebalanced"]
