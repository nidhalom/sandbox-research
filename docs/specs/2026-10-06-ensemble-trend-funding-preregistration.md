# Pre-registration — Ensemble Trend Basket (#1) and Funding-Rate Overlay (#3)

**Written:** 2026-10-06, before any backtest below and before funding data was downloaded. Candidates come
from an independent literature search (Zarattini, Pagani & Barbon, SSRN 5209907; BIS WP 1087).

## ⚠️ Seen data

Phase 1 tested a different trend rule on a similar top-10 universe (NO-GO). The ensemble rules below are
copied from the literature, not tuned here. The **verdict uses only the hold-out 2022-01-01 → 2026-09-30**;
2018–2021 is reported as development, with the same fixed rules.

## #1 Ensemble trend basket (spot, long-only, ≤ 100% invested)

| Item | Rule |
|---|---|
| Universe | Binance USDT spot pairs incl. delisted (`data/spot_1d`), existing exclusions (stablecoins, leveraged tokens, min 10% vol), **≥ 365 days of history**, top **10** by 30-day average quote volume (`research.universe.eligible_mask`). Re-selected on the first day of each month and held for the month |
| Lookbacks | L ∈ {5, 10, 20, 30, 60, 90, 150, 250, 360} days, on daily closes |
| Entry (per coin, per L) | Close > highest close of the previous L days |
| Exit | Trailing stop = max(previous stop, midpoint of the highest and lowest close of the previous L days); exit when close < stop |
| Sizing | Each coin slice = 1/10 of equity. Target weight = slice × (active lookbacks / 9) × min(1, 0.25 / σ90), σ90 = annualized 90-day volatility |
| Execution | Signals at the daily close, trades at the **next day's open**. Signal changes always trade; pure volatility resizes only when the position is more than 20% away from target (relative) |
| Leaving the universe / delisting | A coin dropped at the monthly re-selection is sold at the next open. A coin whose data stops (gap > 3 days) is sold at its last close × 0.5 (haircut) |
| Costs | **0.20% per side (primary)**; 0.10% and 0.30% reported |

## #3 Funding-rate overlay (signal only; no futures position is ever taken)

- Data: Binance USDⓈ-M BTCUSDT funding rate history (data.binance.vision), from 2020-01.
- Signal: 7-day average funding rate, annualized (× 3 × 365). At each daily close: if it is **above
  30%/yr**, the overlay switches ON and stays ON until it falls **below 10%/yr**.
- When ON, total spot exposure is halved (half of every position is held as cash), traded at the next open.
- Applied to: (a) hold BTC, (b) the #1 basket. Evaluated on 2022-01-01 → 2026-09-30 (verdict) and
  2020-01 → 2021-12 (development).

## GO criteria (hold-out 2022-01-01 → 2026-09-30, primary costs)

**#1:** all of CAGR ≥ ⅔ of hold BTC (or ≥ 0 if hold BTC's CAGR is negative); max drawdown no worse than
−40%; Sharpe > hold BTC; Sharpe > an equal-weight basket of the same monthly top-10 universe, rebalanced
monthly, fully invested.

**#3:** for each base strategy, keep the overlay only if it improves **both** Sharpe and max drawdown
in the hold-out.

Benchmarks: hold BTC; equal-weight top-10 basket. Results reported as they come out. A GO justifies
Testnet paper trading only. Not financial advice.
