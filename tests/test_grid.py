import numpy as np
import pandas as pd
import pytest

from botcore.grid import grid_levels, run_grid


def candles(rows):
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="h")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_levels_are_geometric_and_span_the_range():
    lv = grid_levels(100.0, 0.10, 2)
    assert lv[0] == pytest.approx(90.0) and lv[-1] == pytest.approx(110.0)
    assert lv[1] / lv[0] == pytest.approx(lv[2] / lv[1])


def test_flat_price_costs_only_the_launch_buy_for_cells_above_price():
    # n=4 around 100: levels 90, 94.6, 99.5, 104.6, 110 -> only the top cell starts in coin
    c = candles([[100, 100, 100, 100]] * 3)
    v = run_grid(c, 0.10, 4, fee=0.001, mkt_cost=0.0015, close_out=False)
    assert v.iloc[-1] == pytest.approx(0.75 + 0.25 * (1 - 0.0015))


def test_one_round_trip_earns_the_cell_spacing_minus_fees():
    lv = grid_levels(100.0, 0.10, 2)              # 90, 99.499, 110: both cells start in USDT
    c = candles([[100, 100, 95, 95], [95, 110, 95, 110]])
    v = run_grid(c, 0.10, 2, fee=0.001, mkt_cost=0.0, close_out=False)
    coin = 0.5 * 0.999 / lv[1]
    assert v.iloc[-1] == pytest.approx(0.5 + coin * lv[2] * 0.999)


def test_above_range_everything_is_cash_and_stays_flat():
    c = candles([[100, 100, 100, 100], [100, 130, 100, 130], [130, 200, 130, 200]])
    v = run_grid(c, 0.10, 4, fee=0.0, mkt_cost=0.0, close_out=False)
    assert v.iloc[1] == pytest.approx(v.iloc[2])


def test_below_range_everything_is_coin_and_tracks_price():
    c = candles([[100, 100, 100, 100], [100, 100, 80, 80], [80, 80, 40, 40]])
    v = run_grid(c, 0.10, 4, fee=0.0, mkt_cost=0.0, close_out=False)
    assert v.iloc[2] == pytest.approx(v.iloc[1] / 2)


def test_path_goes_to_the_nearer_extreme_first():
    # open 109 near high 110: up first (nothing to sell), then down to 90 buys every cell
    c = candles([[100, 100, 100, 100], [109, 110, 90, 90]])
    v = run_grid(c, 0.10, 2, fee=0.0, mkt_cost=0.0, close_out=False)
    assert v.iloc[-1] == pytest.approx(0.5 * 90 / grid_levels(100.0, 0.10, 2)[1] + 0.5)


def test_close_out_charges_market_cost_on_coin():
    c = candles([[100, 100, 80, 80]])
    a = run_grid(c, 0.10, 2, fee=0.0, mkt_cost=0.0, close_out=False).iloc[-1]
    b = run_grid(c, 0.10, 2, fee=0.0, mkt_cost=0.01, close_out=True).iloc[-1]
    assert b < a and np.isfinite(b)
