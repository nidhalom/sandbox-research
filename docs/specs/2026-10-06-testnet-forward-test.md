# Pre-registration — Testnet Forward Test: 50% BTC / 50% Cash

**Written:** 2026-10-06, before the first Testnet order. Fake money only (Binance Spot Testnet).

## Why

No backtest can be clean any more: every year of history has been looked at. The only untouched data is
the future. This test runs the simplest strategy the evidence supports (BTC + cash; gold is set aside
while its Shariah status is unclear) and checks two things: that the bot behaves exactly as simulated,
and how the strategy does on months nobody has seen.

## Strategy (as implemented in `bot/testnet.py --strategy fixed --gold CASH`)

| Item | Rule |
|---|---|
| Target | 50% BTC, 50% USDT |
| Budget | $3,000 of Testnet USDT, tracked in `bot/state-fixed-CASH.json` (the rest of the Testnet wallet is ignored) |
| When | Every Tuesday shortly after 00:00 UTC (after Monday's daily close), and the day after each quarter starts |
| Trade rule | Rebalance to 50/50 when BTC's weight is more than 5 points from 50%; MARKET orders; orders under $5 skipped |
| Costs | Whatever the Testnet charges, recorded from each fill |

## Schedule

- **Start:** first live run on or after 2026-10-06 (the last closed candle must be a Monday or a quarter start).
- **Monthly check-ins:** value, fills, and any failed run.
- **Final evaluation:** 2027-04-06 (6 months).

## What is measured at the end

1. **Execution check (pass/fail):** replay the same weeks in the simulator (`botcore.portfolio.simulate`,
   Monday/quarter checks, 5-point band, 0.15% cost) from the same start price. Pass if the bot's final
   value is within **1%** of the replay and every scheduled run happened or was made up the next day.
2. **Performance (reported, no verdict):** total return, max drawdown (on weekly values) and number of
   trades, against holding BTC bought at the same first fill. Six months is far too short for
   statistical conclusions; the numbers are reported as they come, good or bad.

## Rules for the operator

- Never change the strategy, band or budget during the test. A missed Tuesday is run on Wednesday with
  `--force`, and noted.
- Testnet keys only (`.env`, gitignored); never real Binance keys. Not financial advice.
