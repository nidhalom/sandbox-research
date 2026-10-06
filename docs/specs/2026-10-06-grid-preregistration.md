# Pre-registration — Spot Grid Bot (idea 6)

**Written:** 2026-10-06, before any grid backtest was run and before hourly data was downloaded.

## Question

Do Binance-style **spot grid bots** (like the "Spot Grid / Top ROI" marketplace bots) make money after
fees, and do they beat simply holding? Spot, long-only, no leverage: compatible with the owner's rules.

## Mechanics (Binance spot grid, neutral, no trailing, no stop-loss)

- Range [P0 × (1 − w), P0 × (1 + w)] around the launch price P0, split into N **geometric** cells.
- Capital C split equally across the N cells. At launch, cells entirely above P0 hold coin bought at P0
  with a market order (waiting to sell at the cell's upper level); the others hold USDT (waiting to buy
  at the cell's lower level).
- A cell holding USDT buys when the price touches its lower level; a cell holding coin sells when the
  price touches its upper level. Limit fills at the level price, **0.10% fee per fill**. The launch
  buy and the final close-out are market orders: 0.10% fee + 0.05% half-spread.
- Prices outside the range: the bot keeps what it holds (all coin below the range, all USDT above).
- **Data:** Binance hourly candles. Path inside each hour: open → the nearer of high/low → the other →
  close; every level crossed on that path fills once.

## Configurations

| | Range w | Cells N | Spacing |
|---|---|---|---|
| **Main (verdict)** | ±15% | 50 | ≈ 0.61% per cell |
| Narrow (informational) | ±7.5% | 25 | ≈ 0.60% |
| Wide (informational) | ±30% | 100 | ≈ 0.62% |

Markets: **BTCUSDT (verdict)**, ETHUSDT (informational). Period: 2021-01-01 → 2026-09-30.

## Tests

1. **30-day grids**, launched every Monday, closed out after 30 days: p10 / median / p90 / worst return,
   % losing, % beating holding the coin over the same 30 days, number of non-overlapping windows.
2. **Back-to-back monthly grid** (relaunched at the first hour of each month on the whole balance,
   closed out at month end): CAGR, max drawdown (on daily marks), Sharpe vs hold BTC.
3. **Screenshot check:** for grids launched every day, the share whose return after 5 days is ≥ +14%
   (the marketplace's top ROI shown ~14–17% in 5 days).

## GO criteria (main config on BTC, test 2)

All of: Sharpe > hold BTC; max drawdown no worse than −40%; CAGR ≥ ⅔ of hold BTC; fewer than 25% of
the 30-day grids in test 1 lose money ("steady income" claim).

## Limitations stated in advance

Touch-fills are optimistic (a real limit order may need the price to trade through); hourly path
order is an assumption; meme coins from the screenshot (MUBARAK, PUMP) are not tested. A GO justifies
Testnet paper trading only. Not financial advice.
