"""Daily event-driven backtest. Decisions use data up to the previous close; orders fill at today's
open; exchange-side stops trigger intraday; equity is marked at the close."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from botcore.costs import trade_cost
from botcore.params import Params
from botcore.risk import BrakeState, atr, update_brakes
from botcore.strategy import compute_raw, weights_for_day
from research.universe import eligible_mask, gap_days, series_breaks


@dataclass
class Market:
    close: pd.DataFrame
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    returns: pd.DataFrame
    adv: pd.DataFrame
    eligible: pd.DataFrame
    atr: pd.DataFrame
    gaps: pd.DataFrame
    breaks: pd.DataFrame
    fng: pd.Series | None = None


def build_market(panel: dict, p: Params, fng: pd.Series | None = None) -> Market:
    close = panel["close"]
    return Market(
        close=close, open=panel["open"], high=panel["high"], low=panel["low"],
        returns=close / close.shift(1) - 1,
        adv=panel["quote_volume"].rolling(p.volume_window, min_periods=1).mean(),
        eligible=eligible_mask(panel, p),
        atr=atr(panel["high"], panel["low"], close, p.atr_window),
        gaps=gap_days(close),
        breaks=series_breaks(close, p),
        fng=None if fng is None else fng.reindex(close.index).ffill(),
    )


@dataclass
class Result:
    returns: pd.Series
    equity: pd.Series
    weights: pd.DataFrame
    trades: int
    costs: float
    stops: int


def run_backtest(m: Market, p: Params, start, end=None, initial: float = 10_000.0) -> Result:
    idx = m.close.index
    dates = m.close.loc[start:end].index
    first = idx.get_loc(dates[0])
    if first < p.cov_window:
        raise ValueError("start must leave at least cov_window days of history")
    syms = list(m.close.columns)
    pos = {s: j for j, s in enumerate(syms)}
    n = len(syms)
    O, L = m.open.values, m.low.values
    lastC = m.close.ffill().values
    A, ADV = m.atr.values, m.adv.values
    raw = compute_raw(m.close, p)
    G, B = m.gaps.values, m.breaks.values

    units = np.zeros(n)
    stop = np.full(n, np.nan)
    cooldown = np.zeros(n, dtype=int)
    cash = initial
    brakes = BrakeState(peak=initial)
    stopped_days = 0
    eq_hist = np.empty(len(dates))
    w_hist = np.zeros((len(dates), n))
    trades, costs, n_stops = 0, 0.0, 0

    for k in range(len(dates)):
        i = first + k

        # 1) series that ended (gap > max_gap_days, known only once it happens) or restarted
        #    (redenomination / reused ticker): sell at the last real close minus a haircut
        for j in np.flatnonzero(units > 0):
            if G[i, j] > p.max_gap_days or B[i, j]:
                cash += units[j] * lastC[i - 1, j] * (1 - p.delist_haircut)
                units[j], stop[j] = 0.0, np.nan

        # 2) rebalance at today's open with information up to yesterday's close
        px_open = np.where(np.isnan(O[i]), lastC[i - 1], O[i])
        equity_open = cash + float(np.nansum(units * px_open))
        current_w = np.where(units > 0, units * px_open / equity_open, 0.0) if equity_open > 0 else np.zeros(n)
        target = np.zeros(n)
        if brakes.mode != "stopped":
            tw = weights_for_day(raw.iloc[i - 1], m.eligible.iloc[i - 1], m.returns.iloc[i - p.cov_window: i], p)
            for s, w in tw.items():
                target[pos[s]] = w
            if p.greed_threshold is not None and m.fng is not None:
                g = m.fng.iloc[i - 1]
                if not np.isnan(g) and g >= p.greed_threshold:
                    target *= p.greed_scale
            if brakes.mode == "half":
                target *= 0.5
            target[cooldown > 0] = 0.0
            if brakes.mode == "paused":
                target = np.minimum(target, current_w)

        tradable = ~np.isnan(O[i])
        diff = (target - current_w) * equity_open
        act = tradable & ((np.abs(target - current_w) > p.band) | ((target == 0) & (units > 0)))

        for j in np.flatnonzero(act & (diff < 0)):  # sells first, to fund buys
            notional = units[j] * O[i, j] if target[j] == 0 else min(-diff[j], units[j] * O[i, j])
            c = trade_cost(notional, ADV[i - 1, j], p)
            units[j] -= notional / O[i, j]
            cash += notional - c
            costs += c
            trades += 1
            if units[j] <= 1e-12:
                units[j], stop[j] = 0.0, np.nan

        buys = np.flatnonzero(act & (diff > 0))
        need = sum(diff[j] + trade_cost(diff[j], ADV[i - 1, j], p) for j in buys)
        scale = min(1.0, 0.999 * cash / need) if need > 0 else 1.0
        for j in buys:
            notional = diff[j] * scale
            c = trade_cost(notional, ADV[i - 1, j], p)
            units[j] += notional / O[i, j]
            cash -= notional + c
            costs += c
            trades += 1
            if np.isnan(stop[j]) and not np.isnan(A[i - 1, j]):
                stop[j] = O[i, j] - p.atr_mult * A[i - 1, j]

        # 3) exchange-side stops trigger intraday (gap below the stop fills at the open)
        for j in np.flatnonzero((units > 0) & ~np.isnan(stop)):
            if not np.isnan(L[i, j]) and L[i, j] <= stop[j]:
                slipped = stop[j] - p.stop_fill * (stop[j] - L[i, j])
                px = min(O[i, j], slipped) if not np.isnan(O[i, j]) else slipped
                notional = units[j] * px
                c = trade_cost(notional, ADV[i - 1, j], p)
                cash += notional - c
                costs += c
                trades += 1
                n_stops += 1
                units[j], stop[j] = 0.0, np.nan
                cooldown[j] = p.stop_cooldown_days + 1

        # 4) mark to market at the close, trail stops, update brakes
        marks = np.nan_to_num(lastC[i])
        equity = cash + float(np.sum(units * marks))
        held = units > 0
        new_stop = lastC[i] - p.atr_mult * A[i]
        stop = np.where(held & ~np.isnan(new_stop), np.fmax(stop, new_stop), stop)
        cooldown = np.maximum(cooldown - 1, 0)
        brakes = update_brakes(brakes, equity, p)
        if brakes.mode == "stopped":
            stopped_days += 1
            if stopped_days > p.stop_resume_days:
                brakes, stopped_days = BrakeState(peak=equity), 0
        eq_hist[k] = equity
        if equity > 0:
            w_hist[k] = np.where(held, units * marks / equity, 0.0)

    equity_s = pd.Series(eq_hist, index=dates)
    rets = equity_s / equity_s.shift(1) - 1
    rets.iloc[0] = equity_s.iloc[0] / initial - 1
    return Result(rets, equity_s, pd.DataFrame(w_hist, index=dates, columns=syms), trades, costs, n_stops)


def benchmark_hold(close: pd.DataFrame, symbol: str, start, end=None) -> pd.Series:
    r = close[symbol] / close[symbol].shift(1) - 1
    return r.loc[start:end].fillna(0)


def benchmark_equal_weight(m: Market, start, end=None) -> pd.Series:
    """Equal weight across the universe chosen at the previous close; no costs (flatters the benchmark)."""
    members = m.eligible.shift(1, fill_value=False).astype(bool)
    return m.returns.where(members).mean(axis=1).loc[start:end].fillna(0)
