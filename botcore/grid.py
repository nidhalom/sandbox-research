"""Spot grid bot simulator on OHLC candles (neutral grid, geometric cells, no trailing, no stop)."""
import numpy as np
import pandas as pd


def grid_levels(p0: float, w: float, n: int) -> np.ndarray:
    lo, hi = p0 * (1 - w), p0 * (1 + w)
    lv = lo * (hi / lo) ** (np.arange(n + 1) / n)
    lv[0], lv[-1] = lo, hi
    return lv


EPS = 1e-12  # relative tolerance so a touch exactly at a level counts


def _path(o, h, l, c):
    first, second = (h, l) if abs(h - o) <= abs(o - l) else (l, h)
    return (o, first, second, c)


def run_grid(candles: pd.DataFrame, w: float, n: int, capital: float = 1.0, fee: float = 0.001,
             mkt_cost: float = 0.0015, close_out: bool = True) -> pd.Series:
    """Marked-to-market value after each candle; the last value includes the market close-out cost.

    Each of the n cells buys at its lower level and sells at its upper level (limit fills at the level,
    `fee` per fill). At launch, cells entirely above the first open hold coin bought at market.
    """
    o, h, l, c = (candles[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    lv = grid_levels(o[0], w, n)
    lower, upper = lv[:-1], lv[1:]
    per = capital / n
    above = lower >= o[0] * (1 - 1e-9)
    coin = np.where(above, per * (1 - mkt_cost) / o[0], 0.0)
    cash = np.where(above, 0.0, per)
    values = np.empty(len(c))
    for t in range(len(c)):
        pts = _path(o[t], h[t], l[t], c[t])
        for a, b in zip(pts[:-1], pts[1:]):
            if b < a:
                buy = (cash > 0) & (lower >= b * (1 - EPS)) & (lower < a)
                coin[buy] = cash[buy] * (1 - fee) / lower[buy]
                cash[buy] = 0.0
            elif b > a:
                sell = (coin > 0) & (upper > a) & (upper <= b * (1 + EPS))
                cash[sell] = coin[sell] * upper[sell] * (1 - fee)
                coin[sell] = 0.0
        values[t] = cash.sum() + coin.sum() * c[t]
    if close_out:
        values[-1] = cash.sum() + coin.sum() * c[-1] * (1 - mkt_cost)
    return pd.Series(values, index=candles.index)
