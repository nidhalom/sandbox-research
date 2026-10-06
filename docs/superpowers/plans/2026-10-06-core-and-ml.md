# BTC + Gold Core, Holding Rules and CPU ML Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the three pre-registered experiments (BTC+gold rebalancing, holding rules, CPU ML on BTC) and write their reports.

**Architecture:** A pure spot portfolio simulator in `botcore/portfolio.py` (deposits, rebalancing, sells at daily closes) is used by `research/run_core.py` (parts 1–2). `research/run_ml.py` (part 3) builds causal features, trains a walk-forward gradient-boosting model and backtests it. Both runners reuse `botcore.metrics`, `research.validation.bootstrap_ci` and the table/chart helpers in `research/run_phase1.py`.

**Tech Stack:** Python 3.12, pandas, NumPy, scikit-learn (new), Matplotlib, pytest. Run everything with `.venv/Scripts/python` from `D:\sandbox`.

**Spec:** `docs/specs/2026-10-06-core-and-ml-preregistration.md`

## Global Constraints

- Spot, long-only, no leverage, no futures, no shorting.
- Daily closes from `data/spot_1d/` (BTCUSDT, PAXGUSDT); trades fill at the day's close.
- Costs: 0.10% fee + 0.05% half-spread on every buy and sell (`COST = 0.0015`); market impact ignored.
- Cash earns 0%.
- Part 1 period 2020-09-01 → 2026-09-30; weights 50/50; band 40–60%; no other weights or bands.
- Owner's plan: $2,000 at month 0, +$500 at month 3, +$500 at month 6.
- ML: `HistGradientBoostingClassifier` defaults, `random_state=0`, target = close 7 days ahead > today, threshold 0.55, train from 2018-02-01, test 2020-01-01 → 2026-09-30, retrain each 1 January.
- Results reported as they come out, including if bad. Commits as the owner, no AI attribution; push `main` after each commit.

## Review Focus

1. PAXG has no prices before 2020-08-28 → mixed-asset price frames keep only days where every asset has a price (test in Task 2).
2. A deposit or sell date on a day missing from the data → use the next available day (test in Task 2).
3. A window whose horizon runs past the last data day → skipped, never crashes or truncates silently (test in Task 2).
4. H3 target hit before month 6 → half of what is held is sold; later deposits still go in; the +30% base is money deposited so far (test in Task 2).
5. Fear & Greed has missing days → forward-filled only, never filled from the future (test in Task 4).

---

### Task 1: Portfolio simulator

**Files:**
- Create: `botcore/portfolio.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Produces: `COST: float = 0.0015`; `simulate(prices: pd.DataFrame, deposits: dict[pd.Timestamp, float], weights: dict[str, float], rule: str = "none", band: float = 0.10, sells: dict[pd.Timestamp, float] | None = None, cost: float = COST) -> pd.DataFrame` with index `date` and columns `value` (holdings at close) and `cash_out` (cumulative sale proceeds after costs).

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify they fail** — `.venv/Scripts/python -m pytest tests/test_portfolio.py -q` → FAIL (`ModuleNotFoundError: botcore.portfolio`).

- [ ] **Step 3: Implement `botcore/portfolio.py`**

```python
"""Spot portfolio simulator: deposits, rebalancing and sells at daily closes."""
import pandas as pd

COST = 0.0015  # 0.10% fee + 0.05% half-spread per traded dollar


def _quarter_start(prev: pd.Timestamp, day: pd.Timestamp) -> bool:
    return day.month in (1, 4, 7, 10) and day.month != prev.month


def simulate(prices: pd.DataFrame, deposits: dict, weights: dict, rule: str = "none",
             band: float = 0.10, sells: dict | None = None, cost: float = COST) -> pd.DataFrame:
    """Daily holdings `value` and cumulative `cash_out` from sales, starting at the first deposit.

    deposits: {date: dollars} bought at that close in `weights`. sells: {date: fraction of current
    holdings} sold at that close. rule: 'none', 'quarterly' (first trading day of Jan/Apr/Jul/Oct)
    or 'band' (any weight more than `band` from target, checked at each close).
    """
    if rule not in ("none", "quarterly", "band"):
        raise ValueError(f"unknown rule {rule!r}")
    sells = sells or {}
    assets = list(weights)
    units = dict.fromkeys(assets, 0.0)
    cash_out, rows, prev = 0.0, [], None
    for day, p in prices.loc[min(deposits):, assets].iterrows():
        value = sum(units[a] * p[a] for a in assets)
        if prev is not None and value > 0 and rule != "none":
            w_now = {a: units[a] * p[a] / value for a in assets}
            due = (_quarter_start(prev, day) if rule == "quarterly"
                   else any(abs(w_now[a] - weights[a]) > band for a in assets))
            if due:
                value -= sum(abs(w_now[a] - weights[a]) for a in assets) * value * cost
                units = {a: value * weights[a] / p[a] for a in assets}
        if day in deposits:
            for a in assets:
                units[a] += deposits[day] * weights[a] * (1 - cost) / p[a]
        if day in sells:
            f = sells[day]
            cash_out += f * sum(units[a] * p[a] for a in assets) * (1 - cost)
            units = {a: u * (1 - f) for a, u in units.items()}
        rows.append((day, sum(units[a] * p[a] for a in assets), cash_out))
        prev = day
    return pd.DataFrame(rows, columns=["date", "value", "cash_out"]).set_index("date")
```

- [ ] **Step 4: Run to verify they pass** — `.venv/Scripts/python -m pytest tests/test_portfolio.py -q` → 6 passed; full suite `-q` → 72 passed.

- [ ] **Step 5: Commit** — `git add botcore/portfolio.py tests/test_portfolio.py && git commit -m "feat: spot portfolio simulator with rebalancing and sells" && git push origin main`

---

### Task 2: Core experiment building blocks

**Files:**
- Create: `research/run_core.py` (functions only in this task)
- Test: `tests/test_run_core.py`

**Interfaces:**
- Consumes: `simulate`, `COST` from Task 1.
- Produces (in `research/run_core.py`): `load_closes(data_dir, symbols) -> pd.DataFrame`; `months_later(index, start, months) -> pd.Timestamp | None`; `plan_deposits(index, start, schedule) -> dict`; exit rules `exit_fixed(h)`, `exit_staged(h)`, `exit_half_at_target(h=30, target=0.30)` each returning `rule(index, start, path, deposits) -> dict[Timestamp, float]`; `plan_gain(prices, weights, rule, start, schedule, exit_rule, horizon) -> float | None`; `independent_count(starts, months) -> int`; `describe(gains, starts, months) -> dict`; `full_period_returns(prices, weights, rule) -> pd.Series`; `core_verdict(s, btc, b3) -> list[str]`; constants `PLAN`, `STAGED_ENTRY`, `START`, `END`.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify they fail** — `.venv/Scripts/python -m pytest tests/test_run_core.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement the functions in `research/run_core.py`**

```python
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
```

- [ ] **Step 4: Run to verify they pass** — `.venv/Scripts/python -m pytest tests/test_run_core.py -q` → 8 passed; full suite → 80 passed.

- [ ] **Step 5: Commit** — `git add research/run_core.py tests/test_run_core.py && git commit -m "feat: building blocks for BTC+gold core and holding-rule study" && git push origin main`

---

### Task 3: Core runner, real run and report

**Files:**
- Modify: `research/run_core.py` (append `main`)
- Create (generated): `reports/core-report.md`, `reports/core-equity.png`

**Interfaces:**
- Consumes: everything from Task 2; `table`, `yearly_table`, `chart` from `research.run_phase1`.

- [ ] **Step 1: Append `main` to `research/run_core.py`**

```python
from research.run_phase1 import chart, table, yearly_table  # noqa: E402  (place with the other imports)

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
    print("\n".join(md))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run tests** — `.venv/Scripts/python -m pytest -q` → 80 passed.
- [ ] **Step 3: Real run** — `.venv/Scripts/python -m research.run_core` → writes `reports/core-report.md` and `reports/core-equity.png`. Sanity check: B1 full-period numbers match a direct `BTC close` calculation over the same period (CAGR within 0.5 pp).
- [ ] **Step 4: Commit** — `git add research/run_core.py reports/core-report.md reports/core-equity.png && git commit -m "BTC+gold core and holding-rule results" && git push origin main`

---

### Task 4: ML building blocks

**Files:**
- Modify: `requirements.txt` (add `scikit-learn>=1.5`)
- Create: `research/run_ml.py` (functions only)
- Test: `tests/test_ml.py`

**Interfaces:**
- Consumes: `COST` from `botcore.portfolio`.
- Produces: `HORIZON = 7`, `THRESHOLD = 0.55`, `TRAIN_START = "2018-02-01"`, `TEST_START = "2020-01-01"`; `make_features(close, fng) -> pd.DataFrame`; `make_target(close) -> pd.Series`; `train_end(cut: pd.Timestamp) -> pd.Timestamp`; `walk_forward_proba(feats, target) -> pd.Series`; `strategy_returns(close, proba, threshold=THRESHOLD, cost=COST) -> pd.Series`; `ml_verdict(r, btc_r, ci) -> list[str]`.

- [ ] **Step 1: Install dependency** — add `scikit-learn>=1.5` to `requirements.txt`; run `.venv/Scripts/python -m pip install "scikit-learn>=1.5"`.

- [ ] **Step 2: Write the failing tests**

```python
import numpy as np
import pandas as pd
import pytest

from research.run_ml import make_features, make_target, ml_verdict, strategy_returns, train_end


def series(n=200, seed=0):
    idx = pd.date_range("2019-01-01", periods=n, freq="D")
    close = pd.Series(100 * np.exp(np.random.default_rng(seed).normal(0, 0.02, n).cumsum()), index=idx)
    fng = pd.Series(np.arange(n, dtype=float), index=idx)
    return close, fng


def test_features_do_not_use_future_prices():
    close, fng = series()
    f1 = make_features(close, fng)
    close2 = close.copy()
    close2.iloc[150:] *= 3
    f2 = make_features(close2, fng)
    pd.testing.assert_frame_equal(f1.iloc[:150], f2.iloc[:150])


def test_missing_fear_greed_is_forward_filled_only():
    close, fng = series()
    gap = fng.drop(fng.index[100:103])
    f = make_features(close, gap)
    assert f["fng"].iloc[100:103].tolist() == [99.0, 99.0, 99.0]


def test_target_compares_close_seven_days_ahead():
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    close = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 0, 0], index=idx, dtype=float)
    t = make_target(close)
    assert t.iloc[0] == 1.0 and t.iloc[1] == 0.0 and t.iloc[3:].isna().all()


def test_training_stops_before_targets_are_known():
    assert train_end(pd.Timestamp("2021-01-01")) == pd.Timestamp("2020-12-24")


def test_strategy_returns_shift_positions_and_charge_switches():
    idx = pd.date_range("2024-01-01", periods=4, freq="D")
    close = pd.Series([100.0, 110.0, 121.0, 108.9], index=idx)
    proba = pd.Series([0.6, 0.6, 0.4, 0.4], index=idx)
    r = strategy_returns(close, proba, threshold=0.55, cost=0.01)
    assert r.tolist() == pytest.approx([-0.01, 0.10, 0.10 - 0.01, 0.0])


def test_ml_verdict():
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    good = {"sharpe": (0.6, 2.0)}
    r = pd.Series([0.01, 0.012, 0.011], index=idx)
    btc = pd.Series([0.01, -0.01, 0.01], index=idx)
    assert ml_verdict(r, btc, good) == []
    assert "Sharpe CI lower bound below 0.5" in ml_verdict(r, btc, {"sharpe": (0.1, 2.0)})
```

- [ ] **Step 3: Run to verify they fail** — `.venv/Scripts/python -m pytest tests/test_ml.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Implement `research/run_ml.py` functions**

```python
"""CPU machine-learning test on BTC (pre-registration 2026-10-06, part 3)."""
import argparse
from pathlib import Path

import pandas as pd

from botcore.metrics import summary
from botcore.portfolio import COST

HORIZON = 7
THRESHOLD = 0.55
TRAIN_START = "2018-02-01"
TEST_START = "2020-01-01"


def make_features(close: pd.Series, fng: pd.Series) -> pd.DataFrame:
    f = pd.DataFrame(index=close.index)
    for n in (1, 7, 30):
        f[f"ret_{n}"] = close.pct_change(n)
    f["vol_30"] = close.pct_change().rolling(30).std()
    for n in (20, 50, 100):
        f[f"sma_{n}"] = close / close.rolling(n).mean() - 1
    g = fng.reindex(close.index).ffill()
    f["fng"] = g
    f["fng_chg_7"] = g.diff(7)
    return f


def make_target(close: pd.Series) -> pd.Series:
    future = close.shift(-HORIZON)
    return (future > close).astype(float).where(future.notna())


def train_end(cut: pd.Timestamp) -> pd.Timestamp:
    """Last day whose 7-day target is known at the close before `cut`."""
    return cut - pd.Timedelta(days=HORIZON + 1)


def walk_forward_proba(feats: pd.DataFrame, target: pd.Series) -> pd.Series:
    from sklearn.ensemble import HistGradientBoostingClassifier

    out = []
    for year in range(pd.Timestamp(TEST_START).year, feats.index[-1].year + 1):
        cut = pd.Timestamp(f"{year}-01-01")
        train = feats.loc[TRAIN_START:train_end(cut)]
        y = target.loc[train.index]
        ok = y.notna()
        model = HistGradientBoostingClassifier(random_state=0).fit(train[ok], y[ok])
        test = feats.loc[cut:f"{year}-12-31"]
        if len(test):
            out.append(pd.Series(model.predict_proba(test)[:, 1], index=test.index))
    return pd.concat(out)


def strategy_returns(close, proba, threshold=THRESHOLD, cost=COST) -> pd.Series:
    pos = (proba > threshold).astype(float)              # decided at close t
    ret = close.pct_change().reindex(pos.index).fillna(0)
    switches = pos.diff().abs().fillna(pos.iloc[0])      # traded at close t
    return pos.shift(1).fillna(0) * ret - switches * cost


def ml_verdict(r, btc_r, ci) -> list[str]:
    s, fails = summary(r), []
    if s["sharpe"] < 1.0:
        fails.append("Sharpe below 1.0")
    if ci["sharpe"][0] < 0.5:
        fails.append("Sharpe CI lower bound below 0.5")
    if s["max_dd"] < -0.35:
        fails.append("max drawdown worse than -35%")
    if s["sharpe"] <= summary(btc_r)["sharpe"]:
        fails.append("Sharpe not above hold BTC")
    return fails
```

- [ ] **Step 5: Run to verify they pass** — `.venv/Scripts/python -m pytest tests/test_ml.py -q` → 6 passed; full suite → 86 passed.
- [ ] **Step 6: Commit** — `git add requirements.txt research/run_ml.py tests/test_ml.py && git commit -m "feat: causal features, walk-forward model and backtest for CPU ML test" && git push origin main`

---

### Task 5: ML real run, report, README and ledger

**Files:**
- Modify: `research/run_ml.py` (append `main`), `README.md`, `.ledger/progress.md`
- Create (generated): `reports/ml-report.md`, `reports/ml-equity.png`

- [ ] **Step 1: Append `main` to `research/run_ml.py`**

```python
from research.run_phase1 import chart, table, yearly_table  # noqa: E402  (place with the other imports)
from research.sentiment import load_fear_greed  # noqa: E402
from research.validation import bootstrap_ci  # noqa: E402


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/spot_1d")
    args = ap.parse_args(argv)
    close = pd.read_parquet(Path(args.data) / "BTCUSDT.parquet").set_index("date")["close"]
    close.index = pd.to_datetime(close.index)
    close = close.loc[:"2026-09-30"]
    fng = load_fear_greed("data/fear_greed.csv")
    proba = walk_forward_proba(make_features(close, fng), make_target(close))
    r = strategy_returns(close, proba)
    btc = close.pct_change().reindex(r.index).fillna(0)
    ci = bootstrap_ci(r)
    fails = ml_verdict(r, btc, ci)
    pos = (proba > THRESHOLD).astype(float)
    hit = ((proba > 0.5) == (make_target(close).reindex(proba.index) == 1.0))[make_target(close).reindex(proba.index).notna()]
    rows = {"ML model": summary(r), "Hold BTC": summary(btc)}
    chart({"ML model": r, "Hold BTC": btc}, Path("reports/ml-equity.png"))
    md = [
        "# CPU Machine-Learning Test on BTC — Results",
        "",
        "Pre-registration: `docs/specs/2026-10-06-core-and-ml-preregistration.md` (rules fixed before this run).",
        f"Test {r.index[0].date()} → {r.index[-1].date()}, walk-forward yearly retraining, costs 0.15% per switch.",
        "One fixed configuration, no tuning loop, so PBO is not computed.",
        "",
        "## Verdict",
        "",
        "**GO** (Testnet paper trading only)" if not fails else "**NO-GO**: " + "; ".join(fails),
        "",
        table(rows, {"cagr": "+.1%", "max_dd": ".1%", "sharpe": ".2f"}),
        "",
        f"Sharpe 90% bootstrap CI: {ci['sharpe'][0]:.2f} to {ci['sharpe'][1]:.2f}. "
        f"Time in market: {pos.mean():.0%}. Switches: {int(pos.diff().abs().sum())}. "
        f"Direction hit rate (P>0.5 vs actual 7-day move): {hit.mean():.1%}.",
        "",
        "![equity](ml-equity.png)",
        "",
        "## Yearly returns",
        "",
        yearly_table({"ML model": r, "Hold BTC": btc}),
    ]
    Path("reports/ml-report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run tests** — `.venv/Scripts/python -m pytest -q` → 86 passed.
- [ ] **Step 3: Real run** — `.venv/Scripts/python -m research.run_ml` → writes `reports/ml-report.md`, `reports/ml-equity.png`.
- [ ] **Step 4: Update README** — add a "Follow-up: BTC + gold core, holding rules and CPU ML (pre-registered)" section after the BTC+ETH section with each verdict and headline numbers copied from the two reports and links to them; update the test count in "Project layout" and "How to run" to the real count; add `python -m research.run_core` and `python -m research.run_ml` to "How to run"; add scikit-learn to "Tech".
- [ ] **Step 5: Update ledger** — append one line to `.ledger/progress.md`: date, verdicts, headline numbers, suite count.
- [ ] **Step 6: Commit** — `git add research/run_ml.py reports/ml-report.md reports/ml-equity.png README.md .ledger/progress.md && git commit -m "CPU ML test results; README and ledger updated" && git push origin main`
