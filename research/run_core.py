"""BTC + gold core experiment and holding rules (pre-registration 2026-10-06, parts 1 and 2)."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from botcore.metrics import summary
from botcore.portfolio import COST, simulate

PLAN = [(0, 2000.0), (3, 500.0), (6, 500.0)]
STAGED_ENTRY = [(m, 500.0) for m in range(6)]
START, END = "2020-09-01", "2026-09-30"


def load_closes(data_dir, symbols) -> pd.DataFrame:
    df = pd.DataFrame({s: pd.read_parquet(Path(data_dir) / f"{s}USDT.parquet").set_index("date")["close"]
                       for s in symbols})
    df.index = pd.to_datetime(df.index)
    return df.dropna().loc[:END]


def months_later(index, start, months):
    i = index.searchsorted(start + pd.DateOffset(months=months))
    return index[i] if i < len(index) else None


def plan_deposits(index, start, schedule) -> dict:
    return {months_later(index, start, m): amount for m, amount in schedule}


def exit_fixed(h):
    def rule(index, start, path, deposits):
        return {months_later(index, start, h): 1.0}
    return rule


def exit_staged(h):
    def rule(index, start, path, deposits):
        d = [months_later(index, start, m) for m in (h - 2, h - 1, h)]
        return {d[0]: 1 / 3, d[1]: 1 / 2, d[2]: 1.0}
    return rule


def exit_half_at_target(h=30, target=0.30):
    def rule(index, start, path, deposits):
        end = months_later(index, start, h)
        deposited = pd.Series(deposits).reindex(path.index, fill_value=0.0).cumsum()
        window = path.loc[path.index[1]:end]
        hit = window.index[window["value"] >= (1 + target) * deposited.loc[window.index]]
        sells = {end: 1.0}
        if len(hit) and hit[0] < end:
            sells[hit[0]] = 0.5
        return sells
    return rule


def plan_gain(prices, weights, rule, start, schedule, exit_rule, horizon):
    end = months_later(prices.index, start, horizon)
    if end is None:
        return None
    px = prices.loc[:end]
    deposits = plan_deposits(px.index, start, schedule)
    path = simulate(px, deposits, weights, rule)
    out = simulate(px, deposits, weights, rule, sells=exit_rule(px.index, start, path, deposits))
    return float(out["cash_out"].iloc[-1] / sum(deposits.values()) - 1)


def independent_count(starts, months) -> int:
    n, nxt = 0, None
    for s in starts:
        if nxt is None or s >= nxt:
            n, nxt = n + 1, s + pd.DateOffset(months=months)
    return n


def describe(gains, starts, months) -> dict:
    g = np.asarray(gains)
    return {"p10": np.percentile(g, 10), "median": np.median(g), "p90": np.percentile(g, 90),
            "worst": g.min(), "lose": (g < 0).mean(), "windows": len(g),
            "independent": independent_count(starts, months)}


def full_period_returns(prices, weights, rule) -> pd.Series:
    v = simulate(prices, {prices.index[0]: 1.0}, weights, rule)["value"]
    return v.pct_change().dropna()


def core_verdict(s, btc, b3) -> list[str]:
    fails = []
    if s["cagr"] < 2 / 3 * btc["cagr"]:
        fails.append("CAGR below 2/3 of hold BTC")
    if s["max_dd"] < -0.40:
        fails.append("max drawdown worse than -40%")
    if s["sharpe"] <= btc["sharpe"]:
        fails.append("Sharpe not above hold BTC")
    if s["sharpe"] <= b3["sharpe"]:
        fails.append("Sharpe not above 50/50 never rebalanced")
    return fails
