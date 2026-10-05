# Crypto Trend Research Engine

A research engine that tests whether a systematic trend-following strategy can make money on crypto
markets **after realistic costs and without the usual backtest biases**. It decides before any capital
is put at risk, and it is built to say "no" when the evidence says no.

**Phase 1 verdict: NO-GO.** A naive test on 10 hand-picked coins showed **+33% a year**. After removing
survivorship bias, modelling costs realistically and validating out-of-sample, the same idea delivered
**+1.8% a year**, against **+20.3%** for simply holding Bitcoin. The engine caught the mirage before it
cost anything.

## What it does

1. **Downloads survivorship-free data**: daily candles for all 757 Binance USDT spot pairs ever listed,
   including coins that were later delisted (LUNA, FTT…), from Binance's public archive.
2. **Builds a point-in-time universe**: each day, the 10 most traded coins *as known at that time*, with
   stablecoins, leveraged tokens and pegged assets excluded.
3. **Simulates the strategy day by day**: decisions use only data up to the previous close, orders fill at
   the next open, exchange-side stop-losses trigger intraday, and drawdown brakes cut risk in crashes.
4. **Charges realistic costs**: exchange fee, half-spread and square-root market impact on every trade;
   stop fills slip towards the day's low in flash crashes.
5. **Validates honestly**: walk-forward tuning (parameters chosen only on past data), bootstrap confidence
   intervals, Deflated Sharpe Ratio, and Probability of Backtest Overfitting (CSCV).
6. **Writes a go/no-go report** with pre-defined pass criteria.

## Strategy (long-only spot)

- Trend score per coin: average of `sign(close − SMA(n))` for n = 20, 50, 100.
- Position size: score ÷ volatility, then the whole portfolio is scaled to a 20% annual volatility target
  using the 60-day covariance matrix (so correlated coins are not double-counted).
- Caps: 30% per coin, 100% gross: no leverage, no shorting, no futures.
- Risk: 3×ATR trailing stops, drawdown brakes at −20% / −30% / −35%.

## Phase 1 results (Jan 2021 – Sep 2026, out-of-sample)

| | CAGR | Max drawdown | Sharpe |
|---|---|---|---|
| Strategy, walk-forward tuned | +1.8% | −39.1% | 0.19 |
| Strategy, fixed defaults | +1.3% | −30.1% | 0.17 |
| Hold BTC | +20.3% | −76.6% | 0.61 |
| Hold top-10 equal weight | +6.0% | −89.4% | 0.48 |

The strategy halved crash losses but gave up most of the upside. Full report:
[`reports/phase1-report.md`](reports/phase1-report.md).

### Follow-up: BTC + ETH only (pre-registered)

Rules were written down and committed **before** the run
([`docs/specs/2026-10-05-btc-eth-preregistration.md`](docs/specs/2026-10-05-btc-eth-preregistration.md)).
Verdict: **NO-GO**. The fixed rules made **+2.9% a year** (max drawdown −25%, Sharpe 0.28), against
+20.3% for holding BTC. It cut the 2022 crash from −64% to −15%, but missed most of the 2023–24 rally.
Full report: [`reports/btc-eth-report.md`](reports/btc-eth-report.md).

## Biases caught along the way

| Problem | Effect if ignored | Fix |
|---|---|---|
| **Survivorship bias**: testing on coins that exist today | Inflated returns (+33% → +1.8%) | Point-in-time universe including delisted coins |
| **Redenominations and reused tickers** (e.g. old LUNA vs LUNA 2.0, ×1000 price jumps) | Fake ×1000 returns | Series breaks: positions sold, history reset |
| **Delisting detected with future knowledge** | Subtle look-ahead | Delisting inferred only after a real data gap |
| **Optimistic stop fills** in flash crashes (10 Oct 2025: lows 12–57% below stops) | Understated losses | Fills slip towards the day's low, plus worst-case sensitivity |
| **Stablecoins in the universe** (RLUSD) | Capital parked in a dollar peg | Exclusion list plus minimum-volatility filter |
| **Brake deadlock**: a pause that could never end while in cash | Strategy stuck in cash for years | Pause ends after 30 days |
| **Overfitting** | Lucky parameters look like skill | Walk-forward, deflated Sharpe, PBO |

An independent audit of the engine is in [`reports/phase1-audit.md`](reports/phase1-audit.md).

## Project layout

```
botcore/     strategy, risk and cost logic (pure functions, reusable by a live bot)
research/    data download, universe, backtester, validation, tuning, report
tests/       66 tests (pytest)
docs/        design spec, implementation plan, pre-registrations
reports/     generated reports and charts
```

## How to run

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on Linux/macOS)
pip install -r requirements.txt

pytest -q                          # 66 tests

python -m research.run_phase1 --trials 60          # full study: downloads data, writes reports/phase1-report.md
python -m research.run_phase1 --skip-download --symbols BTCUSDT,ETHUSDT --max-single 0.5 \
       --primary untuned --report btc-eth --title "BTC + ETH Pre-registered Experiment"
```

The first run downloads about 35 MB of data from `data.binance.vision`. The full study takes about
30 minutes on a laptop.

## Tech

Python 3.12 · pandas · NumPy · SciPy · Optuna · Matplotlib · pytest

## Disclaimer

Research code. Nothing here is financial advice, and no strategy in this repository is cleared for real
money.
