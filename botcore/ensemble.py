"""Ensemble trend signals (Donchian breakout + trailing midpoint stop) and a next-open multi-coin book."""
import numpy as np
import pandas as pd

LOOKBACKS = (5, 10, 20, 30, 60, 90, 150, 250, 360)


def donchian_active(close: pd.Series, L: int) -> pd.Series:
    """1 while in a long position: enter when close > highest of the previous L closes; trailing stop =
    max(previous stop, midpoint of the previous L closes' high and low); exit when close < stop."""
    x = close.to_numpy(float)
    hi = close.rolling(L, min_periods=L).max().shift(1).to_numpy()
    lo = close.rolling(L, min_periods=L).min().shift(1).to_numpy()
    out = np.zeros(len(x))
    active, stop = False, -np.inf
    for t in range(len(x)):
        if np.isnan(x[t]) or np.isnan(hi[t]):
            active, stop = False, -np.inf
            continue
        mid = (hi[t] + lo[t]) / 2
        if active:
            stop = max(stop, mid)
            if x[t] < stop:
                active = False
        elif x[t] > hi[t]:
            active, stop = True, mid
        out[t] = 1.0 if active else 0.0
    return pd.Series(out, index=close.index)


def ensemble_fraction(close: pd.Series, lookbacks=LOOKBACKS) -> pd.Series:
    return sum(donchian_active(close, L) for L in lookbacks) / len(lookbacks)


def hysteresis(x: pd.Series, on: float, off: float) -> pd.Series:
    """1 from the first value above `on` until the first value below `off`."""
    out, state = [], 0
    for v in x.to_numpy(float):
        if not np.isnan(v):
            state = 1 if v > on else (0 if v < off else state)
        out.append(state)
    return pd.Series(out, index=x.index, dtype=float)


def run_book(open_: pd.DataFrame, close: pd.DataFrame, targets: pd.DataFrame, force: pd.DataFrame,
             band: float = 0.2, cost: float = 0.002, haircut: float = 0.5, max_gap: int = 3,
             break_ratio: float = 20.0) -> pd.Series:
    """Equity at each close. Targets/force decided at close t are traded at the open of t+1.

    A coin trades when forced, when its target is 0 while held, or when its weight is more than `band`
    (relative) from target. `cost` is charged per traded dollar. A held coin with no close for more
    than `max_gap` days, or a one-day jump beyond `break_ratio`, is sold at its last close × `haircut`.
    """
    cols = list(close.columns)
    o, c = open_[cols].to_numpy(float), close[cols].to_numpy(float)
    tw, fz = targets[cols].fillna(0).to_numpy(float), force[cols].fillna(False).to_numpy(bool)
    n, k = c.shape
    units, last, gap = np.zeros(k), np.full(k, np.nan), np.zeros(k)
    cash, eq = 1.0, np.empty(n)
    for i in range(n):
        if i > 0:
            px_open = np.where(np.isnan(o[i]), last, o[i])
            value = cash + np.nansum(units * px_open)
            for j in np.argsort(tw[i - 1] - np.nan_to_num(units * px_open / value)):  # sells first
                if np.isnan(o[i, j]):
                    continue
                w_now, tgt = units[j] * o[i, j] / value, tw[i - 1, j]
                if not (fz[i - 1, j] or (tgt == 0 and units[j] > 0) or (tgt > 0 and abs(w_now - tgt) > band * tgt)):
                    continue
                delta = tgt * value - units[j] * o[i, j]
                if delta > 0:
                    bought = delta / (1 + cost)
                    units[j] += bought / o[i, j]
                    cash -= delta
                elif delta < 0:
                    units[j] += delta / o[i, j]
                    cash += -delta * (1 - cost)
        for j in range(k):
            if np.isnan(c[i, j]):
                gap[j] += 1
                if units[j] > 0 and gap[j] > max_gap:
                    cash += units[j] * last[j] * haircut
                    units[j] = 0.0
                continue
            if units[j] > 0 and not np.isnan(last[j]) and not (1 / break_ratio < c[i, j] / last[j] < break_ratio):
                cash += units[j] * last[j] * haircut
                units[j] = 0.0
            gap[j], last[j] = 0, c[i, j]
        eq[i] = cash + np.nansum(units * last)
    return pd.Series(eq, index=close.index)
