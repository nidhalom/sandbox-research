# Pre-registration — BTC + ETH Trend Experiment

**Written:** 2026-10-05, before any BTC/ETH-only backtest was run.
**Engine:** the phase 1 research engine in `D:\sandbox` (spec: `2026-10-05-trend-bot-design.md`).

## Why this experiment

Phase 1 (top-10 coins by volume, survivorship-free) was NO-GO: +1.8% CAGR, Sharpe 0.19, versus +20.3% /
0.61 for holding BTC. Two candidate causes: (a) alt-coin universes are dominated by whipsaws and
collapses, and (b) a pause-brake defect (below) kept the untuned run in cash from 2022 to 2026. This
experiment tests trend-following on the two deepest, longest-lived markets only, with the defect fixed.

## ⚠️ Data already seen

The 2021–2026 period has already been examined in phase 1, including BTC and ETH behaviour in it. This
experiment is therefore **not a clean out-of-sample test**. To limit snooping, every rule below is fixed
now and nothing is tuned after seeing results. A GO here would justify Testnet only, never real money on
its own.

## Fixed rules

| Item | Value | Justification |
|---|---|---|
| Universe | BTCUSDT, ETHUSDT only | Longest history, deepest liquidity, no delisting risk |
| Signal | mean of sign(close − SMA(n)), n = 20, 50, 100, long-only | Phase 1 defaults, unchanged |
| Volatility window / covariance window | 30 / 60 days | Unchanged |
| Portfolio volatility target | 20% annual | Owner's risk choice (option B) |
| Max per coin | **50%** (was 30%) | With 2 coins a 30% cap mechanically limits exposure to 60%; 50% allows full investment while forcing both coins to share it |
| Max gross | 100%, no leverage, spot only | Hard rule 5 |
| Stops | 3 × ATR(14), trailed, fill halfway to the day's low, 5-day cooldown | Unchanged (post-audit) |
| Rebalance band | 2% | Unchanged |
| Brakes | −20% half size, −30% pause, −35% flat + stop (30-day backtest resume) | Unchanged |
| **Pause fix** | A pause ends after **30 days**: the peak is reset to current equity and the bot returns to normal | In cash, equity cannot recover to −25%, so the old rule could never end (phase 1 untuned run sat in cash 2022–2026). A time limit matches the existing 30-day resume after a full stop and needs no extra parameter search |
| Costs | 0.10% fee + 0.05% half-spread + 0.1·√(notional/ADV) | Unchanged |
| Test period | 2021-01-01 → last data (2026-09-30) | Same as phase 1 |

## Primary result and criteria

- **Primary strategy = the fixed rules above, untuned.** Tuning on two assets is easy to overfit, so the
  walk-forward run (same 5 parameters, 60 trials per year, as phase 1) is reported for information and
  used only to compute PBO.
- **Go criteria (identical to phase 1), all on the primary returns:** Sharpe ≥ 1.0; lower bound of the
  90% bootstrap CI of Sharpe ≥ 0.5; max drawdown no worse than −35%; PBO < 0.3; Sharpe above holding BTC;
  Sharpe above a 50/50 BTC+ETH equal-weight benchmark.
- Results are reported as they come out, including if they are bad.
