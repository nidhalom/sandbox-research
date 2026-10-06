"""BTC + gold core experiment and holding rules (pre-registration 2026-10-06, parts 1 and 2)."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from botcore.metrics import summary
from botcore.portfolio import COST, simulate
from research.run_phase1 import chart, table, yearly_table

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

STRATS = {
    "A1 50/50 quarterly": ({"BTC": 0.5, "PAXG": 0.5}, "quarterly"),
    "A2 50/50 band 40-60%": ({"BTC": 0.5, "PAXG": 0.5}, "band"),
    "B1 Hold BTC": ({"BTC": 1.0}, "none"),
    "B2 Hold PAXG": ({"PAXG": 1.0}, "none"),
    "B3 50/50 never rebalanced": ({"BTC": 0.5, "PAXG": 0.5}, "none"),
}
FMT_FULL = {"cagr": "+.1%", "max_dd": ".1%", "sharpe": ".2f"}
FMT_ROLL = {"p10": "+.0%", "median": "+.0%", "p90": "+.0%", "worst": "+.0%", "lose": ".0%",
            "windows": "d", "independent": "d"}


def weekly_starts(index, first, horizon):
    return [s for s in pd.date_range(first, index[-1], freq="W-MON")
            if months_later(index, s, horizon) is not None]


def rolling(prices, weights, rule, starts, schedule, exit_rule, horizon):
    gains = [plan_gain(prices, weights, rule, s, schedule, exit_rule, horizon) for s in starts]
    return describe(gains, starts, horizon)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/spot_1d")
    args = ap.parse_args(argv)
    both = load_closes(args.data, ["BTC", "PAXG"]).loc[START:]
    btc_long = load_closes(args.data, ["BTC"])

    rets = {n: full_period_returns(both[list(w)], w, r) for n, (w, r) in STRATS.items()}
    full = {n: summary(r) for n, r in rets.items()}
    btc, b3 = full["B1 Hold BTC"], full["B3 50/50 never rebalanced"]
    verdicts = {n: core_verdict(full[n], btc, b3) for n in ("A1 50/50 quarterly", "A2 50/50 band 40-60%")}

    def verdict_text(fails):
        if not fails:
            return "**GO** (Testnet paper trading only)"
        if fails == ["Sharpe not above 50/50 never rebalanced"]:
            return "**NO-GO**: rebalancing adds nothing; prefer B3"
        return "**NO-GO**: " + "; ".join(fails)

    passing = [n for n, f in verdicts.items() if not f]
    winner = max(passing, key=lambda n: full[n]["sharpe"]) if passing else "B3 50/50 never rebalanced"

    starts30 = weekly_starts(both.index, START, 30)
    roll1 = {}
    for n, (w, r) in STRATS.items():
        for h in (12, 24, 30):
            roll1[f"{n}, {h}m"] = rolling(both[list(w)], w, r, starts30, PLAN, exit_fixed(h), h)

    roll2 = {}
    for n in (winner, "B1 Hold BTC"):
        w, r = STRATS[n]
        px = both[list(w)]
        roll2[f"{n}: H1 sell at 30m"] = roll1[f"{n}, 30m"]
        for h in (24, 30):
            roll2[f"{n}: H2 staged exit, {h}m"] = rolling(px, w, r, starts30, PLAN, exit_staged(h), h)
        roll2[f"{n}: H3 half at +30%, rest 30m"] = rolling(px, w, r, starts30, PLAN, exit_half_at_target(30, 0.30), 30)
        roll2[f"{n}: H4 staged entry, 30m"] = rolling(px, w, r, starts30, STAGED_ENTRY, exit_fixed(30), 30)
        s48 = weekly_starts(px.index, START, 48)
        if s48:
            roll2[f"{n}: H1 sell at 48m (2020+ starts)"] = rolling(px, w, r, s48, PLAN, exit_fixed(48), 48)
    s48b = weekly_starts(btc_long.index, "2017-09-01", 48)
    roll2["B1 Hold BTC: H1 sell at 48m (2017+ starts)"] = rolling(btc_long, {"BTC": 1.0}, "none", s48b, PLAN, exit_fixed(48), 48)
    roll2["B1 Hold BTC: H1 sell at 30m (2017+ starts)"] = rolling(
        btc_long, {"BTC": 1.0}, "none", weekly_starts(btc_long.index, "2017-09-01", 30), PLAN, exit_fixed(30), 30)

    chart(rets, Path("reports/core-equity.png"))
    md = [
        "# BTC + Gold Core and Holding Rules — Results",
        "",
        "Pre-registration: `docs/specs/2026-10-06-core-and-ml-preregistration.md` (rules fixed before this run).",
        f"Period {both.index[0].date()} → {both.index[-1].date()}. Costs 0.15% per traded dollar. Cash earns 0%.",
        "**Not a clean out-of-sample test** (data seen before; gold rose about +110%). Not financial advice.",
        "",
        "## Part 1 — Verdicts",
        "",
        *[f"- {n}: {verdict_text(f)}" for n, f in verdicts.items()],
        "",
        "## Full period (single deposit)",
        "",
        table(full, FMT_FULL),
        "",
        "Reference, BTC+ETH trend bot (2021-01 → 2026-09, `reports/btc-eth-report.md`): +2.9%/yr, max DD −25%, Sharpe 0.28.",
        "",
        "![equity](core-equity.png)",
        "",
        "## Yearly returns",
        "",
        yearly_table(rets),
        "",
        "## Owner's $3,000 plan — sell at a fixed month (same start dates for all horizons)",
        "",
        "Weekly start dates heavily overlap; `independent` = non-overlapping windows.",
        "",
        table(roll1, FMT_ROLL),
        "",
        f"## Part 2 — Holding rules (informational), on {winner} and hold BTC",
        "",
        table(roll2, FMT_ROLL),
        "",
        "48-month rows rest on very few independent windows and cannot support a conclusion on their own.",
    ]
    Path("reports/core-report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote reports/core-report.md")


if __name__ == "__main__":
    main()
