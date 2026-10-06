# Pre-registration — Ideas 1–5 (gold history, contributions, volatility scaling, AI volatility, crash brake) and Testnet rebalancer

**Written:** 2026-10-06, before any backtest below was run. Builds on
`2026-10-06-core-and-ml-preregistration.md` (50/50 BTC+PAXG quarterly: NO-GO on drawdown only).

## ⚠️ Data already seen / snooping

- BTC prices 2017–2026 and BTC+PAXG 2020–2026 have been examined; weight sensitivities (30/70 … 70/30)
  on 2020–2026 were looked at during the audit (30/70 would have passed). That is why Idea 1's verdict
  uses only **2017-08-17 → 2020-08-31**, where the BTC+gold mix has never been examined.
- Ideas 4, 4b and 5 are new rules on partly seen data. A GO justifies Testnet paper trading only.
- Three weight mixes are tested in Idea 1; all three are reported, and a pass by one mix out of three
  is labelled as such (multiple-testing risk).

## Data

| Series | Source |
|---|---|
| BTC | Binance BTCUSDT daily close (`data/spot_1d/`) |
| Gold, before 2020-09-01 | COMEX gold front-month futures close (Yahoo `GC=F`, `data/gold_gc_yahoo.json`), forward-filled on weekends/holidays |
| Gold, from 2020-09-01 | Binance PAXGUSDT daily close |

The two gold series are chained by daily returns at 2020-09-01. Proxy check done before writing this
(no strategy results seen): weekly-return correlation GC vs PAXG 0.90, total return 2020-09 → 2026-09
+111.6% vs +110.3%. Futures rolls and a few hours' close-time mismatch are accepted limitations.

Shared rules as before: spot, long-only, no leverage; 0.15% cost per traded dollar; fills at the
daily close; cash earns 0%.

## Idea 1 — BTC + gold, fixed weights, quarterly rebalancing, on unseen gold history

- Mixes (BTC/gold): **30/70, 40/60, 50/50**, rebalanced on the first trading day of each quarter.
- **Verdict period: 2017-08-17 → 2020-08-31** (includes the 2018 BTC crash). Full 2017–2026 also reported.
- GO criteria per mix (as in the previous pre-registration): CAGR ≥ ⅔ of hold BTC; max drawdown no
  worse than −40%; Sharpe > hold BTC; Sharpe > the same mix never rebalanced.

## Idea 3 — Monthly contributions (informational)

Owner's plan ($2,000, +$500 at month 3, +$500 at month 6) **plus $100 at every later month start**,
sold at month 30, versus the plan alone. Strategies: hold BTC and 50/50 quarterly. Weekly start dates
2017-08 onward (spliced gold). Gain is measured on total money deposited. No verdict.

## Ideas 4, 4b, 5 — Dynamic BTC share (rest in gold)

Common rules: base BTC weight 50%; checked every Monday; the portfolio trades to target when any weight
is more than 5 percentage points away from target (also on the first quarter day as in A1). **Common
test period 2019-01-01 → 2026-09-30** (needed for 4b's training).

| ID | BTC weight rule |
|---|---|
| 4 | 0.5 × min(1, 0.60 / σ̂), σ̂ = BTC 30-day realized volatility (annualized, √365) at the check day's close. 0.60 ≈ BTC's typical annual volatility, fixed without optimization |
| 4b (AI) | Same formula, σ̂ = forecast of the next 30 days' realized volatility from `HistGradientBoostingRegressor` (defaults, random_state=0). Features at close: realized vol over 7/30/90 days, abs 1-day and 7-day return, Fear & Greed. Expanding-window training from 2018-02-01, retrained each 1 January, using only rows whose 30-day-ahead target was known before that date |
| 5 | Crash brake: 0.5 if BTC close ≥ its 200-day SMA, else 0 |

Benchmarks on the same period: hold BTC; A1 = 50/50 quarterly.

**GO criteria (each of 4, 4b, 5):** max drawdown no worse than −40%; CAGR ≥ ⅔ of hold BTC; Sharpe > hold
BTC; **Sharpe > A1** (extra rules must beat the simple mix). 4b also reports its volatility forecast
error (mean absolute error) against the naive forecast (30-day realized vol); "AI helps" requires a
lower error **and** a higher Sharpe than Idea 4.

## Testnet rebalancer (Idea 2)

- Binance **Spot Testnet only** (`https://testnet.binance.vision`); the code refuses any other base URL.
  Testnet lists BTCUSDT and PAXGUSDT (checked 2026-10-06).
- Pure function computes orders from balances, prices and target weights; skips orders below the
  exchange minimum notional; sells before buys.
- Default mode is **dry run** (prints orders, sends nothing). `--live` sends MARKET orders to Testnet and
  needs `BINANCE_TESTNET_KEY` / `BINANCE_TESTNET_SECRET` from `.env` (gitignored). Keys are never
  printed, logged or committed. Old keys in `archive/` are never used.
- Strategy run on Testnet: the best GO strategy from this study, otherwise A1 (50/50 quarterly).

## Reporting

`reports/ideas-report.md`, results reported as they come out, including bad ones. Not financial advice.
