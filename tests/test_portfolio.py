import pandas as pd
import pytest

from botcore.portfolio import simulate


def frame(**cols):
    idx = pd.date_range("2024-03-28", periods=len(next(iter(cols.values()))), freq="D")
    return pd.DataFrame(cols, index=idx)


def test_hold_single_asset_without_costs():
    px = frame(A=[10.0, 15.0, 20.0])
    out = simulate(px, {px.index[0]: 100.0}, {"A": 1.0}, cost=0.0)
    assert out["value"].tolist() == [100.0, 150.0, 200.0]


def test_deposit_pays_cost_and_later_deposit_is_added():
    px = frame(A=[10.0, 10.0, 10.0])
    out = simulate(px, {px.index[0]: 100.0, px.index[2]: 50.0}, {"A": 1.0}, cost=0.01)
    assert out["value"].iloc[0] == pytest.approx(99.0)
    assert out["value"].iloc[2] == pytest.approx(99.0 + 49.5)


def test_quarterly_rebalances_only_on_first_trading_day_of_quarter():
    # 2024-03-28..2024-04-02; A doubles on 03-29, rebalance due on 04-01
    px = frame(A=[1.0, 2.0, 2.0, 2.0, 2.0, 2.0], B=[1.0] * 6)
    out = simulate(px, {px.index[0]: 100.0}, {"A": 0.5, "B": 0.5}, rule="quarterly", cost=0.0)
    px2 = px.copy()
    px2.loc["2024-04-02", "A"] = 4.0
    out2 = simulate(px2, {px.index[0]: 100.0}, {"A": 0.5, "B": 0.5}, rule="quarterly", cost=0.0)
    # after 04-01 rebalance: 150 total, 75 in A -> A doubling adds 75
    assert out2.loc["2024-04-02", "value"] == pytest.approx(225.0)
    # without the rebalance (none rule) A doubling would add 100
    out3 = simulate(px2, {px.index[0]: 100.0}, {"A": 0.5, "B": 0.5}, cost=0.0)
    assert out3.loc["2024-04-02", "value"] == pytest.approx(250.0)
    assert out["value"].iloc[-1] == pytest.approx(150.0)


def test_band_rebalances_when_weight_leaves_band_and_pays_cost():
    px = frame(A=[1.0, 1.1, 2.0], B=[1.0, 1.0, 1.0])
    out = simulate(px, {px.index[0]: 100.0}, {"A": 0.5, "B": 0.5}, rule="band", cost=0.01)
    v0 = 100.0 * 0.99                       # after deposit cost
    v1 = v0 / 2 * 1.1 + v0 / 2              # A weight 0.524: inside band, no trade
    assert out["value"].iloc[1] == pytest.approx(v1)
    pre = v0 / 2 * 2.0 + v0 / 2             # A weight 0.667: rebalance
    traded = 2 * abs(v0 / 2 * 2.0 / pre - 0.5) * pre
    assert out["value"].iloc[2] == pytest.approx(pre - traded * 0.01)


def test_sells_accumulate_cash_out_after_cost():
    px = frame(A=[10.0, 20.0, 40.0])
    out = simulate(px, {px.index[0]: 100.0}, {"A": 1.0}, sells={px.index[1]: 0.5, px.index[2]: 1.0}, cost=0.0)
    assert out["cash_out"].tolist() == [0.0, 100.0, 300.0]
    assert out["value"].iloc[-1] == 0.0


def test_unknown_rule_raises():
    px = frame(A=[1.0])
    with pytest.raises(ValueError):
        simulate(px, {px.index[0]: 1.0}, {"A": 1.0}, rule="monthly")
