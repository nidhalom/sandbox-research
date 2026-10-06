# Pre-registration — BTC + Gold Core, Holding Rules, and a CPU ML Test

**Written:** 2026-10-06, before any of the backtests below were run.
**Engine:** the research engine in `D:\sandbox` (costs and metrics from `botcore/`).

## Why

Two trend-following experiments were NO-GO (top-10: +1.8%/yr; BTC+ETH: +2.9%/yr vs +20.3%/yr hold BTC).
The owner's real plan is to invest $3,000 ($2,000, then +$500 at month 3 and +$500 at month 6) and hold
for 1–2.5 years. An exploratory rolling-window study, audited independently by Fable and Opus
(2026-10-06), found that holding beat every bot over multi-year spans and that a 50/50 BTC + gold mix
roughly halved the worst case. This pre-registration fixes the rules for testing that idea properly,
plus a small, free machine-learning test.

## ⚠️ Data already seen

- 2020–2026 BTC, ETH and PAXG prices were examined in phase 1, the BTC+ETH experiment and the
  exploratory study, including **50/50 BTC+PAXG buy-and-hold**. Part 1 is **not a clean out-of-sample
  test**.
- Gold rose about +110% over the sample (PAXG Sep 2020 → Sep 2026), which flatters any gold mix.
- The sample covers only about 2–3 crypto cycles; overlapping rolling windows are not independent.
- **A GO only justifies paper trading on Testnet, never real money on its own.** Nothing here is
  financial advice.

## Shared rules

| Item | Value |
|---|---|
| Market | Binance spot, long-only, no leverage, no futures, no shorting |
| Prices | Daily closes from `data/spot_1d/` (BTCUSDT, PAXGUSDT); trades fill at the day's close |
| Costs | 0.10% fee + 0.05% half-spread on every buy and sell (market impact ignored: amounts are small) |
| Cash | Earns 0% |
| PAXG | Proxy for gold: 1 token = 1 troy oz held by Paxos. Issuer, custody and liquidity risk apply. Its Shariah status is the owner's decision; this study takes no position |

## Part 1 — BTC + Gold core (primary)

**Period:** 2020-09-01 → 2026-09-30 (limited by PAXG history).

| ID | Strategy | Rule |
|---|---|---|
| A1 | 50/50 quarterly | Start 50/50; on the first trading day of Jan/Apr/Jul/Oct, trade back to 50/50 |
| A2 | 50/50 band | Start 50/50; trade back to 50/50 whenever either weight leaves 40–60% (checked daily at close) |
| B1 | Hold BTC | Benchmark |
| B2 | Hold PAXG | Benchmark |
| B3 | 50/50 never rebalanced | Benchmark |
| B4 | BTC+ETH trend bot | Reference figures from `reports/btc-eth-report.md` (not re-run) |

Weights and the 40–60% band are fixed now; no other weights or bands are tried.

**Reported:**
1. Full period: CAGR, max drawdown, Sharpe, yearly returns.
2. Owner's $3,000 plan, rolling weekly (Monday) starts, holds of 12, 24 and 30 months — **all horizons on
   the same start dates** (those that allow 30 months) — showing p10 / median / p90, worst, % losing,
   and the number of **non-overlapping** windows.

**GO criteria (all must hold, on full-period daily returns, per strategy A1 / A2):**
1. CAGR ≥ ⅔ of hold BTC's CAGR over the same period.
2. Max drawdown no worse than −40%.
3. Sharpe > hold BTC's Sharpe.
4. Sharpe > 50/50 never rebalanced (B3). If A1/A2 fail only this, the verdict is "rebalancing adds
   nothing; prefer B3".

## Part 2 — Holding rules (informational, no GO verdict)

The owner asked whether a better rule exists than "hold 1–2.5 years, then sell". Compared on the
winner of Part 1 (or B3 if neither passes) and on hold BTC, same deposits and costs:

| ID | Rule |
|---|---|
| H1 | Fixed horizon: sell everything at 12 / 24 / 30 / 48 months |
| H2 | Staged exit: sell ⅓ at each of months H−2, H−1 and H (H = 24 or 30) |
| H3 | Sell half the first day value ≥ +30% over money deposited (checked from day 1 after the first deposit), rest at month 30 |
| H4 | Staged entry: $3,000 in 6 equal monthly deposits instead of 2,000/500/500, sold at month 30 |

48-month windows use 2017+ data for hold BTC; for BTC+gold only 2020-09 → 2022-09 starts exist, which is
reported as too few to conclude. Results are reported with the same statistics as Part 1, item 2.
Only these levels are tested (+30%, ⅓ steps, 6 months).

## Part 3 — Machine learning on CPU ($0)

| Item | Value |
|---|---|
| Asset | BTCUSDT, long-only spot, all-in or all-cash |
| Model | Gradient boosting classifier (scikit-learn `HistGradientBoostingClassifier`, default settings, `random_state=0`) |
| Target | Is the close 7 days ahead higher than today's close? |
| Features (known at today's close) | Returns over 1, 7, 30 days; 30-day volatility; close / SMA(20, 50, 100) − 1; Fear & Greed index (today and 7-day change) |
| Training | Expanding window from 2018-02-01 (Fear & Greed start); retrained each 1 January on data up to that day, dropping the last 7 days whose target is not yet known |
| Test period | 2020-01-01 → 2026-09-30 (out-of-sample year by year; the first model has ~23 months of training) |
| Trading rule | Hold BTC the next day if predicted P(up) > 0.55, else cash; costs on every switch |

One fixed configuration; no tuning loop, so PBO is not computed (stated in the report).

**GO criteria (phase 1 criteria minus PBO):** Sharpe ≥ 1.0; lower bound of the 90% bootstrap CI of
Sharpe ≥ 0.5; max drawdown no worse than −35%; Sharpe > hold BTC over the same test period.

## Reporting

Results are reported as they come out, including if they are bad, in `reports/core-report.md` and
`reports/ml-report.md`. New code: a pure rebalancing function in `botcore/` with tests,
`research/run_core.py` and `research/run_ml.py`. Adds dependency `scikit-learn`.
