# Spot Grid Bot — Results

Pre-registration: `docs/specs/2026-10-06-grid-preregistration.md` (rules fixed before this run).
Hourly Binance candles 2021-01-01 → 2026-09-30. 0.10% fee per grid fill; 0.15% on market launch buys and close-outs. Touch-fills are optimistic. Not financial advice.

## Verdict (main grid on BTC)

**NO-GO**: Sharpe not above hold BTC; max drawdown worse than -40%; CAGR below 2/3 of hold BTC; 25% or more of 30-day grids lose money

## Test 1 — 30-day grids launched every Monday

`independent` = non-overlapping 30-day windows (about one per 4 launches).

| | p10 | median | p90 | worst | lose | windows | independent |
|---|---|---|---|---|---|---|---|
| BTCUSDT grid Main ±15%, 50 cells | -12.7% | +2.4% | +5.3% | -39.6% | 35% | 296 | 75 |
| BTCUSDT hold, same windows | -17.6% | +0.5% | +25.4% | -42.9% | 48% | 296 | 75 |
| BTCUSDT grid Narrow ±7.5%, 25 cells | -15.1% | +2.3% | +4.8% | -41.0% | 31% | 296 | 75 |
| BTCUSDT grid Wide ±30%, 100 cells | -9.0% | +1.4% | +6.8% | -35.0% | 38% | 296 | 75 |
| ETHUSDT grid Main ±15%, 50 cells | -19.0% | +2.7% | +6.3% | -40.8% | 39% | 296 | 75 |
| ETHUSDT hold, same windows | -24.6% | +1.0% | +32.7% | -45.1% | 48% | 296 | 75 |
| ETHUSDT grid Narrow ±7.5%, 25 cells | -21.9% | +2.5% | +6.6% | -43.0% | 38% | 296 | 75 |
| ETHUSDT grid Wide ±30%, 100 cells | -13.9% | +1.8% | +7.7% | -37.5% | 41% | 296 | 75 |

Share of 30-day windows where the grid beat holding the coin: BTCUSDT: Main ±15%, 50 cells 56%; BTCUSDT: Narrow ±7.5%, 25 cells 59%; BTCUSDT: Wide ±30%, 100 cells 53%; ETHUSDT: Main ±15%, 50 cells 56%; ETHUSDT: Narrow ±7.5%, 25 cells 58%; ETHUSDT: Wide ±30%, 100 cells 53%

## Test 2 — Grid relaunched every month on the whole balance

| | cagr | max_dd | sharpe |
|---|---|---|---|
| BTCUSDT hold | +20.0% | -76.6% | 0.60 |
| BTCUSDT monthly grid Main ±15%, 50 cells | -11.9% | -69.8% | -0.22 |
| BTCUSDT monthly grid Narrow ±7.5%, 25 cells | -20.7% | -79.4% | -0.46 |
| BTCUSDT monthly grid Wide ±30%, 100 cells | -3.0% | -59.0% | 0.03 |
| ETHUSDT hold | +25.5% | -79.3% | 0.68 |
| ETHUSDT monthly grid Main ±15%, 50 cells | -24.1% | -87.7% | -0.38 |
| ETHUSDT monthly grid Narrow ±7.5%, 25 cells | -32.0% | -92.4% | -0.55 |
| ETHUSDT monthly grid Wide ±30%, 100 cells | -10.4% | -73.9% | -0.10 |

## Test 3 — Screenshot check: grids launched every day, result after 5 days

| | share_ge_14pct | median_5d | best_5d | launches |
|---|---|---|---|---|
| BTCUSDT Main ±15%, 50 cells | 0.0% | +0.23% | +5.5% | 2094 |
| BTCUSDT Narrow ±7.5%, 25 cells | 0.0% | +0.48% | +6.1% | 2094 |
| BTCUSDT Wide ±30%, 100 cells | 0.0% | +0.08% | +7.1% | 2094 |
| ETHUSDT Main ±15%, 50 cells | 0.0% | +0.46% | +7.0% | 2094 |
| ETHUSDT Narrow ±7.5%, 25 cells | 0.0% | +0.86% | +6.4% | 2094 |
| ETHUSDT Wide ±30%, 100 cells | 0.0% | +0.27% | +8.1% | 2094 |

