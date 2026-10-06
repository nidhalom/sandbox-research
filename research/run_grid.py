"""Spot grid bot study (pre-registration docs/specs/2026-10-06-grid-preregistration.md)."""
from pathlib import Path

import numpy as np
import pandas as pd

from botcore.grid import run_grid
from botcore.metrics import summary
from research.run_core import describe
from research.run_phase1 import table

START, END = "2021-01-01", "2026-09-30 23:00"
CONFIGS = {"Main ±15%, 50 cells": (0.15, 50), "Narrow ±7.5%, 25 cells": (0.075, 25), "Wide ±30%, 100 cells": (0.30, 100)}
MKT = 0.0015
FMT_ROLL = {"p10": "+.1%", "median": "+.1%", "p90": "+.1%", "worst": "+.1%", "lose": ".0%",
            "windows": "d", "independent": "d"}


def load_hourly(symbol: str) -> pd.DataFrame:
    return pd.read_parquet(f"data/spot_1h/{symbol}.parquet").set_index("date").loc[START:END]


def window_returns(c: pd.DataFrame, w: float, n: int, starts, hours: int):
    grid, hold = [], []
    for s in starts:
        win = c.loc[s:].iloc[:hours]
        grid.append(run_grid(win, w, n, mkt_cost=MKT).iloc[-1] - 1)
        hold.append(win["close"].iloc[-1] / win["open"].iloc[0] * (1 - MKT) ** 2 - 1)
    return np.array(grid), np.array(hold)


def monthly_grid_returns(c: pd.DataFrame, w: float, n: int) -> pd.Series:
    """Relaunch on the whole balance each month; daily returns from end-of-day marks."""
    marks, value = [], 1.0
    for _, month in c.groupby(c.index.to_period("M")):
        v = run_grid(month, w, n, capital=value, mkt_cost=MKT)
        marks.append(v)
        value = v.iloc[-1]
    daily = pd.concat(marks).resample("D").last().dropna()
    return pd.concat([pd.Series([1.0], index=[daily.index[0] - pd.Timedelta(days=1)]), daily]).pct_change().dropna()


def grid_verdict(s, btc, lose_share) -> list[str]:
    fails = []
    if s["sharpe"] <= btc["sharpe"]:
        fails.append("Sharpe not above hold BTC")
    if s["max_dd"] < -0.40:
        fails.append("max drawdown worse than -40%")
    if s["cagr"] < 2 / 3 * btc["cagr"]:
        fails.append("CAGR below 2/3 of hold BTC")
    if lose_share >= 0.25:
        fails.append("25% or more of 30-day grids lose money")
    return fails


def main() -> None:
    md = ["# Spot Grid Bot — Results", "",
          "Pre-registration: `docs/specs/2026-10-06-grid-preregistration.md` (rules fixed before this run).",
          "Hourly Binance candles 2021-01-01 → 2026-09-30. 0.10% fee per grid fill; 0.15% on market launch "
          "buys and close-outs. Touch-fills are optimistic. Not financial advice.", ""]
    verdict_lines, roll, full, shot = [], {}, {}, {}
    for sym in ("BTCUSDT", "ETHUSDT"):
        c = load_hourly(sym)
        mondays = [t for t in c.index[(c.index.weekday == 0) & (c.index.hour == 0)] if t + pd.Timedelta(days=30) <= c.index[-1]]
        days = [t for t in c.index[c.index.hour == 0] if t + pd.Timedelta(days=5) <= c.index[-1]]
        hold_daily = c["close"].resample("D").last().pct_change().dropna()
        full[f"{sym} hold"] = summary(hold_daily)
        for name, (w, n) in CONFIGS.items():
            g, h = window_returns(c, w, n, mondays, 30 * 24)
            d = describe(g, mondays, 1)
            d["independent"] = len(mondays) // 4 + 1
            roll[f"{sym} grid {name}"] = d
            roll[f"{sym} hold, same windows"] = describe(h, mondays, 1) | {"independent": d["independent"]}
            roll[f"{sym} grid {name}"]["beats_hold"] = (g > h).mean()
            r = monthly_grid_returns(c, w, n)
            full[f"{sym} monthly grid {name}"] = summary(r)
            g5, _ = window_returns(c, w, n, days, 5 * 24)
            shot[f"{sym} {name}"] = {"share_ge_14pct": (g5 >= 0.14).mean(), "best_5d": g5.max(), "median_5d": np.median(g5), "launches": len(g5)}
            if sym == "BTCUSDT" and name.startswith("Main"):
                fails = grid_verdict(full[f"{sym} monthly grid {name}"], full[f"{sym} hold"], (g < 0).mean())
                verdict_lines.append("**GO** (Testnet paper trading only)" if not fails else "**NO-GO**: " + "; ".join(fails))
        print("done", sym)
    beats = {k: v.pop("beats_hold") for k, v in roll.items() if "beats_hold" in v}
    md += ["## Verdict (main grid on BTC)", "", *verdict_lines, "",
           "## Test 1 — 30-day grids launched every Monday", "",
           "`independent` = non-overlapping 30-day windows (about one per 4 launches).", "",
           table(roll, FMT_ROLL), "",
           "Share of 30-day windows where the grid beat holding the coin: "
           + "; ".join(f"{k.replace(' grid ', ': ')} {v:.0%}" for k, v in beats.items()), "",
           "## Test 2 — Grid relaunched every month on the whole balance", "",
           table(full, {"cagr": "+.1%", "max_dd": ".1%", "sharpe": ".2f"}), "",
           "## Test 3 — Screenshot check: grids launched every day, result after 5 days", "",
           table(shot, {"share_ge_14pct": ".1%", "median_5d": "+.2%", "best_5d": "+.1%", "launches": "d"}), ""]
    Path("reports/grid-report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote reports/grid-report.md")


if __name__ == "__main__":
    main()
